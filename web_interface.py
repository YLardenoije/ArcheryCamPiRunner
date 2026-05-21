"""Flask web interface for kiosk control."""
import os
import time
import threading
from urllib.parse import unquote
from flask import Flask, request, redirect, send_from_directory, url_for, render_template_string

import config


INDEX_HTML = """
<!doctype html>
<html><head><title>Kiosk Control</title>
<style>
body{font-family:Arial;margin:20px;}
button{padding:10px 15px;margin:5px;}
.file{margin:6px 0;}
.camera-list{margin:6px 0;min-width:60ch;}
.camera-card{border:1px solid #ccc;padding:10px;margin:10px 0;border-radius:8px;}
.camera-meta{font-size:0.9rem;color:#333;}
.camera-form input,.camera-form select{margin:4px;}
</style>
</head><body>
<h1>Kiosk Controller</h1>
<form action="/set_stream" method="get">
    <label>Camera: 
        <select name="url" class="camera-list">
        {% if cameras %}
            {% for camera in cameras %}
                <option value="{{ camera.url|e }}" {% if camera.url == current_url %}selected{% endif %}>
                    {{ camera.name }} - {{ camera.url }}
                </option>
            {% endfor %}
        {% else %}
            <option value="" selected>No cameras discovered yet</option>
        {% endif %}
        </select>
    </label>
  <button type="submit">Set Stream</button>
</form>
<p><a href="/show_stream"><button>Show Stream</button></a></p>

<h2>Camera Settings (Persistent by MAC)</h2>
{% if cameras %}
    {% for camera in cameras %}
    <div class="camera-card">
        <div><strong>{{ camera.name }}</strong></div>
        <div class="camera-meta">URL: {{ camera.url }}</div>
        <div class="camera-meta">MAC: {{ camera.mac or "unknown" }}</div>
        <form action="/camera_settings" method="post" class="camera-form">
            <input type="hidden" name="url" value="{{ camera.url|e }}">
            <label>Friendly name:
                <input type="text" name="name" value="{{ camera.name|e }}" size="28">
            </label>
            <label>Role:
                <select name="role">
                    <option value="none" {% if not camera.role %}selected{% endif %}>None</option>
                    <option value="primary" {% if camera.role == "primary" %}selected{% endif %}>Primary</option>
                    <option value="secondary" {% if camera.role == "secondary" %}selected{% endif %}>Secondary</option>
                </select>
            </label>
            <label>Zoom (-1..1):
                <input type="number" name="zoom" min="-1" max="1" step="0.1" value="{{ camera.ptz.zoom }}">
            </label>
            <label>Focus (-1..1):
                <input type="number" name="focus" min="-1" max="1" step="0.1" value="{{ camera.ptz.focus }}">
            </label>
            <button type="submit" name="action" value="save">Save</button>
            <button type="submit" name="action" value="apply">Apply PTZ</button>
        </form>
    </div>
    {% endfor %}
{% else %}
    <p>No cameras discovered yet.</p>
{% endif %}

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


class WebInterface:
    """Flask web interface for controlling the kiosk."""
    
    def __init__(
        self,
        gui,
        vlc_player,
        shutdown_callback,
        initial_rtsp_url=None,
        initial_cameras=None,
        settings_store=None,
        apply_ptz_fn=None,
    ):
        self.gui = gui
        self.vlc_player = vlc_player
        self.shutdown_callback = shutdown_callback
        self.camera_choices = list(initial_cameras or [])
        self.rtsp_url = initial_rtsp_url or config.RTSP_URL or ""
        self.settings_store = settings_store
        self.apply_ptz_fn = apply_ptz_fn
        self._ensure_camera_defaults(self.camera_choices)
        if self.settings_store:
            self.settings_store.apply_to_cameras(self.camera_choices)
            self._ensure_camera_defaults(self.camera_choices)
        
        self.app = Flask(__name__)
        self._setup_routes()

    def update_cameras(self, cameras, selected_url=None):
        """Replace the available camera list and optionally select one."""
        self.camera_choices = list(cameras or [])
        self._ensure_camera_defaults(self.camera_choices)
        if self.settings_store:
            self.settings_store.apply_to_cameras(self.camera_choices)
            self._ensure_camera_defaults(self.camera_choices)
        if selected_url is not None:
            self.rtsp_url = selected_url
    
    def _setup_routes(self):
        """Setup Flask routes."""
        self.app.route("/")(self.index)
        self.app.route("/upload", methods=["POST"])(self.upload)
        self.app.route("/show_image/<path:name>")(self.show_image)
        self.app.route("/delete/<path:name>")(self.delete_image)
        self.app.route("/show_stream")(self.show_stream)
        self.app.route("/images/<path:name>")(self.serve_image)
        self.app.route("/set_stream")(self.set_stream)
        self.app.route("/camera_settings", methods=["POST"])(self.camera_settings)
        self.app.route("/kill")(self.kill_app)

    @staticmethod
    def _ensure_camera_defaults(cameras):
        for camera in cameras or []:
            camera.setdefault("mac", "")
            camera.setdefault("role", "")
            ptz = camera.get("ptz", {}) or {}
            camera["ptz"] = {
                "zoom": float(ptz.get("zoom", 0.0)),
                "focus": float(ptz.get("focus", 0.0)),
            }

    @staticmethod
    def _clamp_unit(value, default=0.0):
        try:
            num = float(value)
        except Exception:
            return float(default)
        return max(-1.0, min(1.0, num))

    def _find_camera_by_url(self, url):
        for camera in self.camera_choices:
            if camera.get("url") == url:
                return camera
        return None

    def _apply_ptz(self, camera, zoom, focus):
        host = camera.get("host", "")
        name = camera.get("name", host)
        print(f"PTZ: _apply_ptz camera={name!r} host={host!r} zoom={zoom} focus={focus} fn_set={self.apply_ptz_fn is not None}")
        if not self.apply_ptz_fn:
            print("PTZ: no apply_ptz_fn configured, skipping")
            return False, "PTZ control is not configured"
        return self.apply_ptz_fn(camera, zoom, focus)
    
    def index(self):
        """Main page."""
        files = sorted([
            f for f in os.listdir(config.UPLOAD_FOLDER)
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp"))
        ])
        return render_template_string(
            INDEX_HTML,
            files=files,
            current_url=self.rtsp_url,
            cameras=self.camera_choices,
        )
    
    def upload(self):
        """Handle file upload."""
        file = request.files.get("file")
        if not file:
            return "No file uploaded", 400
        # Sanitize filename
        filename = os.path.basename(file.filename)
        savepath = os.path.join(config.UPLOAD_FOLDER, filename)
        file.save(savepath)
        return redirect(url_for("index"))
    
    def show_image(self, name):
        """Display an image on the kiosk."""
        name = unquote(name)
        path = os.path.join(config.UPLOAD_FOLDER, name)
        if not os.path.exists(path):
            return "Not found", 404
        # Schedule GUI show
        self.gui.show_image(path)
        return redirect(url_for("index"))
    
    def delete_image(self, name):
        """Delete an image."""
        name = unquote(name)
        path = os.path.join(config.UPLOAD_FOLDER, name)
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            return f"Error deleting: {e}", 500
        return redirect(url_for("index"))
    
    def show_stream(self):
        """Show the RTSP stream."""
        if not self.rtsp_url:
            return "No camera selected", 400
        self.gui.show_stream(self.rtsp_url)
        return redirect(url_for("index"))
    
    def serve_image(self, name):
        """Serve an image file."""
        name = unquote(name)
        return send_from_directory(config.UPLOAD_FOLDER, name)
    
    def set_stream(self):
        """Change the RTSP stream URL."""
        new_url = request.args.get("url")
        if not new_url:
            return "Missing url parameter", 400
        self.rtsp_url = new_url
        for camera in self.camera_choices:
            if camera.get("url") == new_url:
                break
        # Restart VLC media safely in background
        def do_restart():
            try:
                self.vlc_player.stop()
            except Exception:
                pass
            # Small delay to allow stop
            time.sleep(0.3)
            win_id = self.gui.get_video_container_id()
            self.vlc_player.embed_to_window(win_id)
            self.vlc_player.start_media(self.rtsp_url)

            selected = self._find_camera_by_url(self.rtsp_url)
            if selected:
                ptz = selected.get("ptz", {}) or {}
                zoom = self._clamp_unit(ptz.get("zoom", 0.0), 0.0)
                focus = self._clamp_unit(ptz.get("focus", 0.0), 0.0)
                ok, msg = self._apply_ptz(selected, zoom, focus)
                print("PTZ apply on stream select:", "ok" if ok else "failed", msg)
        threading.Thread(target=do_restart, daemon=True).start()
        return redirect(url_for("index"))

    def camera_settings(self):
        """Update persistent camera metadata and optional PTZ control."""
        url = (request.form.get("url") or "").strip()
        if not url:
            return "Missing camera URL", 400

        camera = self._find_camera_by_url(url)
        if not camera:
            return "Camera not found", 404

        friendly_name = (request.form.get("name") or "").strip()
        role = (request.form.get("role") or "none").strip().lower()
        action = (request.form.get("action") or "save").strip().lower()
        zoom = self._clamp_unit(request.form.get("zoom", 0.0), 0.0)
        focus = self._clamp_unit(request.form.get("focus", 0.0), 0.0)

        camera["name"] = friendly_name or camera.get("name", "camera")
        camera["role"] = role if role in ("primary", "secondary") else ""
        camera["ptz"] = {"zoom": zoom, "focus": focus}

        if camera["role"]:
            for other in self.camera_choices:
                if other is camera:
                    continue
                if other.get("role") == camera["role"]:
                    other["role"] = ""

        mac = (camera.get("mac") or "").strip()
        if mac and self.settings_store:
            self.settings_store.set_settings(
                mac,
                name=friendly_name,
                role=role,
                zoom=zoom,
                focus=focus,
            )

        if action == "apply":
            ok, msg = self._apply_ptz(camera, zoom, focus)
            print("PTZ apply from web UI:", "ok" if ok else "failed", msg)

        return redirect(url_for("index"))
    
    def kill_app(self):
        """Shutdown the application."""
        def do_shutdown():
            time.sleep(0.5)  # Give time to send response
            self.shutdown_callback()
        threading.Thread(target=do_shutdown, daemon=True).start()
        return "Shutting down kiosk application...", 200
    
    def run(self):
        """Run the Flask server."""
        self.app.run(host="0.0.0.0", port=config.FLASK_PORT, debug=False, use_reloader=False)
