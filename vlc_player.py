"""VLC player management."""
import time
import vlc


class VLCPlayer:
    """Manages VLC instance and media player."""
    
    def __init__(self):
        self._instance = None
        self._player = None
        self._chosen_args = []
        self._create_instance()
    
    def _create_instance(self):
        """Create a VLC instance with fallbacks."""
        candidates = [
            ["--no-audio", "--rtsp-tcp", "--no-osd", "--no-sub-autodetect-file", "--avcodec-hw=drm"],
            ["--no-audio", "--rtsp-tcp", "--no-osd", "--no-sub-autodetect-file"],
            ["--no-audio", "--rtsp-tcp", "--no-osd", "--no-sub-autodetect-file", "--vout=gl"],
        ]
        last_exc = None
        for args in candidates:
            try:
                inst = vlc.Instance(*args)
                print("VLC: created instance with args:", args)
                self._instance = inst
                self._chosen_args = args
                self._player = inst.media_player_new()
                return
            except Exception as e:
                print("VLC: instance failed with args", args, "error:", e)
                last_exc = e
        
        # Final fallback: try default constructor
        try:
            inst = vlc.Instance()
            print("VLC: created default instance")
            self._instance = inst
            self._chosen_args = []
            self._player = inst.media_player_new()
        except Exception as e:
            print("VLC: failed to create any instance:", e)
            raise last_exc or e
    
    def embed_to_window(self, window_id):
        """Attach VLC video to Tk window XID (works on X11)."""
        try:
            # X11
            self._player.set_xwindow(window_id)
        except Exception:
            try:
                # macOS / Windows variants (not expected on Pi)
                self._player.set_hwnd(window_id)
            except Exception:
                pass
    
    def start_media(self, url):
        """Start or restart VLC media with new URL."""
        print("VLC: starting media", url)
        media = self._instance.media_new(url)
        self._player.set_media(media)
        self._player.play()
        # Give time to start and print state for diagnostics
        time.sleep(0.5)
        try:
            state = self._player.get_state()
            print("VLC: player state after play() ->", state)
        except Exception:
            pass
        # Keep audio off
        try:
            self._player.audio_set_mute(True)
        except Exception:
            pass
    
    def stop(self):
        """Stop the player."""
        try:
            self._player.stop()
            print("VLC: stopped player")
        except Exception as e:
            print("VLC: failed to stop:", e)
    
    def detach_window(self):
        """Detach VLC's video output from the window."""
        try:
            self._player.set_xwindow(0)
            print("VLC: detached X window (set_xwindow(0))")
            return
        except Exception:
            pass
        try:
            self._player.set_hwnd(0)
            print("VLC: detached HWND (set_hwnd(0))")
            return
        except Exception:
            pass
        try:
            # Fallback: stop the player to remove any overlay
            self.stop()
            print("VLC: stopped player as fallback to remove overlay")
        except Exception as e:
            print("VLC: failed to detach or stop player:", e)
    
    @property
    def player(self):
        """Get the media player instance."""
        return self._player
