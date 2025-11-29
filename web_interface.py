"""Flask web interface for kiosk control."""
import json
import os
import time
import threading
from urllib.parse import unquote
from flask import Flask, request, redirect, send_from_directory, url_for, render_template_string, jsonify

import config
from ptz_controller import PTZController


INDEX_HTML = """
<!doctype html>
<html><head><title>Kiosk Control</title>
<style>
body{font-family:Arial;margin:20px;}
button{padding:10px 15px;margin:5px;}
.file{margin:6px 0;}
.ptz-section{background:#f5f5f5;padding:15px;border-radius:8px;margin:15px 0;}
.ptz-controls{display:flex;gap:20px;flex-wrap:wrap;align-items:flex-start;}
.ptz-sliders{flex:1;min-width:300px;}
.ptz-presets{flex:1;min-width:250px;}
.slider-group{margin:10px 0;}
.slider-group label{display:block;margin-bottom:5px;}
.slider-group input[type="range"]{width:100%;}
.slider-value{font-family:monospace;margin-left:10px;}
.preset-item{margin:6px 0;padding:5px;background:#fff;border-radius:4px;}
.preset-item button{padding:5px 10px;margin:2px;}
.camera-config{margin-bottom:15px;padding:10px;background:#e8e8e8;border-radius:4px;}
.camera-config input{margin:0 5px;}
</style>
</head><body>
<h1>Kiosk Controller</h1>
<form action="/set_stream" method="get">
  <label>RTSP URL: <input name="url" size="60" value="{{ current_url|e }}"></label>
  <button type="submit">Set Stream</button>
</form>
<p><a href="/show_stream"><button>Show Stream</button></a></p>

<h2>PTZ Camera Control</h2>
<div class="ptz-section">
  <div class="camera-config">
    <form action="/ptz/configure" method="post" style="display:inline;">
      <label>Camera Host: <input name="host" size="15" value="{{ ptz_host|e if ptz_host else '' }}" placeholder="192.168.1.100"></label>
      <label>Port: <input name="port" size="5" value="{{ ptz_port }}"></label>
      <label>User: <input name="username" size="10" value="{{ ptz_username|e }}"></label>
      <label>Pass: <input name="password" type="password" size="10" value="{{ ptz_password|e }}"></label>
      <button type="submit">Configure &amp; Connect</button>
    </form>
    <span style="margin-left:15px;">Status: <strong>{{ 'Connected' if ptz_connected else 'Not Connected' }}</strong></span>
  </div>
  
  <div class="ptz-controls">
    <div class="ptz-sliders">
      <h3>Position Controls</h3>
      <form action="/ptz/move" method="post" id="ptz-form">
        <div class="slider-group">
          <label>Pan: <span class="slider-value" id="pan-value">{{ "%.2f"|format(ptz_position.pan) }}</span></label>
          <input type="range" name="pan" id="pan-slider" min="-1" max="1" step="0.01" value="{{ ptz_position.pan }}">
        </div>
        <div class="slider-group">
          <label>Tilt: <span class="slider-value" id="tilt-value">{{ "%.2f"|format(ptz_position.tilt) }}</span></label>
          <input type="range" name="tilt" id="tilt-slider" min="-1" max="1" step="0.01" value="{{ ptz_position.tilt }}">
        </div>
        <div class="slider-group">
          <label>Zoom: <span class="slider-value" id="zoom-value">{{ "%.2f"|format(ptz_position.zoom) }}</span></label>
          <input type="range" name="zoom" id="zoom-slider" min="0" max="1" step="0.01" value="{{ ptz_position.zoom }}">
        </div>
        <button type="submit">Move Camera</button>
      </form>
      
      <h4>Save Current Position as Preset</h4>
      <form action="/ptz/presets" method="post">
        <input type="hidden" name="pan" id="save-pan" value="{{ ptz_position.pan }}">
        <input type="hidden" name="tilt" id="save-tilt" value="{{ ptz_position.tilt }}">
        <input type="hidden" name="zoom" id="save-zoom" value="{{ ptz_position.zoom }}">
        <input type="text" name="name" placeholder="Preset name" required pattern="[a-zA-Z0-9_\\-\\s]+">
        <button type="submit">Save Preset</button>
      </form>
    </div>
    
    <div class="ptz-presets">
      <h3>Saved Presets</h3>
      {% if ptz_presets %}
        {% for name, pos in ptz_presets.items() %}
        <div class="preset-item">
          <strong>{{ name }}</strong>
          <span style="font-size:0.8em;color:#666;">(P:{{ "%.2f"|format(pos.pan) }} T:{{ "%.2f"|format(pos.tilt) }} Z:{{ "%.2f"|format(pos.zoom) }})</span>
          <br>
          <a href="{{ url_for('ptz_goto_preset', name=name) }}"><button>Go To</button></a>
          <a href="{{ url_for('ptz_delete_preset', name=name) }}" onclick="return confirm('Delete preset {{ name }}?');"><button style="background:#b33;color:white;">Delete</button></a>
        </div>
        {% endfor %}
      {% else %}
        <p><em>No presets saved yet.</em></p>
      {% endif %}
    </div>
  </div>
</div>

<script>
// Update slider value displays
document.querySelectorAll('input[type="range"]').forEach(function(slider) {
  slider.addEventListener('input', function() {
    var valueSpan = document.getElementById(this.id.replace('-slider', '-value'));
    if (valueSpan) valueSpan.textContent = parseFloat(this.value).toFixed(2);
    // Update hidden fields for save preset form
    document.getElementById('save-pan').value = document.getElementById('pan-slider').value;
    document.getElementById('save-tilt').value = document.getElementById('tilt-slider').value;
    document.getElementById('save-zoom').value = document.getElementById('zoom-slider').value;
  });
});
</script>

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
    
    def __init__(self, gui, vlc_player, shutdown_callback, ptz_controller=None):
        self.gui = gui
        self.vlc_player = vlc_player
        self.shutdown_callback = shutdown_callback
        self.rtsp_url = config.RTSP_URL
        
        # Initialize PTZ controller if not provided
        if ptz_controller is None:
            self.ptz = PTZController(
                presets_file=config.PTZ_PRESETS_FILE,
                camera_host=config.PTZ_CAMERA_HOST,
                camera_port=config.PTZ_CAMERA_PORT,
                username=config.PTZ_CAMERA_USERNAME,
                password=config.PTZ_CAMERA_PASSWORD
            )
        else:
            self.ptz = ptz_controller
        
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
        
        # PTZ routes
        self.app.route("/ptz/configure", methods=["POST"])(self.ptz_configure)
        self.app.route("/ptz/move", methods=["POST"])(self.ptz_move)
        self.app.route("/ptz/position", methods=["GET"])(self.ptz_get_position)
        self.app.route("/ptz/presets", methods=["GET"])(self.ptz_list_presets)
        self.app.route("/ptz/presets", methods=["POST"])(self.ptz_save_preset)
        self.app.route("/ptz/presets/<path:name>", methods=["DELETE"])(self.ptz_delete_preset_api)
        self.app.route("/ptz/delete/<path:name>")(self.ptz_delete_preset)
        self.app.route("/ptz/goto/<path:name>")(self.ptz_goto_preset)
    
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
            ptz_host=self.ptz.camera_host,
            ptz_port=self.ptz.camera_port,
            ptz_username=self.ptz.username,
            ptz_password=self.ptz.password,
            ptz_connected=self.ptz.is_connected(),
            ptz_position=self.ptz.get_position(),
            ptz_presets=self.ptz.list_presets()
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
    
    # PTZ Control Methods
    
    def ptz_configure(self):
        """Configure and connect to PTZ camera."""
        host = request.form.get("host", "").strip()
        port = request.form.get("port", "80")
        username = request.form.get("username", "admin")
        password = request.form.get("password", "admin")
        
        if not host:
            return "Camera host is required", 400
        
        try:
            port = int(port)
        except ValueError:
            return "Invalid port number", 400
        
        self.ptz.configure_camera(host, port, username, password)
        self.ptz.connect()
        
        return redirect(url_for("index"))
    
    def ptz_move(self):
        """Move camera to absolute position."""
        try:
            pan = float(request.form.get("pan", 0))
            tilt = float(request.form.get("tilt", 0))
            zoom = float(request.form.get("zoom", 0))
        except (TypeError, ValueError):
            return "Invalid PTZ values", 400
        
        success = self.ptz.absolute_move(pan, tilt, zoom)
        
        # Check if this is an API call (JSON) or form submission
        if request.is_json or request.headers.get('Accept') == 'application/json':
            return jsonify({
                "success": success,
                "position": {"pan": pan, "tilt": tilt, "zoom": zoom}
            })
        
        return redirect(url_for("index"))
    
    def ptz_get_position(self):
        """Get current PTZ position (API endpoint)."""
        position = self.ptz.get_position()
        return jsonify({
            "connected": self.ptz.is_connected(),
            "position": position
        })
    
    def ptz_list_presets(self):
        """List all saved PTZ presets (API endpoint)."""
        return jsonify({
            "presets": self.ptz.list_presets()
        })
    
    def ptz_save_preset(self):
        """Save a PTZ preset."""
        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json()
            name = data.get("name", "").strip()
            pan = data.get("pan", 0)
            tilt = data.get("tilt", 0)
            zoom = data.get("zoom", 0)
        else:
            name = request.form.get("name", "").strip()
            pan = request.form.get("pan", 0)
            tilt = request.form.get("tilt", 0)
            zoom = request.form.get("zoom", 0)
        
        if not name:
            if request.is_json:
                return jsonify({"error": "Preset name is required"}), 400
            return "Preset name is required", 400
        
        try:
            pan = float(pan)
            tilt = float(tilt)
            zoom = float(zoom)
        except (TypeError, ValueError):
            if request.is_json:
                return jsonify({"error": "Invalid PTZ values"}), 400
            return "Invalid PTZ values", 400
        
        success = self.ptz.save_preset(name, pan, tilt, zoom)
        
        if request.is_json:
            if success:
                return jsonify({
                    "success": True,
                    "preset": {"name": name, "pan": pan, "tilt": tilt, "zoom": zoom}
                }), 201
            return jsonify({"error": "Failed to save preset"}), 500
        
        return redirect(url_for("index"))
    
    def ptz_delete_preset_api(self, name):
        """Delete a PTZ preset (API endpoint with DELETE method)."""
        name = unquote(name)
        success = self.ptz.delete_preset(name)
        
        if success:
            return jsonify({"success": True, "deleted": name})
        return jsonify({"error": f"Preset '{name}' not found"}), 404
    
    def ptz_delete_preset(self, name):
        """Delete a PTZ preset (web UI endpoint)."""
        name = unquote(name)
        self.ptz.delete_preset(name)
        return redirect(url_for("index"))
    
    def ptz_goto_preset(self, name):
        """Move camera to a saved preset position."""
        name = unquote(name)
        success = self.ptz.goto_preset(name)
        
        if request.is_json or request.headers.get('Accept') == 'application/json':
            if success:
                preset = self.ptz.get_preset(name)
                return jsonify({"success": True, "preset": name, "position": preset})
            return jsonify({"error": f"Preset '{name}' not found"}), 404
        
        return redirect(url_for("index"))
    
    def run(self):
        """Run the Flask server."""
        self.app.run(host="0.0.0.0", port=config.FLASK_PORT, debug=False, use_reloader=False)
