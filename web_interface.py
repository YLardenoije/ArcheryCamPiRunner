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
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{font-family:Arial;margin:20px;max-width:900px;}
button{padding:8px 14px;margin:4px;cursor:pointer;}
.file{margin:6px 0;}
.camera-list{margin:6px 0;min-width:40ch;}
.camera-card{border:1px solid #ccc;padding:12px;margin:10px 0;border-radius:8px;background:#fafafa;}
.camera-meta{font-size:0.85rem;color:#555;margin:2px 0;}
.camera-form label{display:block;margin:5px 0;}
.camera-form input[type=text],.camera-form select{padding:4px;margin:3px;}
.ptz-section{margin-top:10px;padding:10px;background:#eef2ff;border-radius:6px;}
.ptz-section h4{margin:0 0 6px 0;font-size:0.95rem;color:#224;}
.ptz-hint{font-size:0.78rem;color:#668;margin-bottom:8px;}
.slider-row{display:flex;align-items:center;gap:10px;margin:4px 0;}
.slider-row input[type=range]{flex:1;min-width:160px;}
.slider-row output{min-width:3.2em;font-family:monospace;font-size:0.9rem;}
.ptz-status{font-size:0.85rem;margin-left:8px;vertical-align:middle;}
</style>
</head><body>
<h1>Kiosk Controller</h1>

<form action="/set_stream" method="get">
    <label>Camera:
        <select name="url" class="camera-list">
        {% if cameras %}
            {% for camera in cameras %}
                <option value="{{ camera.url|e }}" {% if camera.url == current_url %}selected{% endif %}>
                    {{ camera.name }} — {{ camera.url }}
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

<h2>Camera Settings</h2>
{% if cameras %}
    {% for camera in cameras %}
    <div class="camera-card" data-url="{{ camera.url|e }}">
        <div>
            <strong>{{ camera.name }}</strong>
            <span class="ptz-status" id="ptz-status-{{ loop.index }}"></span>
        </div>
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
            <div class="ptz-section">
                <h4>PTZ — Zoom &amp; Focus</h4>
                <div class="ptz-hint">Sliders apply to the camera when you stop moving them (~1s delay). The camera zooms fully out then in — this takes several seconds per adjustment. Click Save to persist.</div>
                <label>Zoom &nbsp;<small>Wide &#8592; &#8594; Tele</small>
                    <div class="slider-row">
                        <input type="range" name="zoom" min="0" max="1" step="0.01"
                                     value="{{ '%.2f'|format(camera.ptz.zoom) }}"
                                     oninput="this.nextElementSibling.value=parseFloat(this.value).toFixed(2);ptzSliderChange(this,{{ loop.index }})"
                                     data-camera-url="{{ camera.url|e }}">
                        <output>{{ '%.2f'|format(camera.ptz.zoom) }}</output>
                    </div>
                </label>
                <label>Focus &nbsp;<small>Near &#8592; &#8594; Far</small>
                    <div class="slider-row">
                        <input type="range" name="focus" min="0" max="1" step="0.01"
                                     value="{{ '%.2f'|format(camera.ptz.focus) }}"
                                     oninput="this.nextElementSibling.value=parseFloat(this.value).toFixed(2);ptzSliderChange(this,{{ loop.index }})"
                                     data-camera-url="{{ camera.url|e }}">
                        <output>{{ '%.2f'|format(camera.ptz.focus) }}</output>
                    </div>
                </label>
            </div>
            <button type="submit" name="action" value="save">Save</button>
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

<script>
const _ptzTimers = {};
function ptzSliderChange(slider, idx) {
        const card = slider.closest('.camera-card');
        const url = card.dataset.url;
        clearTimeout(_ptzTimers[url]);
        _ptzTimers[url] = setTimeout(function() {
                const zoom  = parseFloat(card.querySelector('[name="zoom"]').value);
                const focus = parseFloat(card.querySelector('[name="focus"]').value);
                const statusEl = document.getElementById('ptz-status-' + idx);
                if (statusEl) { statusEl.textContent = ' Applying\u2026'; statusEl.style.color = '#a60'; }
                fetch('/ptz_live', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({url: url, zoom: zoom, focus: focus, changed: slider.name})
                }).then(function(r){ return r.json(); }).then(function(d) {
                        if (statusEl) {
                                statusEl.textContent = d.ok ? ' \u2713 Applied' : ' \u2717 ' + d.msg;
                                statusEl.style.color = d.ok ? 'green' : '#c00';
                                setTimeout(function(){ if (statusEl) statusEl.textContent = ''; }, 4000);
                        }
                }).catch(function() {
                        if (statusEl) { statusEl.textContent = ' \u2717 Request failed'; statusEl.style.color = '#c00'; }
                });
        }, 1000);
}
</script>
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
        self.app.route("/ptz_live", methods=["POST"])(self.ptz_live)
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
        return max(0.0, min(1.0, num))

    def _find_camera_by_url(self, url):
        for camera in self.camera_choices:
            if camera.get("url") == url:
                return camera
        return None

    def _apply_ptz(self, camera, zoom, focus, **kwargs):
        host = camera.get("host", "")
        name = camera.get("name", host)
        apply_zoom  = kwargs.get("apply_zoom",  True)
        apply_focus = kwargs.get("apply_focus", True)
        print(f"PTZ: _apply_ptz camera={name!r} host={host!r} zoom={zoom} focus={focus} apply_zoom={apply_zoom} apply_focus={apply_focus} fn_set={self.apply_ptz_fn is not None}")
        if not self.apply_ptz_fn:
            print("PTZ: no apply_ptz_fn configured, skipping")
            return False, "PTZ control is not configured"
        return self.apply_ptz_fn(camera, zoom, focus, **kwargs)

    def ptz_live(self):
        """AJAX endpoint: apply PTZ from slider interaction. Returns JSON."""
        data = request.get_json(silent=True) or {}
        url = (data.get("url") or "").strip()
        zoom  = self._clamp_unit(data.get("zoom",  0.0))
        focus = self._clamp_unit(data.get("focus", 0.0))
        # Only run the axis that the user actually moved to avoid cross-axis interference.
        changed = (data.get("changed") or "both").strip().lower()
        apply_zoom  = changed in ("zoom",  "both")
        apply_focus = changed in ("focus", "both")
        camera = self._find_camera_by_url(url)
        if not camera:
            return {"ok": False, "msg": "Camera not found"}, 404
        camera["ptz"]["zoom"]  = zoom
        camera["ptz"]["focus"] = focus
        ok, msg = self._apply_ptz(camera, zoom, focus,
                                  apply_zoom=apply_zoom, apply_focus=apply_focus)
        print(f"PTZ live slider ({changed}): {'ok' if ok else 'failed'} {msg}")
        return {"ok": ok, "msg": msg}
    
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
