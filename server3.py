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


def discover_camera_after_launch(gui, web, vlc_player):
    """Discover a camera in the background after the kiosk has launched."""
    if not config.ENABLE_ZEROCONF_DISCOVERY:
        print("Zeroconf discovery disabled; using configured RTSP_URL")
        return

    discovered_url = discover_rtsp_url(
        config.ZEROCONF_SERVICE_TYPES,
        timeout_seconds=config.ZEROCONF_DISCOVERY_TIMEOUT,
    )
    if not discovered_url:
        print("No zeroconf RTSP camera discovered after launch; keeping configured RTSP_URL")
        return

    print(f"Discovered RTSP camera via zeroconf after launch: {discovered_url}")
    web.rtsp_url = discovered_url
    gui.show_stream(discovered_url)


if __name__ == "__main__":
    # Create Tkinter root window
    root = tk.Tk()
    
    # Initialize VLC player
    vlc_player = VLCPlayer()
    
    # Initialize GUI
    gui = KioskGUI(root, vlc_player)
    
    # Initialize web interface
    web = WebInterface(gui, vlc_player, shutdown, initial_rtsp_url=config.RTSP_URL)
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    # Start Flask in background thread
    flask_thread = threading.Thread(target=web.run, daemon=True)
    flask_thread.start()
    
    # Embed VLC and start streaming
    root.after(100, lambda: (
        gui.embed_vlc(),
        vlc_player.start_media(config.RTSP_URL)
    ))

    # Start zeroconf discovery after the kiosk is already live.
    threading.Thread(
        target=discover_camera_after_launch,
        args=(gui, web, vlc_player),
        daemon=True,
    ).start()
    
    # Start Tkinter main loop
    root.mainloop()
