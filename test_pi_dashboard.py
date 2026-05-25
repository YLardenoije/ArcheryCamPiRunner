"""Unit tests for the multi-Pi dashboard."""

import os
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from pi_registry import PiRegistryStore


class TestPiRegistryStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.store_path = os.path.join(self.temp_dir, "pis.json")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_upsert_and_rename_by_mac(self):
        store = PiRegistryStore(self.store_path)
        self.assertTrue(store.upsert_pi("AA-BB-CC-DD-EE-FF", name="Lane A", api_base_url="http://192.168.1.10:8080"))
        self.assertTrue(store.rename_pi("aa:bb:cc:dd:ee:ff", "Lane B"))

        pi = store.get_pi("aa:bb:cc:dd:ee:ff")
        self.assertEqual(pi.get("name"), "Lane B")
        self.assertEqual(pi.get("api_base_url"), "http://192.168.1.10:8080")


class TestPiDashboardApp(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.store_path = os.path.join(self.temp_dir, "pis.json")
        self.store = PiRegistryStore(self.store_path)
        self.store.upsert_pi("AA:BB:CC:DD:EE:FF", name="Lane 1", api_base_url="http://192.168.1.10:8080")
        self.store.upsert_pi("AA:BB:CC:DD:EE:11", name="Lane 2", api_base_url="http://192.168.1.11:8080")

        self.mock_flask = SimpleNamespace(
            Flask=lambda *args, **kwargs: unittest.mock.MagicMock(),
            jsonify=lambda *args, **kwargs: args[0] if args else kwargs,
            render_template_string=lambda template, **context: template,
            request=unittest.mock.MagicMock(),
        )
        self.flask_patcher = patch.dict("sys.modules", {"flask": self.mock_flask})
        self.flask_patcher.start()

    def tearDown(self):
        import shutil
        self.flask_patcher.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_app(self, request_sender=None):
        from pi_dashboard import PiDashboardApp
        app = PiDashboardApp(store=self.store, auto_discovery_enabled=False)
        if request_sender is not None:
            app._request = request_sender
        return app

    def test_register_pi_route_adds_entry(self):
        app = self._create_app()
        with patch("pi_dashboard.request") as mock_request:
            mock_request.get_json.return_value = {
                "mac": "11:22:33:44:55:66",
                "name": "Lane 3",
                "api_base_url": "http://192.168.1.12:8080",
            }
            result = app.pis_collection()

        self.assertTrue(result["ok"])
        stored = self.store.get_pi("11:22:33:44:55:66")
        self.assertEqual(stored.get("name"), "Lane 3")

    def test_broadcast_primary_hits_all_registered_pis(self):
        calls = []

        def fake_request(method, url, timeout=4.0):
            calls.append((method, url))
            return {"ok": True, "status": 200, "body": "{}"}

        app = self._create_app(request_sender=fake_request)
        result = app._broadcast("primary")

        self.assertTrue(result["ok"])
        self.assertEqual(len(calls), 2)
        self.assertIn("/set_stream_to_primary_camera", calls[0][1])

    def test_show_stream_command_path(self):
        calls = []

        def fake_request(method, url, timeout=4.0):
            calls.append((method, url))
            return {"ok": True, "status": 200, "body": "{}"}

        app = self._create_app(request_sender=fake_request)
        pi = self.store.get_pi("AA:BB:CC:DD:EE:FF")
        result = app._send_command(pi, "show_stream")

        self.assertTrue(result["ok"])
        self.assertIn("/show_stream", calls[0][1])

    def test_primary_fallback_to_get_url_then_set_stream(self):
        calls = []

        def fake_request(method, url, timeout=4.0):
            calls.append(url)
            if url.endswith("/set_stream_to_primary_camera"):
                return {"ok": False, "status": 404, "body": "not found", "error": "404"}
            if url.endswith("/get_primary_url"):
                return {
                    "ok": True,
                    "status": 200,
                    "body": '{"ok": true, "url": "rtsp://192.168.1.10:554/live/0/MAIN"}',
                }
            if "/set_stream?url=" in url:
                return {"ok": True, "status": 200, "body": "ok"}
            return {"ok": False, "status": 500, "body": "", "error": "unexpected"}

        app = self._create_app(request_sender=fake_request)
        pi = self.store.get_pi("AA:BB:CC:DD:EE:FF")
        result = app._send_command(pi, "primary")

        self.assertTrue(result["ok"])
        self.assertTrue(result.get("fallback_used"))
        self.assertTrue(any("/get_primary_url" in item for item in calls))
        self.assertTrue(any("/set_stream?url=" in item for item in calls))

    def test_show_image_falls_back_to_logo(self):
        def fake_request(method, url, timeout=4.0):
            if url.endswith("/show_image/Commercial1.jpg"):
                return {"ok": False, "status": 404, "body": "not found", "error": "404"}
            if url.endswith("/show_image/Logo.jpg"):
                return {"ok": True, "status": 200, "body": "{}"}
            return {"ok": True, "status": 200, "body": "{}"}

        app = self._create_app(request_sender=fake_request)
        pi = self.store.get_pi("AA:BB:CC:DD:EE:FF")
        result = app._send_command(pi, "show_image", image="Commercial1.jpg")

        self.assertTrue(result["ok"])
        self.assertTrue(result["fallback_used"])

    def test_start_and_stop_commercials_state(self):
        app = self._create_app()
        with patch("pi_dashboard.request") as mock_request:
            mock_request.get_json.return_value = None
            mock_request.form.to_dict.return_value = {}
            result = app.start_commercials()

        self.assertEqual(result[1], 400)
        self.assertFalse(result[0]["ok"])

        with patch("pi_dashboard.threading.Thread") as mock_thread:
            mock_thread.return_value.is_alive.return_value = False
            mock_thread.return_value.start.return_value = None
            with patch("pi_dashboard.request") as mock_request:
                mock_request.get_json.return_value = None
                mock_request.form.to_dict.return_value = {
                    "images": "Commercial1.jpg,Commercial2.jpg",
                    "interval_seconds": 3,
                }
                result = app.start_commercials()

        self.assertTrue(result["ok"])
        stop_result = app.stop_commercials()
        self.assertTrue(stop_result["ok"])

    def test_discover_pis_registers_when_mac_resolved(self):
        app = self._create_app()
        with patch.object(app, "_discover_pi_candidates", return_value=[
            {
                "host": "192.168.1.77",
                "api_base_url": "http://192.168.1.77:8080",
                "ui_url": "http://192.168.1.77:8080",
                "mac": "22:33:44:55:66:77",
                "name": "Pi 192.168.1.77",
            }
        ]):
            with patch("pi_dashboard.request") as mock_request:
                mock_request.get_json.return_value = {}
                result = app.discover_pis()

        self.assertTrue(result["ok"])
        self.assertEqual(result["found"], 1)
        self.assertEqual(result["added"], 1)
        stored = self.store.get_pi("22:33:44:55:66:77")
        self.assertEqual(stored.get("api_base_url"), "http://192.168.1.77:8080")

    def test_discover_pis_reports_unresolved_mac(self):
        app = self._create_app()
        with patch.object(app, "_discover_pi_candidates", return_value=[
            {
                "host": "192.168.1.88",
                "api_base_url": "http://192.168.1.88:8080",
                "ui_url": "http://192.168.1.88:8080",
                "mac": "",
                "name": "Pi 192.168.1.88",
            }
        ]):
            with patch("pi_dashboard.request") as mock_request:
                mock_request.get_json.return_value = {}
                result = app.discover_pis()

        self.assertTrue(result["ok"])
        self.assertEqual(result["found"], 1)
        self.assertEqual(result["added"], 0)
        self.assertEqual(len(result["unresolved"]), 1)

    def test_run_discovery_cycle_returns_stats(self):
        app = self._create_app()
        with patch.object(app, "_discover_pi_candidates", return_value=[
            {
                "host": "192.168.1.90",
                "api_base_url": "http://192.168.1.90:8080",
                "ui_url": "http://192.168.1.90:8080",
                "mac": "33:44:55:66:77:88",
                "name": "Pi 192.168.1.90",
            }
        ]):
            stats = app._run_discovery_cycle(timeout_seconds=0.5)

        self.assertEqual(stats["found"], 1)
        self.assertEqual(stats["added"], 1)
        self.assertEqual(stats["unresolved"], [])


if __name__ == "__main__":
    unittest.main()
