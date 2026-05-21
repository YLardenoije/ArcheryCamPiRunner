"""Discover RTSP cameras via zeroconf/mDNS."""

import socket
import threading


def _decode_property(properties, keys):
    """Return first matching TXT property value from keys as a string."""
    for key in keys:
        if key in properties:
            value = properties.get(key)
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="ignore").strip()
            if value is not None:
                return str(value).strip()
    return ""


def _build_rtsp_url(info):
    """Build an RTSP URL from zeroconf service info."""
    addresses = getattr(info, "addresses", None) or []
    if not addresses:
        return None

    host = socket.inet_ntoa(addresses[0])
    if not host:
        return None

    port = getattr(info, "port", 554) or 554
    properties = getattr(info, "properties", {}) or {}

    # Common TXT fields seen on RTSP-capable zeroconf services.
    path = _decode_property(properties, (b"path", b"resource", b"stream", b"url"))
    if path.startswith("rtsp://"):
        return path

    if path and not path.startswith("/"):
        path = "/" + path

    return f"rtsp://{host}:{port}{path}"


def _get_service_name(name):
    """Normalize zeroconf service instance names for display."""
    if not name:
        return "unknown camera"
    return str(name).rstrip(".")


def discover_rtsp_url(service_types, timeout_seconds=8.0):
    """Discover the first RTSP URL from zeroconf services.

    Returns:
        str | None: Discovered RTSP URL, or None if discovery fails/times out.
    """
    try:
        from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
    except Exception:
        return None

    found_event = threading.Event()
    found = {"url": None}
    lock = threading.Lock()

    class _Listener(ServiceListener):
        def _resolve(self, zeroconf, service_type, name):
            info = zeroconf.get_service_info(service_type, name, timeout=1000)
            if info is None:
                return

            url = _build_rtsp_url(info)
            if not url:
                return

            with lock:
                if not found["url"]:
                    found["url"] = url
                    found_event.set()

        def add_service(self, zeroconf, service_type, name):
            self._resolve(zeroconf, service_type, name)

        def update_service(self, zeroconf, service_type, name):
            self._resolve(zeroconf, service_type, name)

        def remove_service(self, zeroconf, service_type, name):
            return None

    zeroconf = Zeroconf()
    browsers = []
    listener = _Listener()
    try:
        for service_type in service_types:
            browsers.append(ServiceBrowser(zeroconf, service_type, listener))
        found_event.wait(timeout=max(0.1, float(timeout_seconds)))
        return found["url"]
    finally:
        for browser in browsers:
            try:
                browser.cancel()
            except Exception:
                pass
        zeroconf.close()


def discover_rtsp_cameras(service_types, timeout_seconds=8.0):
    """Discover RTSP cameras via zeroconf/mDNS.

    Returns:
        list[dict]: Ordered camera entries with name/url/service_type/host/port.
    """
    try:
        from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
    except Exception:
        return []

    cameras = []
    seen_urls = set()
    lock = threading.Lock()
    done_event = threading.Event()

    class _Listener(ServiceListener):
        def _resolve(self, zeroconf, service_type, name):
            info = zeroconf.get_service_info(service_type, name, timeout=1000)
            if info is None:
                return

            url = _build_rtsp_url(info)
            if not url:
                return

            with lock:
                if url in seen_urls:
                    return
                seen_urls.add(url)
                addresses = getattr(info, "addresses", None) or []
                host = socket.inet_ntoa(addresses[0]) if addresses else ""
                cameras.append(
                    {
                        "name": _get_service_name(name),
                        "url": url,
                        "service_type": service_type,
                        "host": host,
                        "port": getattr(info, "port", 554) or 554,
                    }
                )

        def add_service(self, zeroconf, service_type, name):
            self._resolve(zeroconf, service_type, name)

        def update_service(self, zeroconf, service_type, name):
            self._resolve(zeroconf, service_type, name)

        def remove_service(self, zeroconf, service_type, name):
            return None

    zeroconf = Zeroconf()
    browsers = []
    listener = _Listener()
    try:
        for service_type in service_types:
            browsers.append(ServiceBrowser(zeroconf, service_type, listener))
        done_event.wait(timeout=max(0.1, float(timeout_seconds)))
        if not cameras:
            print("Zeroconf discovery finished with no cameras found.")
        return cameras
    finally:
        for browser in browsers:
            try:
                browser.cancel()
            except Exception:
                pass
        zeroconf.close()
