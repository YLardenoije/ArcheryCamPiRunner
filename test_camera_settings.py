"""Unit tests for camera settings persistence."""

import os
import tempfile
import unittest

from camera_settings import CameraSettingsStore


class TestCameraSettingsStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.file_path = os.path.join(self.temp_dir, "camera_settings.json")
        self.store = CameraSettingsStore(self.file_path)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_set_and_get_settings(self):
        ok = self.store.set_settings(
            "AA-BB-CC-DD-EE-FF",
            name="Lane 1",
            role="primary",
            zoom=0.4,
            focus=-0.2,
        )
        self.assertTrue(ok)

        loaded = self.store.get_settings("aa:bb:cc:dd:ee:ff")
        self.assertEqual(loaded.get("name"), "Lane 1")
        self.assertEqual(loaded.get("role"), "primary")
        self.assertEqual(loaded.get("ptz", {}).get("zoom"), 0.4)
        self.assertEqual(loaded.get("ptz", {}).get("focus"), -0.2)

    def test_role_is_unique(self):
        self.store.set_settings("aa:bb:cc:dd:ee:01", role="primary")
        self.store.set_settings("aa:bb:cc:dd:ee:02", role="primary")

        one = self.store.get_settings("aa:bb:cc:dd:ee:01")
        two = self.store.get_settings("aa:bb:cc:dd:ee:02")
        self.assertEqual(one.get("role", ""), "")
        self.assertEqual(two.get("role", ""), "primary")

    def test_choose_startup_camera_prefers_roles(self):
        cameras = [
            {"name": "cam-a", "url": "rtsp://a", "mac": "aa:bb:cc:dd:ee:01"},
            {"name": "cam-b", "url": "rtsp://b", "mac": "aa:bb:cc:dd:ee:02"},
        ]
        self.store.set_settings("aa:bb:cc:dd:ee:02", role="primary")
        self.store.apply_to_cameras(cameras)

        chosen = self.store.choose_startup_camera(cameras)
        self.assertEqual(chosen.get("url"), "rtsp://b")


if __name__ == "__main__":
    unittest.main()
