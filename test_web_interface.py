"""Unit tests for web interface module."""
import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os
from io import BytesIO


class TestWebInterface(unittest.TestCase):
    """Test Flask web interface functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Mock Flask
        self.mock_flask = MagicMock()
        
        self.flask_patcher = patch.dict('sys.modules', {'flask': self.mock_flask})
        self.flask_patcher.start()
        
        # Mock dependencies
        self.mock_gui = MagicMock()
        self.mock_vlc_player = MagicMock()
        self.mock_shutdown = MagicMock()
        
        # Import after patching
        import config
        self.config = config
        
        # Create temporary upload folder for testing
        self.temp_dir = tempfile.mkdtemp()
        self.original_upload_folder = config.UPLOAD_FOLDER
        config.UPLOAD_FOLDER = self.temp_dir
    
    def tearDown(self):
        """Clean up patches and temp files."""
        self.flask_patcher.stop()
        # Clean up temp directory
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        self.config.UPLOAD_FOLDER = self.original_upload_folder
    
    def _create_web_interface(self):
        """Helper to create web interface instance."""
        from web_interface import WebInterface
        return WebInterface(self.mock_gui, self.mock_vlc_player, self.mock_shutdown)
    
    def test_web_interface_initialization(self):
        """Test web interface initializes correctly."""
        web = self._create_web_interface()
        
        self.assertEqual(web.gui, self.mock_gui)
        self.assertEqual(web.vlc_player, self.mock_vlc_player)
        self.assertEqual(web.shutdown_callback, self.mock_shutdown)
        self.assertIsNotNone(web.rtsp_url)
    
    def test_index_lists_images(self):
        """Test index page lists uploaded images."""
        # Create some test image files
        test_files = ['test1.jpg', 'test2.png', 'test3.gif']
        for filename in test_files:
            open(os.path.join(self.temp_dir, filename), 'w').close()
        
        # Also create a non-image file
        open(os.path.join(self.temp_dir, 'readme.txt'), 'w').close()
        
        with patch('web_interface.render_template_string') as mock_render:
            web = self._create_web_interface()
            web.index()
            
            # Check that render was called
            mock_render.assert_called_once()
            call_args = mock_render.call_args
            
            # Check that only image files are listed
            files_arg = call_args[1]['files']
            self.assertEqual(len(files_arg), 3)
            self.assertIn('test1.jpg', files_arg)
            self.assertIn('test2.png', files_arg)
            self.assertIn('test3.gif', files_arg)
            self.assertNotIn('readme.txt', files_arg)
    
    def test_show_image_calls_gui(self):
        """Test show_image endpoint calls GUI."""
        test_filename = 'test.jpg'
        test_path = os.path.join(self.temp_dir, test_filename)
        open(test_path, 'w').close()
        
        with patch('web_interface.redirect') as mock_redirect:
            web = self._create_web_interface()
            web.show_image(test_filename)
            
            self.mock_gui.show_image.assert_called_once()
            call_args = self.mock_gui.show_image.call_args[0][0]
            self.assertEqual(call_args, test_path)
    
    def test_show_image_not_found(self):
        """Test show_image returns 404 for missing file."""
        web = self._create_web_interface()
        result = web.show_image('nonexistent.jpg')
        
        self.assertEqual(result, ("Not found", 404))
    
    def test_show_stream_calls_gui(self):
        """Test show_stream endpoint calls GUI."""
        with patch('web_interface.redirect') as mock_redirect:
            web = self._create_web_interface()
            web.show_stream()
            
            self.mock_gui.show_stream.assert_called_once()
    
    def test_delete_image_removes_file(self):
        """Test delete endpoint removes image file."""
        test_filename = 'delete_me.jpg'
        test_path = os.path.join(self.temp_dir, test_filename)
        open(test_path, 'w').close()
        
        self.assertTrue(os.path.exists(test_path))
        
        with patch('web_interface.redirect') as mock_redirect:
            web = self._create_web_interface()
            web.delete_image(test_filename)
            
            self.assertFalse(os.path.exists(test_path))
    
    def test_set_stream_updates_url(self):
        """Test set_stream updates RTSP URL."""
        new_url = "rtsp://new.example.com/stream"
        
        with patch('web_interface.request') as mock_request:
            mock_request.args.get.return_value = new_url
            
            with patch('web_interface.redirect') as mock_redirect:
                with patch('web_interface.threading.Thread') as mock_thread:
                    web = self._create_web_interface()
                    web.set_stream()
                    
                    self.assertEqual(web.rtsp_url, new_url)
                    # Should start background thread to restart player
                    mock_thread.assert_called_once()
    
    def test_set_stream_missing_url(self):
        """Test set_stream returns 400 for missing URL."""
        with patch('web_interface.request') as mock_request:
            mock_request.args.get.return_value = None
            
            web = self._create_web_interface()
            result = web.set_stream()
            
            self.assertEqual(result, ("Missing url parameter", 400))
    
    def test_kill_app_calls_shutdown(self):
        """Test kill endpoint schedules shutdown."""
        with patch('web_interface.threading.Thread') as mock_thread:
            web = self._create_web_interface()
            result = web.kill_app()
            
            # Should start background thread for shutdown
            mock_thread.assert_called_once()
            self.assertIn("Shutting down", result[0])
    
    def test_upload_saves_file(self):
        """Test upload endpoint saves uploaded file."""
        mock_file = MagicMock()
        mock_file.filename = 'uploaded.jpg'
        mock_file.save = MagicMock()
        
        with patch('web_interface.request') as mock_request:
            mock_request.files.get.return_value = mock_file
            
            with patch('web_interface.redirect') as mock_redirect:
                web = self._create_web_interface()
                web.upload()
                
                # Check file.save was called
                mock_file.save.assert_called_once()
                save_path = mock_file.save.call_args[0][0]
                self.assertIn('uploaded.jpg', save_path)
    
    def test_upload_no_file(self):
        """Test upload returns 400 when no file provided."""
        with patch('web_interface.request') as mock_request:
            mock_request.files.get.return_value = None
            
            web = self._create_web_interface()
            result = web.upload()
            
            self.assertEqual(result, ("No file uploaded", 400))
    
    def test_serve_image(self):
        """Test serve_image endpoint."""
        test_filename = 'serve_test.jpg'
        
        with patch('web_interface.send_from_directory') as mock_send:
            web = self._create_web_interface()
            web.serve_image(test_filename)
            
            mock_send.assert_called_once_with(self.temp_dir, test_filename)
    
    def test_url_decoding(self):
        """Test that URL-encoded filenames are decoded."""
        encoded_name = 'my%20image.jpg'
        decoded_name = 'my image.jpg'
        test_path = os.path.join(self.temp_dir, decoded_name)
        open(test_path, 'w').close()
        
        with patch('web_interface.redirect') as mock_redirect:
            web = self._create_web_interface()
            web.show_image(encoded_name)
            
            # Should decode and find the file
            self.mock_gui.show_image.assert_called_once()


if __name__ == "__main__":
    unittest.main()
