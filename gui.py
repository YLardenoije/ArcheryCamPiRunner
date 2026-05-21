"""Tkinter GUI management for the kiosk display."""
import threading
import tkinter as tk
from PIL import Image, ImageTk


class KioskGUI:
    """Manages the Tkinter kiosk window and display elements."""
    
    def __init__(self, root, vlc_player):
        self.root = root
        self.vlc_player = vlc_player
        self._gui_lock = threading.Lock()
        self._showing_image = False
        self._current_image_name = None
        
        # Keep references to PhotoImage objects to prevent GC
        self._image_tk_ref = None
        self._overlay_tk_ref = None
        self._black_bg = None
        
        # Setup window
        self._setup_window()
        
        # Get screen dimensions
        self.screen_w = root.winfo_screenwidth()
        self.screen_h = root.winfo_screenheight()
        
        # Create UI elements
        self._create_widgets()
    
    def _setup_window(self):
        """Configure the root window for kiosk mode."""
        self.root.title("Kiosk")
        self.root.attributes("-fullscreen", True)
        self.root.overrideredirect(True)  # Remove window decorations
        self.root.geometry(f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}+0+0")
        self.root.configure(background="black")
        self.root.config(cursor="none")  # Hide mouse cursor
        self.root.focus_set()  # Ensure window has focus
    
    def _create_widgets(self):
        """Create container frames and widgets."""
        # Video container
        self.video_container = tk.Frame(self.root, bg="black")
        self.video_container.place(relx=0, rely=0, relwidth=1, relheight=1)
        
        # Image label that sits on top of video
        self.image_label = tk.Label(self.root, bg="black")
        self.image_label.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.image_label.lower()  # Start below overlay (so video visible)
        
        # Black overlay used for fading
        self.overlay_label = tk.Label(self.root, bg="black")
        self.overlay_label.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.overlay_label.lower()  # Start below image_label
    
    def get_video_container_id(self):
        """Get the window ID for embedding VLC."""
        self.root.update_idletasks()
        return self.video_container.winfo_id()
    
    def _load_and_scale_image(self, path):
        """Load image from path and scale to fit screen (preserve aspect)."""
        img = Image.open(path)
        # Convert to RGB for faster processing (no alpha channel)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        iw, ih = img.size
        sw, sh = self.screen_w, self.screen_h
        # Scale preserving aspect
        scale = min(sw / iw, sh / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        # Use BILINEAR for faster scaling on Pi (LANCZOS is slower but higher quality)
        img = img.resize((nw, nh), Image.BILINEAR)
        
        # Reuse black background if size matches
        if self._black_bg is None or self._black_bg.size != (sw, sh):
            self._black_bg = Image.new("RGB", (sw, sh), (0, 0, 0))
        else:
            # Fill with black
            self._black_bg.paste((0, 0, 0), (0, 0, sw, sh))
        
        # Center image on black background
        x = (sw - nw) // 2
        y = (sh - nh) // 2
        self._black_bg.paste(img, (x, y))
        return self._black_bg
    
    def _set_image_tk(self, img_pil):
        """Set image_label to the given PIL image."""
        tkimg = ImageTk.PhotoImage(img_pil)
        self._image_tk_ref = tkimg
        self.image_label.config(image=tkimg)
        self.image_label.lift()
    
    def _fade_and_show_image(self, path):
        """Show image immediately (no fade)."""
        print("GUI: showing image immediately:", path)
        self._showing_image = True
        # Stop player first to remove overlay quickly
        self.vlc_player.stop()
        try:
            print(f"GUI: loading image from {path}")
            pil = self._load_and_scale_image(path)
            print(f"GUI: image loaded, size={pil.size}, setting to Tk...")
            self._set_image_tk(pil)
            print("GUI: image set to Tk successfully")
        except Exception as e:
            print("Image load error:", e)
            import traceback
            traceback.print_exc()
            return
        # Bring image_label on top
        self.image_label.lift()
        self.overlay_label.lower()
        print("GUI: image displayed, overlay lowered")
    
    def _fade_and_show_stream(self, rtsp_url):
        """Show stream immediately (no fade)."""
        print("GUI: switching back to stream")
        self._showing_image = False
        # Remove image
        self.image_label.config(image="")
        self.image_label.lower()
        self.overlay_label.lower()
        # Restart VLC to restore stream (since we stopped it)
        try:
            win_id = self.get_video_container_id()
            self.vlc_player.embed_to_window(win_id)
            self.vlc_player.start_media(rtsp_url)
            print("GUI: stream restarted")
        except Exception as e:
            print("GUI: failed to restart VLC:", e)
        print("GUI: stream should be visible now")
    
    def show_image(self, path):
        """Schedule showing an image (thread-safe)."""
        with self._gui_lock:
            self.root.after(0, lambda: self._fade_and_show_image(path))
    
    def show_stream(self, rtsp_url):
        """Schedule showing the stream (thread-safe)."""
        with self._gui_lock:
            self.root.after(0, lambda: self._fade_and_show_stream(rtsp_url))
    
    def embed_vlc(self):
        """Embed VLC player into the video container."""
        win_id = self.get_video_container_id()
        self.vlc_player.embed_to_window(win_id)

    @property
    def is_showing_image(self):
        """Return True when the GUI is currently showing a static image."""
        return bool(self._showing_image)
