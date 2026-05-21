"""Unit tests for config module."""
import os
import unittest
from unittest.mock import patch
import config


class TestConfig(unittest.TestCase):
    """Test configuration settings."""
    
    def test_upload_folder_exists(self):
        """Test that upload folder is created."""
        self.assertTrue(os.path.exists(config.UPLOAD_FOLDER))
    
    def test_upload_folder_path(self):
        """Test that upload folder path is expanded."""
        self.assertIn("kiosk_images", config.UPLOAD_FOLDER)
        self.assertNotIn("~", config.UPLOAD_FOLDER)
    
    def test_rtsp_url_format(self):
        """Test that RTSP URL is no longer hardcoded."""
        self.assertEqual(config.RTSP_URL, "")
    
    def test_flask_port_is_int(self):
        """Test that Flask port is an integer."""
        self.assertIsInstance(config.FLASK_PORT, int)
        self.assertGreater(config.FLASK_PORT, 0)
        self.assertLess(config.FLASK_PORT, 65536)
    
    def test_fade_duration_is_positive(self):
        """Test that fade duration is positive."""
        self.assertIsInstance(config.FADE_DURATION, (int, float))
        self.assertGreater(config.FADE_DURATION, 0)
    
    def test_fade_steps_is_positive_int(self):
        """Test that fade steps is a positive integer."""
        self.assertIsInstance(config.FADE_STEPS, int)
        self.assertGreater(config.FADE_STEPS, 0)


if __name__ == "__main__":
    unittest.main()
