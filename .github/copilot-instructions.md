# Copilot Instructions for ArcheryCamPiRunner

## Project Overview
Raspberry Pi kiosk application for displaying RTSP camera streams and static images, designed for archery ranges. Built for fullscreen display with remote web control.

## Architecture

### Module Responsibilities
- **`server3.py`**: Entry point. Wires together Tkinter main loop, VLC player, GUI, Flask web server (threaded), and signal handlers
- **`vlc_player.py`**: VLC instance management with fallback args for Pi hardware acceleration (`--avcodec-hw=drm`)
- **`gui.py`**: Tkinter fullscreen kiosk window. Manages video container (for VLC embedding) and image overlay layer
- **`web_interface.py`**: Flask server for remote control. HTML templated inline (no templates folder)
- **`config.py`**: Centralized settings. Creates `UPLOAD_FOLDER` on import

### Critical Threading Model
- **Main thread**: Tkinter event loop (`root.mainloop()`)
- **Background daemon thread**: Flask server (`flask_thread`)
- **GUI updates**: MUST use `root.after()` for thread safety (see `show_image()` and `show_stream()` in `gui.py`)
- **Web route handlers**: Trigger GUI changes via `gui.show_image()` or `gui.show_stream()` which schedule updates on Tk thread

### Video Embedding Pattern
VLC player embeds into Tkinter window using X11 window ID:
1. Get container ID: `video_container.winfo_id()`
2. Attach VLC: `player.set_xwindow(window_id)`
3. Start media: `vlc_player.start_media(rtsp_url)`

When showing images, VLC is stopped to remove video overlay, then restarted when returning to stream view.

## Key Conventions

### Image Display Approach
- Images loaded with PIL, scaled to fit screen (preserving aspect ratio)
- Centered on black background canvas (`self._black_bg`)
- Uses `BILINEAR` resize (not LANCZOS) for faster performance on Pi
- Image references stored as instance variables to prevent garbage collection (Tkinter requirement)
- Fade transitions removed for simplicity (was `FADE_DURATION` and `FADE_STEPS`)

### VLC Instance Creation
`VLCPlayer._create_instance()` tries multiple arg combinations with fallbacks:
1. Hardware decode: `--avcodec-hw=drm` (Pi-specific)
2. Standard: `--no-audio --rtsp-tcp --no-osd`
3. GL output: `--vout=gl`
4. Default: no args

Always mutes audio and uses RTSP over TCP.

### File Upload Handling
Web interface accepts images via `/upload`, saves to `config.UPLOAD_FOLDER` with sanitized filename (`os.path.basename()`). Supports JPG, PNG, GIF, BMP.

## Development Workflows

### Running Tests
```bash
python run_tests.py                    # Run all tests
python -m unittest test_config.py      # Run specific module
```

### Test Patterns
- Mock external dependencies (`tkinter`, `vlc`, `PIL`, `flask`) in `setUp()` using `patch.dict('sys.modules', ...)`
- Use `tempfile.mkdtemp()` for upload folder isolation
- Integration tests verify cross-module communication (e.g., `test_web_interface_gui_integration`)

### Starting Application
```bash
python3 server3.py
```
Access web UI at `http://<pi-ip>:8080` (port configurable in `config.py`)

### Shutdown Flow
1. Signal handlers (`SIGINT`, `SIGTERM`) trigger `shutdown()`
2. Stops VLC player: `vlc_player.stop()`
3. Destroys Tkinter root: `root.destroy()`
4. Flask thread is daemon, exits automatically

## Common Gotchas

### Tkinter PhotoImage References
Must store PhotoImage objects as instance variables (`self._image_tk_ref`) or they get garbage collected, causing blank display.

### Window Manager Behavior
- `root.overrideredirect(True)`: Removes window decorations
- `root.attributes("-fullscreen", True)`: Fullscreen mode
- `root.config(cursor="none")`: Hides cursor for kiosk

### VLC State Diagnostics
After `player.play()`, check state with `player.get_state()` for debugging (logged to console).

### Z-ordering Layers
- Bottom: `video_container` (VLC video)
- Middle: `image_label` (static images)
- Top: `overlay_label` (fade effect - currently unused)

Use `.lift()` and `.lower()` to manage which layer is visible.

## Dependencies
- **VLC**: System package (`sudo apt-get install vlc`), not just python-vlc
- **Tkinter**: Pre-installed on Pi, but may need `python3-tk` package
- **Flask/Pillow/python-vlc**: Installed via `requirements.txt`

## Raspberry Pi Specifics
- Designed for X11 environment (uses `set_xwindow()`)
- Hardware decode flags optimized for Pi 3/4/5
- Target: 1920x1080 displays (handles different resolutions dynamically)
- systemd service template in README for autostart on boot
