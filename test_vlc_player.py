"""Unit tests for VLC player module."""
import unittest
from unittest.mock import Mock, patch, MagicMock, call
import time


class TestVLCPlayer(unittest.TestCase):
    """Test VLC player functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Mock VLC module before importing
        self.mock_vlc = MagicMock()
        self.mock_instance = MagicMock()
        self.mock_player = MagicMock()
        self.mock_media = MagicMock()
        
        self.mock_vlc.Instance.return_value = self.mock_instance
        self.mock_instance.media_player_new.return_value = self.mock_player
        self.mock_instance.media_new.return_value = self.mock_media
        
        self.patcher = patch.dict('sys.modules', {'vlc': self.mock_vlc})
        self.patcher.start()
        
        # Import after patching
        from vlc_player import VLCPlayer
        self.VLCPlayer = VLCPlayer
    
    def tearDown(self):
        """Clean up patches."""
        self.patcher.stop()
    
    def test_player_initialization(self):
        """Test that player initializes correctly."""
        player = self.VLCPlayer()
        self.assertIsNotNone(player._instance)
        self.assertIsNotNone(player._player)
        self.assertIsInstance(player._chosen_args, list)
    
    def test_player_creation_with_args(self):
        """Test player creation with specific arguments."""
        player = self.VLCPlayer()
        self.mock_vlc.Instance.assert_called()
    
    def test_embed_to_window(self):
        """Test embedding player to window."""
        player = self.VLCPlayer()
        window_id = 12345
        player.embed_to_window(window_id)
        # Should try set_xwindow first
        self.mock_player.set_xwindow.assert_called_with(window_id)
    
    def test_embed_to_window_fallback(self):
        """Test embedding falls back to set_hwnd if set_xwindow fails."""
        player = self.VLCPlayer()
        self.mock_player.set_xwindow.side_effect = Exception("X11 not available")
        window_id = 12345
        player.embed_to_window(window_id)
        self.mock_player.set_hwnd.assert_called_with(window_id)
    
    @patch('time.sleep')
    def test_start_media(self, mock_sleep):
        """Test starting media playback."""
        player = self.VLCPlayer()
        test_url = "rtsp://test.example.com/stream"
        
        player.start_media(test_url)
        
        self.mock_instance.media_new.assert_called_with(test_url)
        self.mock_player.set_media.assert_called_with(self.mock_media)
        self.mock_player.play.assert_called_once()
        self.mock_player.audio_set_mute.assert_called_with(True)
    
    def test_stop_player(self):
        """Test stopping the player."""
        player = self.VLCPlayer()
        player.stop()
        self.mock_player.stop.assert_called_once()
    
    def test_detach_window_x11(self):
        """Test detaching window on X11."""
        player = self.VLCPlayer()
        player.detach_window()
        self.mock_player.set_xwindow.assert_called_with(0)
    
    def test_detach_window_fallback(self):
        """Test detaching window falls back to stop."""
        player = self.VLCPlayer()
        self.mock_player.set_xwindow.side_effect = Exception("X11 not available")
        self.mock_player.set_hwnd.side_effect = Exception("HWND not available")
        
        player.detach_window()
        self.mock_player.stop.assert_called()
    
    def test_player_property(self):
        """Test player property accessor."""
        player = self.VLCPlayer()
        self.assertEqual(player.player, self.mock_player)
    
    def test_instance_creation_fallback(self):
        """Test instance creation with fallback to default."""
        # Make all specific args fail
        self.mock_vlc.Instance.side_effect = [
            Exception("Failed 1"),
            Exception("Failed 2"),
            Exception("Failed 3"),
            self.mock_instance  # Default constructor succeeds
        ]
        
        player = self.VLCPlayer()
        self.assertIsNotNone(player._instance)


if __name__ == "__main__":
    unittest.main()
