"""Discover RTSP cameras via zeroconf/mDNS."""

import concurrent.futures
import ipaddress
import re
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


def _extract_host_from_url(url):
    """Extract host part from an HTTP/RTSP URL-like string."""
    if not url:
        return ""
    match = re.match(r"^[a-zA-Z]+://([^/:]+)", url)
    if not match:
        return ""
    return match.group(1)


def discover_onvif_ws_cameras(timeout_seconds=4.0):
    """Discover cameras via ONVIF WS-Discovery over multicast UDP.

    Returns:
        list[dict]: Camera entries with source='onvif-ws-discovery'.
    """
    message = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<e:Envelope xmlns:e=\"http://www.w3.org/2003/05/soap-envelope\" "
        "xmlns:w=\"http://schemas.xmlsoap.org/ws/2004/08/addressing\" "
        "xmlns:d=\"http://schemas.xmlsoap.org/ws/2005/04/discovery\" "
        "xmlns:dn=\"http://www.onvif.org/ver10/network/wsdl\">"
        "<e:Header>"
        "<w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>"
        "<w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>"
        "</e:Header>"
        "<e:Body>"
        "<d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe>"
        "</e:Body>"
        "</e:Envelope>"
    ).encode("utf-8")

    cameras = []
    seen = set()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.settimeout(max(0.2, float(timeout_seconds) / 3.0))
        sock.sendto(message, ("239.255.255.250", 3702))

        while True:
            try:
                payload, _addr = sock.recvfrom(8192)
            except socket.timeout:
                break

            text = payload.decode("utf-8", errors="ignore")
            xaddrs = re.findall(r"<[^>]*XAddrs[^>]*>(.*?)</[^>]*XAddrs>", text, flags=re.IGNORECASE | re.DOTALL)
            if not xaddrs:
                continue

            for field in xaddrs:
                for token in field.split():
                    host = _extract_host_from_url(token)
                    if not host:
                        continue
                    rtsp_url = f"rtsp://{host}:554"
                    if rtsp_url in seen:
                        continue
                    seen.add(rtsp_url)
                    cameras.append(
                        {
                            "name": f"onvif-{host}",
                            "url": rtsp_url,
                            "service_type": "_onvif._tcp.local.",
                            "host": host,
                            "port": 554,
                            "source": "onvif-ws-discovery",
                        }
                    )
    except Exception:
        return []
    finally:
        sock.close()

    return cameras


def _is_tcp_port_open(host, port, timeout_seconds):
    """Return True when a TCP port is connectable within timeout."""
    try:
        with socket.create_connection((host, int(port)), timeout=max(0.05, float(timeout_seconds))):
            return True
    except Exception:
        return False


def _candidate_hosts(subnet):
    """Return host IPs from a subnet CIDR string."""
    try:
        network = ipaddress.ip_network(subnet, strict=False)
    except Exception:
        return []
    return [str(ip) for ip in network.hosts()]


def _auto_subnet_cidr():
    """Best-effort detection of local /24 subnet from default route interface."""
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        local_ip = probe.getsockname()[0]
        probe.close()
        octets = local_ip.split(".")
        if len(octets) != 4:
            return ""
        return f"{octets[0]}.{octets[1]}.{octets[2]}.0/24"
    except Exception:
        return ""


def discover_rtsp_port_scan_cameras(subnet_cidr="", ports=None, timeout_seconds=4.0, max_hosts=254):
    """Fallback discovery by scanning likely RTSP ports on local subnet.

    Returns:
        list[dict]: Camera entries with source='rtsp-port-scan'.
    """
    if ports is None:
        ports = [554, 8554]

    cidr = subnet_cidr or _auto_subnet_cidr()
    if not cidr:
        return []

    hosts = _candidate_hosts(cidr)
    if max_hosts > 0:
        hosts = hosts[: int(max_hosts)]

    cameras = []
    seen_urls = set()
    per_connect_timeout = max(0.05, float(timeout_seconds) / max(1, len(hosts)))

    def _scan_target(host, port):
        if _is_tcp_port_open(host, port, per_connect_timeout):
            return host, int(port)
        return None

    futures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as pool:
        for host in hosts:
            for port in ports:
                futures.append(pool.submit(_scan_target, host, port))

        try:
            for future in concurrent.futures.as_completed(futures, timeout=max(1.0, float(timeout_seconds) * 2.0)):
                result = future.result()
                if not result:
                    continue
                host, port = result
                url = f"rtsp://{host}:{port}"
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                cameras.append(
                    {
                        "name": f"scan-{host}:{port}",
                        "url": url,
                        "service_type": "_rtsp._tcp.scan",
                        "host": host,
                        "port": port,
                        "source": "rtsp-port-scan",
                    }
                )
        except concurrent.futures.TimeoutError:
            # Keep cameras discovered so far when scan time budget is exceeded.
            pass

    return cameras
