"""Main entry point for the kiosk application."""
import sys
import signal
import threading
import tkinter as tk

import config
from camera_discovery import discover_rtsp_url
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
    boot_rtsp_url = config.RTSP_URL
    if config.ENABLE_ZEROCONF_DISCOVERY:
        discovered_url = discover_rtsp_url(
            config.ZEROCONF_SERVICE_TYPES,
            timeout_seconds=config.ZEROCONF_DISCOVERY_TIMEOUT,
        )
        if discovered_url:
            boot_rtsp_url = discovered_url
            print(f"Discovered RTSP camera via zeroconf: {boot_rtsp_url}")
        else:
            print("No zeroconf RTSP camera discovered; using configured RTSP_URL")

    # Create Tkinter root window
    root = tk.Tk()
    
    # Initialize VLC player
    vlc_player = VLCPlayer()
    
    # Initialize GUI
    gui = KioskGUI(root, vlc_player)
    
    # Initialize web interface
    web = WebInterface(gui, vlc_player, shutdown, initial_rtsp_url=boot_rtsp_url)
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    # Start Flask in background thread
    flask_thread = threading.Thread(target=web.run, daemon=True)
    flask_thread.start()
    
    # Embed VLC and start streaming
    root.after(100, lambda: (
        gui.embed_vlc(),
        vlc_player.start_media(boot_rtsp_url)
    ))
    
    # Start Tkinter main loop
    root.mainloop()
