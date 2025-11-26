import os
import time
import threading
from io import BytesIO
from urllib.parse import unquote

import vlc
from flask import Flask, request, redirect, send_from_directory, url_for, abort, render_template_string
from PIL import Image, ImageTk

import tkinter as tk

# -----------------------------
# Config
# -----------------------------
UPLOAD_FOLDER = os.path.expanduser("~/kiosk_images")
RTSP_URL = "rtsp://192.168.10.31:554/live/0/MAIN"
#RTSP_URL = "rtsp://admin:admin@192.168.100.27:554/11"
FLASK_PORT = 8080
FADE_DURATION = 1.0    # seconds
FADE_STEPS = 5

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# -----------------------------
# Tkinter window (kiosk)
# -----------------------------
root = tk.Tk()
root.title("Kiosk")
# Multiple approaches for fullscreen on Pi
root.attributes("-fullscreen", True)
root.overrideredirect(True)  # Remove window decorations
root.geometry(f"{root.winfo_screenwidth()}x{root.winfo_screenheight()}+0+0")
root.configure(background="black")
root.config(cursor="none")  # hide mouse cursor
root.focus_set()  # Ensure window has focus

screen_w = root.winfo_screenwidth()
screen_h = root.winfo_screenheight()

# container frames / widgets
video_container = tk.Frame(root, bg="black")
video_container.place(relx=0, rely=0, relwidth=1, relheight=1)

# Image label that sits on top of video
image_label = tk.Label(root, bg="black")
image_label.place(relx=0, rely=0, relwidth=1, relheight=1)
image_label.lower()  # start below overlay (so video visible)

# Black overlay used for fading (we change its PhotoImage of semi-transparent black)
overlay_label = tk.Label(root, bg="black")
overlay_label.place(relx=0, rely=0, relwidth=1, relheight=1)
overlay_label.lower()  # start below image_label

# Keep references to PhotoImage objects to prevent GC
_image_tk_ref = None
_overlay_tk_ref = None

# Pre-create black background for image compositing (reused for performance)
_black_bg = None

# GUI state
_gui_lock = threading.Lock()
_showing_image = False
_current_image_name = None

# -----------------------------
# VLC setup (no-audio to avoid G.711 issues)
# -----------------------------
# Create a VLC instance with fallbacks. Hardware-accelerated video renderers
# on the Pi (DRM/OMX/MMAL) often use a hardware overlay that stays on top
# of the window system and can hide Tk widgets. Try a sequence of args that
# prefers non-overlay rendering when available.
def _make_vlc_instance():
    candidates = [
        ["--no-audio", "--rtsp-tcp", "--no-osd", "--no-sub-autodetect-file" , "--avcodec-hw=drm"],
        ["--no-audio", "--rtsp-tcp", "--no-osd", "--no-sub-autodetect-file"],
        ["--no-audio", "--rtsp-tcp", "--no-osd", "--no-sub-autodetect-file", "--vout=gl"],
    ]
    last_exc = None
    for args in candidates:
        try:
            inst = vlc.Instance(*args)
            print("VLC: created instance with args:", args)
            return inst, args
        except Exception as e:
            print("VLC: instance failed with args", args, "error:", e)
            last_exc = e
    # final fallback: try default constructor
    try:
        inst = vlc.Instance()
        print("VLC: created default instance")
        return inst, []
    except Exception as e:
        print("VLC: failed to create any instance:", e)
        raise last_exc or e


_instance, _chosen_vlc_args = _make_vlc_instance()
_player = _instance.media_player_new()


def embed_vlc_to_tk():
    """Attach VLC video to Tk window XID (works on X11)."""
    root.update_idletasks()
    win_id = video_container.winfo_id()
    try:
        # X11
        _player.set_xwindow(win_id)
    except Exception:
        try:
            # macOS / Windows variants (not expected on Pi)
            _player.set_hwnd(win_id)
        except Exception:
            pass


def _detach_vlc_window():
    """Try to detach VLC's video output from the window so any hardware
    overlay is removed. This helps when we need to show a Tk widget above
    the video on platforms where the video plane is privileged.
    """
    try:
        _player.set_xwindow(0)
        print("VLC: detached X window (set_xwindow(0))")
        return
    except Exception:
        pass
    try:
        _player.set_hwnd(0)
        print("VLC: detached HWND (set_hwnd(0))")
        return
    except Exception:
        pass
    try:
        # Fallback: stop the player to remove any overlay
        _player.stop()
        print("VLC: stopped player as fallback to remove overlay")
    except Exception as e:
        print("VLC: failed to detach or stop player:", e)


def _attach_vlc_window():
    """Re-attach VLC to the Tk video container and resume playback if possible."""
    try:
        embed_vlc_to_tk()
        print("VLC: re-attached video to Tk window")
    except Exception as e:
        print("VLC: failed to re-attach video window:", e)


def start_vlc(url):
    """Start or restart VLC media with new URL."""
    print("VLC: starting media", url)
    media = _instance.media_new(url)
    _player.set_media(media)
    embed_vlc_to_tk()
    _player.play()
    # give time to start and print state for diagnostics
    time.sleep(0.5)
    try:
        state = _player.get_state()
        print("VLC: player state after play() ->", state)
    except Exception:
        pass
    # keep audio off
    try:
        _player.audio_set_mute(True)
    except Exception:
        pass


# initialize once
start_vlc(RTSP_URL)

# -----------------------------
# Fade helpers (all GUI updates MUST be done via root.after)
# -----------------------------
def _make_overlay_image(alpha: float):
    """Return a PhotoImage of a semi-transparent black rectangle with given alpha [0..1]."""
    global _overlay_tk_ref
    a = int(max(0, min(1, alpha)) * 255)
    # Create an RGBA image (black with alpha a)
    img = Image.new("RGBA", (screen_w, screen_h), (0, 0, 0, a))
    tkimg = ImageTk.PhotoImage(img)
    _overlay_tk_ref = tkimg
    return tkimg


def _set_overlay_alpha(alpha: float):
    """Set overlay_label to semi-transparent black with given alpha."""
    tkimg = _make_overlay_image(alpha)
    overlay_label.config(image=tkimg)
    overlay_label.lift()


def _load_and_scale_image(path: str):
    """Load image from path and scale to fit screen (preserve aspect)."""
    global _black_bg
    img = Image.open(path)
    # Convert to RGB for faster processing (no alpha channel)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    iw, ih = img.size
    sw, sh = screen_w, screen_h
    # scale preserving aspect
    scale = min(sw / iw, sh / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    # Use BILINEAR for faster scaling on Pi (LANCZOS is slower but higher quality)
    img = img.resize((nw, nh), Image.BILINEAR)

    # Reuse black background if size matches
    if _black_bg is None or _black_bg.size != (sw, sh):
        _black_bg = Image.new("RGB", (sw, sh), (0, 0, 0))
    else:
        # Fill with black
        _black_bg.paste((0, 0, 0), (0, 0, sw, sh))
    
    # Center image on black background
    x = (sw - nw) // 2
    y = (sh - nh) // 2
    _black_bg.paste(img, (x, y))
    return _black_bg


def _set_image_tk(img_pil):
    """Set image_label to the given PIL RGBA image."""
    global _image_tk_ref
    tkimg = ImageTk.PhotoImage(img_pil)
    _image_tk_ref = tkimg
    image_label.config(image=tkimg)
    image_label.lift()


# Show image immediately (no fade)
def _fade_and_show_image(path: str):
    print("GUI: showing image immediately:", path)
    # Stop player first to remove overlay quickly
    try:
        _player.stop()
        print("VLC: stopped player")
    except Exception as e:
        print("GUI: failed to stop VLC:", e)
    try:
        print(f"GUI: loading image from {path}")
        pil = _load_and_scale_image(path)
        print(f"GUI: image loaded, size={pil.size}, setting to Tk...")
        _set_image_tk(pil)
        print("GUI: image set to Tk successfully")
    except Exception as e:
        print("Image load error:", e)
        import traceback
        traceback.print_exc()
        return
    # bring image_label on top
    image_label.lift()
    overlay_label.lower()
    print("GUI: image displayed, overlay lowered")


def _fade_and_show_stream():
    """Show stream immediately (no fade)."""
    print("GUI: switching back to stream")
    # remove image
    image_label.config(image="")
    image_label.lower()
    overlay_label.lower()
    # restart VLC to restore stream (since we stopped it)
    try:
        start_vlc(RTSP_URL)
        print("GUI: stream restarted")
    except Exception as e:
        print("GUI: failed to restart VLC:", e)
    print("GUI: stream should be visible now")


# Public GUI scheduling helpers (safe to call from Flask threads)
def gui_show_image(path):
    with _gui_lock:
        root.after(0, lambda: _fade_and_show_image(path))


def gui_show_stream():
    with _gui_lock:
        root.after(0, _fade_and_show_stream)


# -----------------------------
# Flask web app
# -----------------------------
app = Flask(__name__)


INDEX_HTML = """
<!doctype html>
<html><head><title>Kiosk Control</title>
<style>
body{font-family:Arial;margin:20px;}
button{padding:10px 15px;margin:5px;}
.file{margin:6px 0;}
</style>
</head><body>
<h1>Kiosk Controller</h1>
<form action="/set_stream" method="get">
  <label>RTSP URL: <input name="url" size="60" value="{{ current_url|e }}"></label>
  <button type="submit">Set Stream</button>
</form>
<p><a href="/show_stream"><button>Show Stream</button></a></p>

<h2>Upload Image</h2>
<form action="/upload" method="post" enctype="multipart/form-data">
  <input type="file" name="file" accept="image/*" required>
  <button type="submit">Upload</button>
</form>

<h2>Images</h2>
<ul>
{% for f in files %}
  <li class="file">
    {{ f }} &nbsp;
    <a href="{{ url_for('show_image', name=f) }}"><button>Show</button></a>
    <a href="{{ url_for('delete_image', name=f) }}"><button style="background:#b33;color:white;">Delete</button></a>
    <a href="{{ url_for('serve_image', name=f) }}" target="_blank">View</a>
  </li>
{% endfor %}
</ul>

<hr>
<p><a href="/kill" onclick="return confirm('Shutdown the kiosk application?');"><button style="background:#900;color:white;">Shutdown App</button></a></p>
</body></html>
"""


@app.route("/")
def index():
    files = sorted([f for f in os.listdir(UPLOAD_FOLDER) if f.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp"))])
    return render_template_string(INDEX_HTML, files=files, current_url=RTSP_URL)


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file:
        return "No file uploaded", 400
    # sanitize filename a bit
    filename = os.path.basename(file.filename)
    savepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(savepath)
    return redirect(url_for("index"))


@app.route("/show_image/<path:name>")
def show_image(name):
    # name may be URL-encoded; decode safely
    name = unquote(name)
    path = os.path.join(UPLOAD_FOLDER, name)
    if not os.path.exists(path):
        return "Not found", 404
    # schedule GUI show
    gui_show_image(path)
    return redirect(url_for("index"))


@app.route("/delete/<path:name>")
def delete_image(name):
    name = unquote(name)
    path = os.path.join(UPLOAD_FOLDER, name)
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        return f"Error deleting: {e}", 500
    return redirect(url_for("index"))


@app.route("/show_stream")
def show_stream():
    gui_show_stream()
    return redirect(url_for("index"))


@app.route("/images/<path:name>")
def serve_image(name):
    name = unquote(name)
    return send_from_directory(UPLOAD_FOLDER, name)


@app.route("/set_stream")
def set_stream():
    global RTSP_URL
    new_url = request.args.get("url")
    if not new_url:
        return "Missing url parameter", 400
    RTSP_URL = new_url
    # restart vlc media safely in background
    def do_restart():
        try:
            _player.stop()
        except Exception:
            pass
        # small delay to allow stop
        time.sleep(0.3)
        start_vlc(RTSP_URL)
    threading.Thread(target=do_restart, daemon=True).start()
    return redirect(url_for("index"))


@app.route("/kill")
def kill_app():
    """Shutdown the application."""
    def do_shutdown():
        time.sleep(0.5)  # Give time to send response
        shutdown()
    threading.Thread(target=do_shutdown, daemon=True).start()
    return "Shutting down kiosk application...", 200

import signal
import sys

def shutdown(*args):
    print("shutting down...")
    try:
        _player.stop()
    except:
        pass
    root.destroy()
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

# -----------------------------
# Start Flask thread and Tk mainloop
# -----------------------------
def run_flask():
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    # ensure VLC embedded after mainloop starts
    root.after(100, embed_vlc_to_tk)
    root.mainloop()
