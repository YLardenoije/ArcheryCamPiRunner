"""Main entry point for the kiosk application."""
import sys
import signal
import threading
import tkinter as tk

import config
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
    # Create Tkinter root window
    root = tk.Tk()
    
    # Initialize VLC player
    vlc_player = VLCPlayer()
    
    # Initialize GUI
    gui = KioskGUI(root, vlc_player)
    
    # Initialize web interface
    web = WebInterface(gui, vlc_player, shutdown)
    
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
    
    # Start Tkinter main loop
    root.mainloop()
