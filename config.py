"""Configuration settings for the kiosk application."""
import os

# Directories
UPLOAD_FOLDER = os.path.expanduser("~/kiosk_images")

# Network settings
RTSP_URL = ""
RTSP_DEFAULT_PATH = "/live/0/MAIN"
FLASK_PORT = 8080
ENABLE_ZEROCONF_DISCOVERY = True
ZEROCONF_DISCOVERY_TIMEOUT = 8.0
ZEROCONF_SERVICE_TYPES = [
	"_rtsp._tcp.local.",
	"_onvif._tcp.local.",
	"_camera._tcp.local.",
	"_axis-video._tcp.local.",
]
ENABLE_DISCOVERY_FALLBACKS = True
ONVIF_FALLBACK_TIMEOUT = 3.0
RTSP_SCAN_FALLBACK_TIMEOUT = 4.0
RTSP_SCAN_SUBNET = ""
RTSP_SCAN_SUBNETS = ["192.168.100.0/24", "192.168.10.0/24"]
RTSP_SCAN_PORTS = [554, 8554]
RTSP_SCAN_MAX_HOSTS = 254
RTSP_SCAN_INTERFACE_HINT = "eth0"
RTSP_SCAN_REQUIRE_RTSP_HANDSHAKE = True
RTSP_SCAN_CONNECT_TIMEOUT = 0.0
RTSP_SCAN_RETRY_WITHOUT_HANDSHAKE = True
RTSP_SCAN_PATH_CANDIDATES = [
	"/live/0/MAIN",
	"/Streaming/Channels/101",
	"/stream1",
	"/cam/realmonitor?channel=1&subtype=0",
	"/h264Preview_01_main",
	"/h264/ch1/main/av_stream",
	"/live/ch00_0",
	"/11",
]

# Display settings
FADE_DURATION = 1.0    # seconds
FADE_STEPS = 5

# Initialize upload folder
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
