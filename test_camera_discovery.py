"""Unit tests for zeroconf camera discovery."""
import types
import unittest
from unittest.mock import patch

import camera_discovery


class _FakeServiceInfo:
    def __init__(self, ip_bytes, port=554, properties=None):
        self.addresses = [ip_bytes]
        self.port = port
        self.properties = properties or {}


class TestCameraDiscovery(unittest.TestCase):
    """Test zeroconf discovery and URL construction."""

    def test_build_rtsp_url_with_path(self):
        info = _FakeServiceInfo(
            b"\xc0\xa8\x01\x0a",  # 192.168.1.10
            port=8554,
            properties={b"path": b"/live"},
        )
        url = camera_discovery._build_rtsp_url(info)
        self.assertEqual(url, "rtsp://192.168.1.10:8554/live")

    def test_build_rtsp_url_full_url_property(self):
        info = _FakeServiceInfo(
            b"\xc0\xa8\x01\x0a",
            properties={b"url": b"rtsp://10.0.0.5:554/stream1"},
        )
        url = camera_discovery._build_rtsp_url(info)
        self.assertEqual(url, "rtsp://10.0.0.5:554/stream1")

    def test_discover_returns_none_without_zeroconf(self):
        with patch.dict("sys.modules", {"zeroconf": None}):
            url = camera_discovery.discover_rtsp_url(["_rtsp._tcp.local."], timeout_seconds=0.1)
        self.assertIsNone(url)

    def test_discover_returns_first_found_url(self):
        class FakeListener:
            pass

        class FakeZeroconf:
            def get_service_info(self, service_type, name, timeout=1000):
                return _FakeServiceInfo(
                    b"\xc0\xa8\x01\x14",  # 192.168.1.20
                    port=554,
                    properties={b"path": b"main"},
                )

            def close(self):
                return None

        class FakeServiceBrowser:
            def __init__(self, zeroconf, service_type, listener):
                listener.add_service(zeroconf, service_type, "camera._rtsp._tcp.local.")

            def cancel(self):
                return None

        fake_zeroconf_module = types.SimpleNamespace(
            ServiceBrowser=FakeServiceBrowser,
            ServiceListener=FakeListener,
            Zeroconf=FakeZeroconf,
        )

        with patch.dict("sys.modules", {"zeroconf": fake_zeroconf_module}):
            url = camera_discovery.discover_rtsp_url(["_rtsp._tcp.local."], timeout_seconds=0.2)

        self.assertEqual(url, "rtsp://192.168.1.20:554/main")

    def test_discover_returns_camera_list(self):
        class FakeListener:
            pass

        class FakeZeroconf:
            def get_service_info(self, service_type, name, timeout=1000):
                if "one" in name:
                    return _FakeServiceInfo(b"\xc0\xa8\x01\x0a", port=554, properties={b"path": b"/stream1"})
                return _FakeServiceInfo(b"\xc0\xa8\x01\x0b", port=8554, properties={b"path": b"/stream2"})

            def close(self):
                return None

        class FakeServiceBrowser:
            def __init__(self, zeroconf, service_type, listener):
                listener.add_service(zeroconf, service_type, "camera-one._rtsp._tcp.local.")
                listener.add_service(zeroconf, service_type, "camera-two._rtsp._tcp.local.")

            def cancel(self):
                return None

        fake_zeroconf_module = types.SimpleNamespace(
            ServiceBrowser=FakeServiceBrowser,
            ServiceListener=FakeListener,
            Zeroconf=FakeZeroconf,
        )

        with patch.dict("sys.modules", {"zeroconf": fake_zeroconf_module}):
            cameras = camera_discovery.discover_rtsp_cameras(["_rtsp._tcp.local."], timeout_seconds=0.2)

        self.assertEqual(len(cameras), 2)
        self.assertEqual(cameras[0]["url"], "rtsp://192.168.1.10:554/stream1")
        self.assertEqual(cameras[1]["url"], "rtsp://192.168.1.11:8554/stream2")


if __name__ == "__main__":
    unittest.main()
