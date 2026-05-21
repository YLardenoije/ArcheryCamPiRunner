"""Configuration settings for the kiosk application."""
import os

# Directories
UPLOAD_FOLDER = os.path.expanduser("~/kiosk_images")

# Network settings
RTSP_URL = ""
FLASK_PORT = 8080
ENABLE_ZEROCONF_DISCOVERY = True
ZEROCONF_DISCOVERY_TIMEOUT = 8.0
ZEROCONF_SERVICE_TYPES = [
	"_rtsp._tcp.local.",
	"_onvif._tcp.local.",
	"_camera._tcp.local.",
	"_axis-video._tcp.local.",
]

# Display settings
FADE_DURATION = 1.0    # seconds
FADE_STEPS = 5

# Initialize upload folder
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
