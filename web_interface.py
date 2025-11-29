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


class WebInterface:
    """Flask web interface for controlling the kiosk."""
    
    def __init__(self, gui, vlc_player, shutdown_callback):
        self.gui = gui
        self.vlc_player = vlc_player
        self.shutdown_callback = shutdown_callback
        self.rtsp_url = config.RTSP_URL
        
        self.app = Flask(__name__)
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup Flask routes."""
        self.app.route("/")(self.index)
        self.app.route("/upload", methods=["POST"])(self.upload)
        self.app.route("/show_image/<path:name>")(self.show_image)
        self.app.route("/delete/<path:name>")(self.delete_image)
        self.app.route("/show_stream")(self.show_stream)
        self.app.route("/images/<path:name>")(self.serve_image)
        self.app.route("/set_stream")(self.set_stream)
        self.app.route("/kill")(self.kill_app)
    
    def index(self):
        """Main page."""
        files = sorted([
            f for f in os.listdir(config.UPLOAD_FOLDER)
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp"))
        ])
        return render_template_string(INDEX_HTML, files=files, current_url=self.rtsp_url)
    
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
        threading.Thread(target=do_restart, daemon=True).start()
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
