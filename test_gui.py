"""Unit tests for GUI module."""
import unittest
from unittest.mock import Mock, patch, MagicMock, call
import tempfile
import os
from io import BytesIO


class TestKioskGUI(unittest.TestCase):
    """Test Kiosk GUI functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Mock tkinter
        self.mock_tk = MagicMock()
        self.mock_root = MagicMock()
        self.mock_root.winfo_screenwidth.return_value = 1920
        self.mock_root.winfo_screenheight.return_value = 1080
        self.mock_root.winfo_id.return_value = 12345
        
        # Mock PIL
        self.mock_pil = MagicMock()
        self.mock_image = MagicMock()
        self.mock_image_tk = MagicMock()
        
        self.tk_patcher = patch.dict('sys.modules', {
            'tkinter': self.mock_tk,
            'PIL': self.mock_pil,
            'PIL.Image': self.mock_image,
            'PIL.ImageTk': self.mock_image_tk
        })
        self.tk_patcher.start()
        
        # Mock VLC player
        self.mock_vlc_player = MagicMock()
        
        # Import after patching
        from gui import KioskGUI
        self.KioskGUI = KioskGUI
    
    def tearDown(self):
        """Clean up patches."""
        self.tk_patcher.stop()
    
    def test_gui_initialization(self):
        """Test GUI initializes correctly."""
        gui = self.KioskGUI(self.mock_root, self.mock_vlc_player)
        
        self.assertEqual(gui.root, self.mock_root)
        self.assertEqual(gui.vlc_player, self.mock_vlc_player)
        self.assertEqual(gui.screen_w, 1920)
        self.assertEqual(gui.screen_h, 1080)
        self.assertFalse(gui._showing_image)
    
    def test_window_setup(self):
        """Test window is configured for kiosk mode."""
        gui = self.KioskGUI(self.mock_root, self.mock_vlc_player)
        
        self.mock_root.title.assert_called_with("Kiosk")
        self.mock_root.attributes.assert_called_with("-fullscreen", True)
        self.mock_root.overrideredirect.assert_called_with(True)
        self.mock_root.configure.assert_called_with(background="black")
        self.mock_root.config.assert_called()
    
    def test_get_video_container_id(self):
        """Test getting video container window ID."""
        gui = self.KioskGUI(self.mock_root, self.mock_vlc_player)
        container_mock = MagicMock()
        container_mock.winfo_id.return_value = 54321
        gui.video_container = container_mock
        
        window_id = gui.get_video_container_id()
        
        self.assertEqual(window_id, 54321)
        self.mock_root.update_idletasks.assert_called()
    
    def test_embed_vlc(self):
        """Test embedding VLC player."""
        gui = self.KioskGUI(self.mock_root, self.mock_vlc_player)
        container_mock = MagicMock()
        container_mock.winfo_id.return_value = 99999
        gui.video_container = container_mock
        
        gui.embed_vlc()
        
        self.mock_vlc_player.embed_to_window.assert_called_with(99999)
    
    @patch('os.path.exists')
    def test_show_image_schedules_display(self, mock_exists):
        """Test showing image schedules GUI update."""
        mock_exists.return_value = True
        gui = self.KioskGUI(self.mock_root, self.mock_vlc_player)
        test_path = "/tmp/test.jpg"
        
        gui.show_image(test_path)
        
        # Should schedule with root.after
        self.mock_root.after.assert_called()
        call_args = self.mock_root.after.call_args
        self.assertEqual(call_args[0][0], 0)  # Immediate scheduling
    
    def test_show_stream_schedules_display(self):
        """Test showing stream schedules GUI update."""
        gui = self.KioskGUI(self.mock_root, self.mock_vlc_player)
        test_url = "rtsp://test.example.com/stream"
        
        gui.show_stream(test_url)
        
        # Should schedule with root.after
        self.mock_root.after.assert_called()
        call_args = self.mock_root.after.call_args
        self.assertEqual(call_args[0][0], 0)  # Immediate scheduling
    
    @patch('gui.Image')
    def test_load_and_scale_image_aspect_ratio(self, mock_pil_image):
        """Test image scaling preserves aspect ratio."""
        # Mock PIL Image operations
        mock_img = MagicMock()
        mock_img.mode = 'RGB'
        mock_img.size = (800, 600)  # 4:3 aspect ratio
        mock_img.convert.return_value = mock_img
        
        mock_resized = MagicMock()
        mock_resized.size = (1440, 1080)
        mock_img.resize.return_value = mock_resized
        
        mock_black_bg = MagicMock()
        mock_black_bg.size = (1920, 1080)
        
        mock_pil_image.open.return_value = mock_img
        mock_pil_image.new.return_value = mock_black_bg
        
        gui = self.KioskGUI(self.mock_root, self.mock_vlc_player)
        result = gui._load_and_scale_image('/fake/path/test.jpg')
        
        # Verify image was opened
        mock_pil_image.open.assert_called_with('/fake/path/test.jpg')
        
        # Should have called resize with appropriate dimensions
        mock_img.resize.assert_called()
        resize_args = mock_img.resize.call_args[0][0]
        
        # Check that aspect ratio is preserved (within screen bounds)
        self.assertLessEqual(resize_args[0], 1920)
        self.assertLessEqual(resize_args[1], 1080)
        
        # Verify proper scaling calculation (800x600 -> 1440x1080 to fit 1920x1080)
        self.assertEqual(resize_args, (1440, 1080))


if __name__ == "__main__":
    unittest.main()
