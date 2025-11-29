"""Unit tests for PTZ controller module."""
import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch, MagicMock


class TestPTZController(unittest.TestCase):
    """Test PTZ controller functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create temporary directory for presets file
        self.temp_dir = tempfile.mkdtemp()
        self.presets_file = os.path.join(self.temp_dir, "presets.json")
        
        # Import after setup
        from ptz_controller import PTZController
        self.PTZController = PTZController
    
    def tearDown(self):
        """Clean up temp files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_initialization_no_presets_file(self):
        """Test controller initializes with no existing presets file."""
        controller = self.PTZController(self.presets_file)
        
        self.assertEqual(controller.presets_file, self.presets_file)
        self.assertIsNone(controller.camera_host)
        self.assertEqual(controller.camera_port, 80)
        self.assertEqual(controller.list_presets(), {})
    
    def test_initialization_with_camera_config(self):
        """Test controller initializes with camera configuration."""
        controller = self.PTZController(
            self.presets_file,
            camera_host="192.168.1.100",
            camera_port=8080,
            username="testuser",
            password="testpass"
        )
        
        self.assertEqual(controller.camera_host, "192.168.1.100")
        self.assertEqual(controller.camera_port, 8080)
        self.assertEqual(controller.username, "testuser")
        self.assertEqual(controller.password, "testpass")
    
    def test_load_existing_presets(self):
        """Test loading existing presets from file."""
        # Create presets file
        presets = {
            "preset1": {"pan": 0.5, "tilt": -0.3, "zoom": 0.2},
            "preset2": {"pan": -0.8, "tilt": 0.1, "zoom": 0.9}
        }
        with open(self.presets_file, 'w') as f:
            json.dump(presets, f)
        
        controller = self.PTZController(self.presets_file)
        
        loaded_presets = controller.list_presets()
        self.assertEqual(len(loaded_presets), 2)
        self.assertEqual(loaded_presets["preset1"]["pan"], 0.5)
        self.assertEqual(loaded_presets["preset2"]["zoom"], 0.9)
    
    def test_load_corrupt_presets_file(self):
        """Test handling of corrupt presets file."""
        # Create corrupt presets file
        with open(self.presets_file, 'w') as f:
            f.write("not valid json{{{")
        
        controller = self.PTZController(self.presets_file)
        
        # Should return empty dict on error
        self.assertEqual(controller.list_presets(), {})
    
    def test_save_preset(self):
        """Test saving a preset."""
        controller = self.PTZController(self.presets_file)
        
        success = controller.save_preset("test_preset", 0.5, -0.3, 0.2)
        
        self.assertTrue(success)
        self.assertTrue(os.path.exists(self.presets_file))
        
        # Verify preset is saved
        presets = controller.list_presets()
        self.assertIn("test_preset", presets)
        self.assertEqual(presets["test_preset"]["pan"], 0.5)
        self.assertEqual(presets["test_preset"]["tilt"], -0.3)
        self.assertEqual(presets["test_preset"]["zoom"], 0.2)
    
    def test_save_preset_clamps_values(self):
        """Test that save_preset clamps values to valid ranges."""
        controller = self.PTZController(self.presets_file)
        
        # Values outside range
        controller.save_preset("clamped", 2.0, -2.0, 1.5)
        
        presets = controller.list_presets()
        self.assertEqual(presets["clamped"]["pan"], 1.0)  # clamped from 2.0
        self.assertEqual(presets["clamped"]["tilt"], -1.0)  # clamped from -2.0
        self.assertEqual(presets["clamped"]["zoom"], 1.0)  # clamped from 1.5
    
    def test_save_preset_invalid_name(self):
        """Test saving preset with invalid name fails."""
        controller = self.PTZController(self.presets_file)
        
        # Empty name
        success = controller.save_preset("", 0.5, 0.5, 0.5)
        self.assertFalse(success)
        
        # Special characters
        success = controller.save_preset("test@#$%", 0.5, 0.5, 0.5)
        self.assertFalse(success)
    
    def test_save_preset_valid_names(self):
        """Test saving preset with various valid names."""
        controller = self.PTZController(self.presets_file)
        
        # Alphanumeric
        self.assertTrue(controller.save_preset("preset1", 0.1, 0.1, 0.1))
        
        # With underscores
        self.assertTrue(controller.save_preset("my_preset", 0.2, 0.2, 0.2))
        
        # With hyphens
        self.assertTrue(controller.save_preset("my-preset", 0.3, 0.3, 0.3))
        
        # With spaces
        self.assertTrue(controller.save_preset("My Preset", 0.4, 0.4, 0.4))
    
    def test_delete_preset(self):
        """Test deleting a preset."""
        controller = self.PTZController(self.presets_file)
        controller.save_preset("to_delete", 0.5, 0.5, 0.5)
        
        success = controller.delete_preset("to_delete")
        
        self.assertTrue(success)
        self.assertNotIn("to_delete", controller.list_presets())
    
    def test_delete_nonexistent_preset(self):
        """Test deleting a preset that doesn't exist."""
        controller = self.PTZController(self.presets_file)
        
        success = controller.delete_preset("nonexistent")
        
        self.assertFalse(success)
    
    def test_get_preset(self):
        """Test getting a specific preset."""
        controller = self.PTZController(self.presets_file)
        controller.save_preset("get_test", 0.1, 0.2, 0.3)
        
        preset = controller.get_preset("get_test")
        
        self.assertIsNotNone(preset)
        self.assertEqual(preset["pan"], 0.1)
        self.assertEqual(preset["tilt"], 0.2)
        self.assertEqual(preset["zoom"], 0.3)
    
    def test_get_nonexistent_preset(self):
        """Test getting a preset that doesn't exist."""
        controller = self.PTZController(self.presets_file)
        
        preset = controller.get_preset("nonexistent")
        
        self.assertIsNone(preset)
    
    def test_configure_camera(self):
        """Test camera configuration."""
        controller = self.PTZController(self.presets_file)
        
        controller.configure_camera("192.168.1.200", 8080, "admin", "pass123")
        
        self.assertEqual(controller.camera_host, "192.168.1.200")
        self.assertEqual(controller.camera_port, 8080)
        self.assertEqual(controller.username, "admin")
        self.assertEqual(controller.password, "pass123")
    
    def test_is_connected_false_initially(self):
        """Test that is_connected returns False initially."""
        controller = self.PTZController(self.presets_file)
        
        self.assertFalse(controller.is_connected())
    
    def test_get_position_returns_cached_when_not_connected(self):
        """Test get_position returns cached position when not connected."""
        controller = self.PTZController(self.presets_file)
        
        position = controller.get_position()
        
        self.assertEqual(position["pan"], 0.0)
        self.assertEqual(position["tilt"], 0.0)
        self.assertEqual(position["zoom"], 0.0)
    
    def test_absolute_move_caches_position_when_not_connected(self):
        """Test absolute_move caches position when not connected."""
        controller = self.PTZController(self.presets_file)
        
        success = controller.absolute_move(0.5, -0.3, 0.8)
        
        self.assertTrue(success)
        position = controller.get_position()
        self.assertEqual(position["pan"], 0.5)
        self.assertEqual(position["tilt"], -0.3)
        self.assertEqual(position["zoom"], 0.8)
    
    def test_absolute_move_clamps_values(self):
        """Test absolute_move clamps values to valid ranges."""
        controller = self.PTZController(self.presets_file)
        
        controller.absolute_move(2.0, -2.0, -0.5)
        
        position = controller.get_position()
        self.assertEqual(position["pan"], 1.0)
        self.assertEqual(position["tilt"], -1.0)
        self.assertEqual(position["zoom"], 0.0)
    
    def test_goto_preset(self):
        """Test going to a saved preset."""
        controller = self.PTZController(self.presets_file)
        controller.save_preset("goto_test", 0.3, -0.4, 0.5)
        
        success = controller.goto_preset("goto_test")
        
        self.assertTrue(success)
        position = controller.get_position()
        self.assertEqual(position["pan"], 0.3)
        self.assertEqual(position["tilt"], -0.4)
        self.assertEqual(position["zoom"], 0.5)
    
    def test_goto_nonexistent_preset(self):
        """Test going to a preset that doesn't exist."""
        controller = self.PTZController(self.presets_file)
        
        success = controller.goto_preset("nonexistent")
        
        self.assertFalse(success)
    
    def test_connect_without_host(self):
        """Test connect fails when no host is configured."""
        controller = self.PTZController(self.presets_file)
        
        result = controller.connect()
        
        self.assertFalse(result)
    
    @patch('ptz_controller.PTZController.connect')
    def test_connect_with_onvif(self, mock_connect):
        """Test connect with ONVIF mocked."""
        mock_connect.return_value = True
        
        controller = self.PTZController(
            self.presets_file,
            camera_host="192.168.1.100"
        )
        
        # Manually set internal state as if connected
        controller._ptz_service = Mock()
        controller._profile_token = "test_token"
        
        self.assertTrue(controller.is_connected())
    
    def test_stop_returns_true_when_not_connected(self):
        """Test stop returns True when not connected."""
        controller = self.PTZController(self.presets_file)
        
        result = controller.stop()
        
        self.assertTrue(result)
    
    def test_presets_persist_across_instances(self):
        """Test that presets persist across controller instances."""
        # First controller saves presets
        controller1 = self.PTZController(self.presets_file)
        controller1.save_preset("persistent1", 0.1, 0.2, 0.3)
        controller1.save_preset("persistent2", 0.4, 0.5, 0.6)
        
        # Second controller should load them
        controller2 = self.PTZController(self.presets_file)
        presets = controller2.list_presets()
        
        self.assertEqual(len(presets), 2)
        self.assertIn("persistent1", presets)
        self.assertIn("persistent2", presets)


class TestPTZControllerWebIntegration(unittest.TestCase):
    """Test PTZ controller integration with web interface."""
    
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
        
        # Create temp dir for presets
        self.temp_dir = tempfile.mkdtemp()
        
        # Configure config module
        import config
        self.config = config
        self.original_presets_file = config.PTZ_PRESETS_FILE
        config.PTZ_PRESETS_FILE = os.path.join(self.temp_dir, "presets.json")
        
        # Create temp upload folder
        self.original_upload_folder = config.UPLOAD_FOLDER
        config.UPLOAD_FOLDER = self.temp_dir
    
    def tearDown(self):
        """Clean up patches and temp files."""
        self.flask_patcher.stop()
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        self.config.PTZ_PRESETS_FILE = self.original_presets_file
        self.config.UPLOAD_FOLDER = self.original_upload_folder
    
    def _create_web_interface(self):
        """Helper to create web interface instance."""
        from web_interface import WebInterface
        return WebInterface(self.mock_gui, self.mock_vlc_player, self.mock_shutdown)
    
    def test_web_interface_has_ptz_controller(self):
        """Test web interface initializes with PTZ controller."""
        web = self._create_web_interface()
        
        self.assertIsNotNone(web.ptz)
        self.assertIsNotNone(web.ptz.presets_file)
    
    def test_ptz_configure_sets_camera_host(self):
        """Test PTZ configure endpoint updates camera settings."""
        with patch('web_interface.request') as mock_request:
            mock_request.form.get.side_effect = lambda k, d="": {
                "host": "192.168.1.50",
                "port": "80",
                "username": "admin",
                "password": "admin123"
            }.get(k, d)
            
            with patch('web_interface.redirect'):
                with patch('ptz_controller.PTZController.connect'):
                    web = self._create_web_interface()
                    web.ptz_configure()
                    
                    self.assertEqual(web.ptz.camera_host, "192.168.1.50")
                    self.assertEqual(web.ptz.password, "admin123")
    
    def test_ptz_move_updates_position(self):
        """Test PTZ move endpoint updates position."""
        with patch('web_interface.request') as mock_request:
            mock_request.form.get.side_effect = lambda k, d=0: {
                "pan": "0.5",
                "tilt": "-0.3",
                "zoom": "0.8"
            }.get(k, str(d))
            mock_request.is_json = False
            mock_request.headers.get.return_value = None
            
            with patch('web_interface.redirect'):
                web = self._create_web_interface()
                web.ptz_move()
                
                position = web.ptz.get_position()
                self.assertEqual(position["pan"], 0.5)
                self.assertEqual(position["tilt"], -0.3)
                self.assertEqual(position["zoom"], 0.8)
    
    def test_ptz_save_preset_via_form(self):
        """Test saving preset via form submission."""
        with patch('web_interface.request') as mock_request:
            mock_request.is_json = False
            mock_request.form.get.side_effect = lambda k, d="": {
                "name": "test_preset",
                "pan": "0.2",
                "tilt": "0.3",
                "zoom": "0.4"
            }.get(k, str(d) if d != "" else "")
            
            with patch('web_interface.redirect'):
                web = self._create_web_interface()
                web.ptz_save_preset()
                
                presets = web.ptz.list_presets()
                self.assertIn("test_preset", presets)
    
    def test_ptz_delete_preset_via_web(self):
        """Test deleting preset via web UI."""
        with patch('web_interface.redirect'):
            web = self._create_web_interface()
            web.ptz.save_preset("to_delete", 0.1, 0.1, 0.1)
            
            self.assertIn("to_delete", web.ptz.list_presets())
            
            web.ptz_delete_preset("to_delete")
            
            self.assertNotIn("to_delete", web.ptz.list_presets())
    
    def test_ptz_goto_preset_via_web(self):
        """Test going to preset via web UI."""
        with patch('web_interface.request') as mock_request:
            mock_request.is_json = False
            mock_request.headers.get.return_value = None
            
            with patch('web_interface.redirect'):
                web = self._create_web_interface()
                web.ptz.save_preset("goto_test", 0.6, -0.7, 0.8)
                
                web.ptz_goto_preset("goto_test")
                
                position = web.ptz.get_position()
                self.assertEqual(position["pan"], 0.6)
                self.assertEqual(position["tilt"], -0.7)
                self.assertEqual(position["zoom"], 0.8)


if __name__ == "__main__":
    unittest.main()
