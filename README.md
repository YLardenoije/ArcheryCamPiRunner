# Archery Cam Pi Runner

A Raspberry Pi kiosk application for displaying RTSP camera streams and static images, designed for archery range monitoring and displays.

## Features

- **RTSP Stream Display**: View live camera feeds from network cameras
- **Image Display**: Upload and display static images in fullscreen
- **Web Interface**: Remote control via browser on any device
- **Kiosk Mode**: Fullscreen display with no window decorations
- **Seamless Switching**: Switch between live stream and images
- **Multi-Camera Support**: Change RTSP stream URLs on the fly
- **PTZ Control**: Pan, Tilt, Zoom control for ONVIF-compatible cameras with preset management

## Requirements

### Hardware
- Raspberry Pi (tested on Pi 3/4/5)
- Display connected via HDMI
- Network connection

### Software
- Python 3.7+
- VLC media player
- Tkinter (usually pre-installed)
- Flask
- Pillow (PIL)
- python-vlc
- onvif-zeep (for PTZ control)

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/YLardenoije/ArcheryCamPiRunner.git
   cd ArcheryCamPiRunner
   ```

2. **Install system dependencies:**
   ```bash
   sudo apt-get update
   sudo apt-get install python3-pip python3-tk vlc
   ```

3. **Install Python dependencies:**
   ```bash
   pip3 install -r requirements.txt
   ```
   Or manually:
   ```bash
   pip3 install flask pillow python-vlc onvif-zeep
   ```

4. **Configure the application:**
   Edit `config.py` to set your RTSP stream URL and preferences:
   ```python
   RTSP_URL = "rtsp://your-camera-ip:554/stream"
   FLASK_PORT = 8080
   ```

5. **(Optional) Setup Network Bridge:**
   If using a USB-to-LAN adapter (eth1) to extend network connectivity, bridge it with the built-in Ethernet (eth0):
   ```bash
   chmod +x setup_bridge_persistent.sh
   sudo ./setup_bridge_persistent.sh
   ```
   This creates a persistent bridge that survives reboots, allowing both interfaces to act as one logical network connection.

## Usage

### Starting the Application

Run the main application:
```bash
python3 server3.py
```

The application will:
- Start in fullscreen kiosk mode
- Begin streaming from the configured RTSP URL
- Launch a web server on port 8080 (configurable)

### Web Interface

Access the web interface from any browser on the same network:
```
http://<raspberry-pi-ip>:8080
```

**Available Actions:**
- **Upload Images**: Upload JPG, PNG, GIF, or BMP images
- **Show Image**: Display an uploaded image in fullscreen
- **Show Stream**: Return to live camera feed
- **Delete Image**: Remove uploaded images
- **Change Stream**: Update the RTSP URL
- **PTZ Control**: Control camera pan, tilt, and zoom (ONVIF cameras)
- **PTZ Presets**: Save and recall camera positions
- **Shutdown**: Gracefully stop the application

### PTZ Control

The web interface includes PTZ (Pan-Tilt-Zoom) controls for ONVIF-compatible cameras:

1. **Configure Camera**: Enter the camera's IP address, port (usually 80 or 8080), and credentials
2. **Position Controls**: Use sliders to control pan (-1.0 to 1.0), tilt (-1.0 to 1.0), and zoom (0.0 to 1.0)
3. **Save Presets**: Save current position as a named preset for quick recall
4. **Recall Presets**: Click "Go To" on any saved preset to move the camera

Presets are stored persistently in `~/kiosk_config/ptz_presets.json`.

#### PTZ API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ptz/configure` | POST | Configure camera connection (host, port, username, password) |
| `/ptz/move` | POST | Move to absolute position (pan, tilt, zoom) |
| `/ptz/position` | GET | Get current PTZ position |
| `/ptz/presets` | GET | List all saved presets |
| `/ptz/presets` | POST | Save a new preset (name, pan, tilt, zoom) |
| `/ptz/presets/<name>` | DELETE | Delete a preset |
| `/ptz/goto/<name>` | GET | Move camera to saved preset |

### Keyboard Shortcuts

- `Ctrl+C`: Shutdown the application (when terminal is focused)

## Project Structure

```
ArcheryCamPiRunner/
├── server3.py                    # Main application entry point
├── config.py                     # Configuration settings
├── vlc_player.py                # VLC media player management
├── gui.py                       # Tkinter GUI and display logic
├── web_interface.py             # Flask web server and routes
├── ptz_controller.py            # PTZ camera control and presets
├── setup_bridge.sh              # Network bridge setup (temporary)
├── setup_bridge_persistent.sh   # Network bridge setup (persistent)
├── test_*.py                    # Unit tests
├── run_tests.py                 # Test runner
├── requirements-test.txt        # Test dependencies
└── README.md                    # This file
```

## Configuration

### `config.py` Options

| Setting | Description | Default |
|---------|-------------|---------|
| `UPLOAD_FOLDER` | Directory for uploaded images | `~/kiosk_images` |
| `PTZ_PRESETS_FILE` | JSON file for PTZ presets | `~/kiosk_config/ptz_presets.json` |
| `RTSP_URL` | Default RTSP stream URL | `rtsp://192.168.10.31:554/live/0/MAIN` |
| `FLASK_PORT` | Web interface port | `8080` |
| `PTZ_CAMERA_HOST` | PTZ camera IP address | `None` |
| `PTZ_CAMERA_PORT` | PTZ camera ONVIF port | `80` |
| `PTZ_CAMERA_USERNAME` | PTZ camera username | `admin` |
| `PTZ_CAMERA_PASSWORD` | PTZ camera password | `admin` |
| `FADE_DURATION` | Fade transition duration (seconds) | `1.0` |
| `FADE_STEPS` | Number of fade steps | `5` |

## Development

### Running Tests

Run the full test suite:
```bash
python run_tests.py
```

Run specific test modules:
```bash
python -m unittest test_config.py
python -m unittest test_vlc_player.py
python -m unittest test_gui.py
python -m unittest test_web_interface.py
python -m unittest test_integration.py
```

### Install Test Dependencies

```bash
pip3 install -r requirements-test.txt
```

### Code Coverage

```bash
coverage run run_tests.py
coverage report
coverage html  # Generate HTML report
```

## Troubleshooting

### Video Not Displaying
- Verify RTSP URL is correct and camera is accessible
- Check network connectivity to camera
- Test RTSP stream with VLC directly: `vlc <rtsp-url>`
- Review console output for VLC errors

### Black Screen After Showing Image
- Ensure the image file is a valid format (JPG, PNG, GIF, BMP)
- Check file permissions in upload folder
- Look for PIL/Pillow errors in console

### Web Interface Not Accessible
- Verify Flask server started (check console output)
- Confirm firewall allows connections on the configured port
- Check Raspberry Pi's IP address: `hostname -I`

### Performance Issues
- Reduce screen resolution if using 4K displays
- Lower RTSP stream quality settings on camera
- Close other applications to free resources
- Consider using hardware acceleration flags in `vlc_player.py`

### Network Bridge Issues
- If using USB-to-LAN adapter, verify bridge is active: `brctl show`
- Check both eth0 and eth1 are in bridge: `brctl show br0`
- Verify IP is assigned to br0, not eth0/eth1: `ip addr show`
- Test connectivity on both interfaces

## Auto-Start on Boot

To run the kiosk automatically when the Raspberry Pi boots:

1. **Create a systemd service:**
   ```bash
   sudo nano /etc/systemd/system/kiosk.service
   ```

2. **Add the following content:**
   ```ini
   [Unit]
   Description=Archery Kiosk Display
   After=network.target

   [Service]
   Environment=DISPLAY=:0
   Environment=XAUTHORITY=/home/pi/.Xauthority
   Type=simple
   User=pi
   WorkingDirectory=/home/pi/ArcheryCamPiRunner
   ExecStart=/usr/bin/python3 /home/pi/ArcheryCamPiRunner/server3.py
   Restart=on-failure
   RestartSec=10

   [Install]
   WantedBy=graphical.target
   ```

3. **Enable and start the service:**
   ```bash
   sudo systemctl enable kiosk.service
   sudo systemctl start kiosk.service
   ```

4. **Check status:**
   ```bash
   sudo systemctl status kiosk.service
   ```

## Camera Compatibility

Tested with:
- Generic RTSP cameras (H.264/H.265)
- Hikvision cameras
- Dahua cameras
- ONVIF-compatible cameras

**Supported Protocols:**
- RTSP over TCP (recommended)
- RTSP over UDP

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Run tests: `python run_tests.py`
5. Commit changes: `git commit -am 'Add my feature'`
6. Push to branch: `git push origin feature/my-feature`
7. Submit a pull request

## License

This project is provided as-is for archery range and display purposes.

## Acknowledgments

- Built with VLC for robust RTSP streaming
- Uses Flask for lightweight web interface
- Tkinter for cross-platform GUI support

## Contact

For issues and questions, please use the GitHub issue tracker.