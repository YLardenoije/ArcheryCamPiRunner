"""Main entry point for the kiosk application."""
import sys
import signal
import threading
import tkinter as tk

import config
from camera_discovery import discover_rtsp_cameras
from vlc_player import VLCPlayer
from gui import KioskGUI
from web_interface import WebInterface

def shutdown(*args):
    """Shutdown the application gracefully."""
    print("Shutting down...")
    try:
        vlc_player.stop()
    except:
        pass
    root.destroy()
    sys.exit(0)
if __name__ == "__main__":
    discovered_cameras = []
    if config.ENABLE_ZEROCONF_DISCOVERY:
        discovered_cameras = discover_rtsp_cameras(
            config.ZEROCONF_SERVICE_TYPES,
            timeout_seconds=config.ZEROCONF_DISCOVERY_TIMEOUT,
        )
        if discovered_cameras:
            print("Discovered RTSP cameras via zeroconf:")
            for camera in discovered_cameras:
                print(f" - {camera['name']}: {camera['url']}")
        else:
            print("No zeroconf RTSP cameras discovered on launch")
    else:
        print("Zeroconf discovery disabled")

    boot_rtsp_url = discovered_cameras[0]["url"] if discovered_cameras else ""

    # Create Tkinter root window
    root = tk.Tk()
    
    # Initialize VLC player
    vlc_player = VLCPlayer()
    
    # Initialize GUI
    gui = KioskGUI(root, vlc_player)
    
    # Initialize web interface
    web = WebInterface(
        gui,
        vlc_player,
        shutdown,
        initial_rtsp_url=boot_rtsp_url,
        initial_cameras=discovered_cameras,
    )
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    # Start Flask in background thread
    flask_thread = threading.Thread(target=web.run, daemon=True)
    flask_thread.start()
    
    # Embed VLC and start streaming
    def start_initial_stream():
        gui.embed_vlc()
        if boot_rtsp_url:
            vlc_player.start_media(boot_rtsp_url)
        else:
            print("No discovered stream available at launch; waiting for a camera selection")

    root.after(100, start_initial_stream)
    
    # Start Tkinter main loop
    root.mainloop()
