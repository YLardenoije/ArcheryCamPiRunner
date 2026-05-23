"""Unit tests for web interface module."""
import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os
from io import BytesIO
from camera_settings import CameraSettingsStore


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

    def _create_web_interface_with_settings(self, apply_ptz_fn=None):
        """Helper to create web interface instance with persistent settings store."""
        from web_interface import WebInterface

        store_file = os.path.join(self.temp_dir, "camera_settings.json")
        settings_store = CameraSettingsStore(store_file)
        return WebInterface(
            self.mock_gui,
            self.mock_vlc_player,
            self.mock_shutdown,
            initial_cameras=[
                {
                    "name": "scan-cam",
                    "url": "rtsp://192.168.100.198:554/live/0/MAIN",
                    "host": "192.168.100.198",
                    "mac": "aa:bb:cc:dd:ee:ff",
                }
            ],
            settings_store=settings_store,
            apply_ptz_fn=apply_ptz_fn,
        )
    
    def test_web_interface_initialization(self):
        """Test web interface initializes correctly."""
        web = self._create_web_interface()
        
        self.assertEqual(web.gui, self.mock_gui)
        self.assertEqual(web.vlc_player, self.mock_vlc_player)
        self.assertEqual(web.shutdown_callback, self.mock_shutdown)
        self.assertIsNotNone(web.rtsp_url)

    def test_web_interface_uses_initial_rtsp_url(self):
        """Test web interface can start with a discovered RTSP URL."""
        from web_interface import WebInterface
        discovered_url = "rtsp://192.168.1.123:554/discovered"
        web = WebInterface(
            self.mock_gui,
            self.mock_vlc_player,
            self.mock_shutdown,
            initial_rtsp_url=discovered_url,
        )
        self.assertEqual(web.rtsp_url, discovered_url)

    def test_web_interface_initial_cameras_populates_dropdown(self):
        """Test web interface renders a discovered camera list."""
        from web_interface import WebInterface

        cameras = [
            {"name": "camera-one", "url": "rtsp://192.168.1.10:554/stream1"},
            {"name": "camera-two", "url": "rtsp://192.168.1.11:8554/stream2"},
        ]

        web = WebInterface(
            self.mock_gui,
            self.mock_vlc_player,
            self.mock_shutdown,
            initial_cameras=cameras,
        )

        with patch('web_interface.render_template_string') as mock_render:
            web.index()

        rendered_context = mock_render.call_args[1]
        self.assertEqual(rendered_context['cameras'], cameras)
        self.assertEqual(rendered_context['current_url'], "")
    
    def test_index_lists_images(self):
        """Test index page lists uploaded images."""
        # Create some test image files
        test_files = ['test1.jpg', 'test2.png', 'test3.gif', 'test4.webp', 'test5.tiff']
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
            self.assertEqual(len(files_arg), 5)
            self.assertIn('test1.jpg', files_arg)
            self.assertIn('test2.png', files_arg)
            self.assertIn('test3.gif', files_arg)
            self.assertIn('test4.webp', files_arg)
            self.assertIn('test5.tiff', files_arg)
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
            web.rtsp_url = "rtsp://192.168.1.10:554/stream1"
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

    def test_upload_rejects_unsupported_extension(self):
        """Test upload returns 400 for unsupported file extension."""
        mock_file = MagicMock()
        mock_file.filename = 'uploaded.txt'
        mock_file.save = MagicMock()

        with patch('web_interface.request') as mock_request:
            mock_request.files.get.return_value = mock_file
            web = self._create_web_interface()
            result = web.upload()

        self.assertEqual(result[1], 400)
        self.assertIn("Unsupported file type", result[0])
        mock_file.save.assert_not_called()
    
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

    def test_camera_settings_persists_when_mac_present(self):
        web = self._create_web_interface_with_settings()

        form_data = {
            "url": "rtsp://192.168.100.198:554/live/0/MAIN",
            "name": "Lane 1",
            "role": "primary",
            "zoom": "50",
            "focus": "60",
            "action": "save",
        }
        mock_form = MagicMock()
        mock_form.get.side_effect = lambda key, default=None: form_data.get(key, default)

        with patch("web_interface.request") as mock_request, patch("web_interface.redirect"):
            mock_request.form = mock_form
            web.camera_settings()

        saved = web.settings_store.get_settings("aa:bb:cc:dd:ee:ff")
        self.assertEqual(saved.get("name"), "Lane 1")
        self.assertEqual(saved.get("role"), "primary")
        self.assertEqual(saved.get("ptz", {}).get("zoom"), 0.5)
        self.assertEqual(saved.get("ptz", {}).get("focus"), 0.6)

    def test_camera_settings_apply_calls_ptz_handler(self):
        applied = {"called": False}

        def apply_fn(camera, zoom, focus):
            applied["called"] = True
            return True, "ok"

        web = self._create_web_interface_with_settings(apply_ptz_fn=apply_fn)

        form_data = {
            "url": "rtsp://192.168.100.198:554/live/0/MAIN",
            "name": "Lane 1",
            "role": "secondary",
            "zoom": "10",
            "focus": "20",
            "action": "apply",
        }
        mock_form = MagicMock()
        mock_form.get.side_effect = lambda key, default=None: form_data.get(key, default)

        with patch("web_interface.request") as mock_request, patch("web_interface.redirect"):
            mock_request.form = mock_form
            web.camera_settings()

        self.assertTrue(applied["called"])

    def test_get_primary_url_returns_configured_camera(self):
        web = self._create_web_interface_with_settings()
        web.camera_choices[0]["role"] = "primary"

        result = web.get_primary_url()
        self.assertTrue(result["ok"])
        self.assertEqual(result["role"], "primary")
        self.assertEqual(result["url"], "rtsp://192.168.100.198:554/live/0/MAIN")

    def test_get_primary_url_returns_404_when_missing(self):
        web = self._create_web_interface_with_settings()

        result = web.get_primary_url()
        self.assertEqual(result[1], 404)
        self.assertFalse(result[0]["ok"])

    def test_get_secondary_url_returns_configured_camera(self):
        web = self._create_web_interface_with_settings()
        web.camera_choices[0]["role"] = "secondary"

        result = web.get_secondary_url()
        self.assertTrue(result["ok"])
        self.assertEqual(result["role"], "secondary")
        self.assertEqual(result["url"], "rtsp://192.168.100.198:554/live/0/MAIN")

    def test_get_secondary_url_returns_404_when_missing(self):
        web = self._create_web_interface_with_settings()

        result = web.get_secondary_url()
        self.assertEqual(result[1], 404)
        self.assertFalse(result[0]["ok"])

    def test_set_stream_to_primary_camera_success(self):
        web = self._create_web_interface_with_settings()
        web.camera_choices[0]["role"] = "primary"

        with patch('web_interface.threading.Thread') as mock_thread:
            result = web.set_stream_to_primary_camera()

        self.assertTrue(result["ok"])
        self.assertEqual(result["role"], "primary")
        self.assertEqual(result["url"], "rtsp://192.168.100.198:554/live/0/MAIN")
        self.assertEqual(web.rtsp_url, "rtsp://192.168.100.198:554/live/0/MAIN")
        mock_thread.assert_called_once()

    def test_set_stream_to_primary_camera_missing(self):
        web = self._create_web_interface_with_settings()

        result = web.set_stream_to_primary_camera()
        self.assertEqual(result[1], 404)
        self.assertFalse(result[0]["ok"])

    def test_set_stream_to_secondary_camera_success(self):
        web = self._create_web_interface_with_settings()
        web.camera_choices[0]["role"] = "secondary"

        with patch('web_interface.threading.Thread') as mock_thread:
            result = web.set_stream_to_secondary_camera()

        self.assertTrue(result["ok"])
        self.assertEqual(result["role"], "secondary")
        self.assertEqual(result["url"], "rtsp://192.168.100.198:554/live/0/MAIN")
        self.assertEqual(web.rtsp_url, "rtsp://192.168.100.198:554/live/0/MAIN")
        mock_thread.assert_called_once()

    def test_set_stream_to_secondary_camera_missing(self):
        web = self._create_web_interface_with_settings()

        result = web.set_stream_to_secondary_camera()
        self.assertEqual(result[1], 404)
        self.assertFalse(result[0]["ok"])

    def test_update_app_starts_thread_when_script_exists(self):
        web = self._create_web_interface()

        with patch("web_interface.os.path.exists", side_effect=[False, True]), \
             patch("web_interface.threading.Thread") as mock_thread:
            result = web.update_app()

        self.assertTrue(result["ok"])
        self.assertEqual(result["msg"], "Update started")
        self.assertEqual(result["script"], "update_app.sh")
        mock_thread.assert_called_once()

    def test_update_app_returns_404_when_script_missing(self):
        web = self._create_web_interface()

        with patch("web_interface.os.path.exists", return_value=False):
            result = web.update_app()

        self.assertEqual(result[1], 404)
        self.assertFalse(result[0]["ok"])
        self.assertIn("not found", result[0]["msg"].lower())


if __name__ == "__main__":
    unittest.main()
