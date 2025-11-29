"""Configuration settings for the kiosk application."""
import os

# Directories
UPLOAD_FOLDER = os.path.expanduser("~/kiosk_images")
PTZ_PRESETS_FILE = os.path.expanduser("~/kiosk_config/ptz_presets.json")

# Network settings
RTSP_URL = "rtsp://192.168.10.31:554/live/0/MAIN"
# RTSP_URL = "rtsp://admin:admin@192.168.100.27:554/11"
FLASK_PORT = 8080

# PTZ Camera settings (ONVIF)
PTZ_CAMERA_HOST = None  # Set to camera IP to enable PTZ
PTZ_CAMERA_PORT = 80
PTZ_CAMERA_USERNAME = "admin"
PTZ_CAMERA_PASSWORD = "admin"

# Display settings
FADE_DURATION = 1.0    # seconds
FADE_STEPS = 5

# Initialize folders
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.dirname(PTZ_PRESETS_FILE), exist_ok=True)
