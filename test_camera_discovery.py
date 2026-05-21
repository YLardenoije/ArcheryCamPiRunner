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

    def test_discover_onvif_ws_cameras(self):
        class FakeSocket:
            def __init__(self, *_args, **_kwargs):
                self.responses = [
                    (
                        (
                            b"<Envelope><Body><d:ProbeMatches>"
                            b"<d:ProbeMatch><d:XAddrs>http://192.168.1.77/onvif/device_service</d:XAddrs>"
                            b"</d:ProbeMatch></d:ProbeMatches></Body></Envelope>"
                        ),
                        ("192.168.1.77", 3702),
                    )
                ]

            def setsockopt(self, *_args, **_kwargs):
                return None

            def settimeout(self, *_args, **_kwargs):
                return None

            def sendto(self, *_args, **_kwargs):
                return None

            def recvfrom(self, *_args, **_kwargs):
                if self.responses:
                    return self.responses.pop(0)
                raise camera_discovery.socket.timeout()

            def close(self):
                return None

        with patch("camera_discovery.socket.socket", return_value=FakeSocket()):
            cameras = camera_discovery.discover_onvif_ws_cameras(
                timeout_seconds=0.2,
                default_path="/live/0/MAIN",
            )

        self.assertEqual(len(cameras), 1)
        self.assertEqual(cameras[0]["url"], "rtsp://192.168.1.77:554/live/0/MAIN")
        self.assertEqual(cameras[0]["source"], "onvif-ws-discovery")

    def test_discover_rtsp_port_scan_cameras(self):
        hosts = ["192.168.1.10", "192.168.1.11", "192.168.1.12"]

        def fake_open(host, port, _timeout):
            return (host, port) in {("192.168.1.10", 554), ("192.168.1.12", 8554)}

        def fake_rtsp(host, port, _timeout):
            return (host, port) in {("192.168.1.10", 554), ("192.168.1.12", 8554)}

        with patch("camera_discovery._candidate_hosts", return_value=hosts), patch(
            "camera_discovery._is_tcp_port_open", side_effect=fake_open
        ), patch(
            "camera_discovery._looks_like_rtsp_endpoint", side_effect=fake_rtsp
        ):
            cameras = camera_discovery.discover_rtsp_port_scan_cameras(
                subnet_cidr="192.168.1.0/24",
                ports=[554, 8554],
                timeout_seconds=0.2,
                max_hosts=3,
                default_path="/live/0/MAIN",
            )

        urls = sorted([c["url"] for c in cameras])
        self.assertEqual(urls, ["rtsp://192.168.1.10:554/live/0/MAIN", "rtsp://192.168.1.12:8554/live/0/MAIN"])

    def test_normalize_rtsp_paths_dedupes_and_formats(self):
        paths = camera_discovery._normalize_rtsp_paths(
            default_path="live/0/MAIN",
            path_candidates=["/live/0/MAIN", "stream1", "/stream1", ""],
        )
        self.assertEqual(paths, ["/live/0/MAIN", "/stream1", ""])

    def test_discover_working_rtsp_url_uses_first_valid_candidate(self):
        with patch(
            "camera_discovery._probe_rtsp_path_status",
            side_effect=[404, 404, 200],
        ):
            url = camera_discovery._discover_working_rtsp_url(
                "192.168.1.88",
                554,
                default_path="/live/0/MAIN",
                path_candidates=["/bad", "/stream1"],
                timeout_seconds=0.2,
            )

        self.assertEqual(url, "rtsp://192.168.1.88:554/stream1")

    def test_discover_working_rtsp_url_auth_ambiguous_returns_base_url(self):
        with patch(
            "camera_discovery._probe_rtsp_path_status",
            side_effect=[401, 401, 401],
        ):
            url = camera_discovery._discover_working_rtsp_url(
                "192.168.1.88",
                554,
                default_path="/live/0/MAIN",
                path_candidates=["/stream1", "/11"],
                timeout_seconds=0.2,
            )

        self.assertEqual(url, "rtsp://192.168.1.88:554")

    def test_discover_rtsp_port_scan_uses_interface_hint_subnet(self):
        with patch("camera_discovery._interface_subnet_cidr", return_value="192.168.100.0/24"), patch(
            "camera_discovery._candidate_hosts", return_value=[]
        ):
            cameras = camera_discovery.discover_rtsp_port_scan_cameras(
                subnet_cidr="",
                interface_hint="eth0",
                timeout_seconds=0.2,
                max_hosts=5,
            )

        self.assertEqual(cameras, [])

    def test_discover_rtsp_port_scan_cameras_multi_dedupes(self):
        scan_one = [
            {
                "name": "scan-192.168.100.10:554",
                "url": "rtsp://192.168.100.10:554/live/0/MAIN",
                "service_type": "_rtsp._tcp.scan",
                "host": "192.168.100.10",
                "port": 554,
                "source": "rtsp-port-scan",
            }
        ]
        scan_two = [
            {
                "name": "scan-192.168.10.103:554",
                "url": "rtsp://192.168.10.103:554/live/0/MAIN",
                "service_type": "_rtsp._tcp.scan",
                "host": "192.168.10.103",
                "port": 554,
                "source": "rtsp-port-scan",
            },
            {
                "name": "scan-192.168.100.10:554",
                "url": "rtsp://192.168.100.10:554/live/0/MAIN",
                "service_type": "_rtsp._tcp.scan",
                "host": "192.168.100.10",
                "port": 554,
                "source": "rtsp-port-scan",
            },
        ]

        with patch(
            "camera_discovery.discover_rtsp_port_scan_cameras",
            side_effect=[scan_one, scan_two],
        ):
            cameras = camera_discovery.discover_rtsp_port_scan_cameras_multi(
                subnet_cidrs=["192.168.100.0/24", "192.168.10.0/24"],
                timeout_seconds=0.2,
            )

        urls = sorted([c["url"] for c in cameras])
        self.assertEqual(
            urls,
            [
                "rtsp://192.168.10.103:554/live/0/MAIN",
                "rtsp://192.168.100.10:554/live/0/MAIN",
            ],
        )

    def test_discover_rtsp_port_scan_cameras_multi_retries_without_handshake(self):
        retry_result = [
            {
                "name": "scan-192.168.10.103:554",
                "url": "rtsp://192.168.10.103:554/live/0/MAIN",
                "service_type": "_rtsp._tcp.scan",
                "host": "192.168.10.103",
                "port": 554,
                "source": "rtsp-port-scan",
            }
        ]

        with patch(
            "camera_discovery.discover_rtsp_port_scan_cameras",
            side_effect=[[], retry_result],
        ) as scan_mock:
            cameras = camera_discovery.discover_rtsp_port_scan_cameras_multi(
                subnet_cidrs=["192.168.10.0/24"],
                timeout_seconds=0.2,
                require_rtsp_handshake=True,
                retry_without_handshake=True,
            )

        self.assertEqual(len(cameras), 1)
        self.assertEqual(cameras[0]["url"], "rtsp://192.168.10.103:554/live/0/MAIN")
        self.assertEqual(cameras[0]["source"], "rtsp-port-scan-unverified")
        self.assertIn("(unverified)", cameras[0]["name"])

        first_call = scan_mock.call_args_list[0].kwargs
        second_call = scan_mock.call_args_list[1].kwargs
        self.assertTrue(first_call["require_rtsp_handshake"])
        self.assertFalse(second_call["require_rtsp_handshake"])


if __name__ == "__main__":
    unittest.main()
