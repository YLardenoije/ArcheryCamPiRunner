"""Configuration settings for the kiosk application."""
import os

# Directories
UPLOAD_FOLDER = os.path.expanduser("~/kiosk_images")

# Network settings
RTSP_URL = "rtsp://192.168.10.31:554/live/0/MAIN"
# RTSP_URL = "rtsp://admin:admin@192.168.100.27:554/11"
FLASK_PORT = 8080

# Display settings
FADE_DURATION = 1.0    # seconds
FADE_STEPS = 5

# Initialize upload folder
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
