"""Integration tests for the kiosk application."""
import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os


class TestIntegration(unittest.TestCase):
    """Test integration between modules."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create temporary upload folder
        self.temp_dir = tempfile.mkdtemp()
        
        # Mock external dependencies
        self.mock_tk = MagicMock()
        self.mock_vlc = MagicMock()
        self.mock_pil = MagicMock()
        self.mock_flask = MagicMock()
        
        self.patchers = [
            patch.dict('sys.modules', {
                'tkinter': self.mock_tk,
                'vlc': self.mock_vlc,
                'PIL': self.mock_pil,
                'PIL.Image': MagicMock(),
                'PIL.ImageTk': MagicMock(),
                'flask': self.mock_flask
            }),
            patch('config.UPLOAD_FOLDER', self.temp_dir)
        ]
        
        for patcher in self.patchers:
            patcher.start()
    
    def tearDown(self):
        """Clean up patches and temp files."""
        for patcher in self.patchers:
            patcher.stop()
        
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_vlc_player_gui_integration(self):
        """Test VLC player integrates with GUI."""
        from vlc_player import VLCPlayer
        from gui import KioskGUI
        
        mock_root = MagicMock()
        mock_root.winfo_screenwidth.return_value = 1920
        mock_root.winfo_screenheight.return_value = 1080
        
        # Set up VLC mocks
        mock_instance = MagicMock()
        mock_player = MagicMock()
        self.mock_vlc.Instance.return_value = mock_instance
        mock_instance.media_player_new.return_value = mock_player
        
        vlc_player = VLCPlayer()
        gui = KioskGUI(mock_root, vlc_player)
        
        # Test embedding
        container_mock = MagicMock()
        container_mock.winfo_id.return_value = 12345
        gui.video_container = container_mock
        
        gui.embed_vlc()
        
        # VLC player should have been embedded
        mock_player.set_xwindow.assert_called_with(12345)
    
    def test_web_interface_gui_integration(self):
        """Test web interface integrates with GUI."""
        from web_interface import WebInterface
        
        mock_gui = MagicMock()
        mock_vlc_player = MagicMock()
        mock_shutdown = MagicMock()
        
        web = WebInterface(mock_gui, mock_vlc_player, mock_shutdown)
        
        # Create test image
        test_file = os.path.join(self.temp_dir, 'test.jpg')
        open(test_file, 'w').close()
        
        # Test showing image through web interface
        with patch('web_interface.redirect'):
            web.show_image('test.jpg')
        
        # GUI should have been called
        mock_gui.show_image.assert_called_once()
        call_path = mock_gui.show_image.call_args[0][0]
        self.assertEqual(call_path, test_file)
    
    def test_web_interface_vlc_integration(self):
        """Test web interface integrates with VLC player."""
        from web_interface import WebInterface
        
        mock_gui = MagicMock()
        mock_vlc_player = MagicMock()
        mock_shutdown = MagicMock()
        
        web = WebInterface(mock_gui, mock_vlc_player, mock_shutdown)
        
        # Test stream URL update
        new_url = "rtsp://new.example.com/test"
        
        with patch('web_interface.request') as mock_request:
            mock_request.args.get.return_value = new_url
            
            with patch('web_interface.redirect'):
                with patch('web_interface.threading.Thread') as mock_thread:
                    # Capture the thread target
                    def capture_thread(target, daemon):
                        # Execute the target immediately for testing
                        with patch('time.sleep'):
                            target()
                        return MagicMock()
                    
                    mock_thread.side_effect = capture_thread
                    
                    web.set_stream()
        
        # VLC player should have been stopped
        mock_vlc_player.stop.assert_called()
    
    def test_config_used_by_modules(self):
        """Test that config values are used by other modules."""
        import config
        from web_interface import WebInterface
        
        mock_gui = MagicMock()
        mock_vlc_player = MagicMock()
        mock_shutdown = MagicMock()
        
        web = WebInterface(mock_gui, mock_vlc_player, mock_shutdown)
        
        # Web interface should use config values
        self.assertEqual(web.rtsp_url, config.RTSP_URL)
    
    def test_shutdown_cleanup(self):
        """Test that shutdown properly cleans up resources."""
        from vlc_player import VLCPlayer
        
        # Set up VLC mocks
        mock_instance = MagicMock()
        mock_player = MagicMock()
        self.mock_vlc.Instance.return_value = mock_instance
        mock_instance.media_player_new.return_value = mock_player
        
        vlc_player = VLCPlayer()
        
        # Stop should clean up
        vlc_player.stop()
        mock_player.stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
