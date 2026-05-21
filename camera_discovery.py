"""Discover RTSP cameras via zeroconf/mDNS."""

import concurrent.futures
import ipaddress
import re
import socket
import subprocess
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


def discover_rtsp_cameras(service_types, timeout_seconds=8.0, default_path=""):
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
            url = _append_default_path_if_missing(url, default_path)

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


def _append_default_path_if_missing(url, default_path=""):
    """Append default path if URL has no path component."""
    if not url or not default_path:
        return url

    path = default_path if default_path.startswith("/") else "/" + default_path
    match = re.match(r"^(rtsp://[^/]+)(/.*)?$", url)
    if not match:
        return url

    base, existing_path = match.group(1), match.group(2)
    if existing_path:
        return url
    return base + path


def discover_onvif_ws_cameras(timeout_seconds=4.0, default_path=""):
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
                    rtsp_url = _append_default_path_if_missing(f"rtsp://{host}:554", default_path)
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


def _interface_subnet_cidr(interface_name):
    """Return IPv4 subnet CIDR for a given interface name using ip command."""
    if not interface_name:
        return ""
    try:
        result = subprocess.run(
            ["ip", "-o", "-4", "addr", "show", "dev", interface_name],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return ""
        for line in result.stdout.splitlines():
            match = re.search(r"inet\s+([0-9.]+)/(\d+)", line)
            if not match:
                continue
            ip_addr = match.group(1)
            prefix = match.group(2)
            network = ipaddress.ip_network(f"{ip_addr}/{prefix}", strict=False)
            return str(network)
    except Exception:
        return ""
    return ""


def _looks_like_rtsp_endpoint(host, port, timeout_seconds):
    """Send an RTSP OPTIONS probe and verify RTSP-like response."""
    try:
        with socket.create_connection((host, int(port)), timeout=max(0.05, float(timeout_seconds))) as sock:
            sock.settimeout(max(0.05, float(timeout_seconds)))
            request = (
                f"OPTIONS rtsp://{host}:{int(port)}/ RTSP/1.0\r\n"
                "CSeq: 1\r\n"
                "User-Agent: ArcheryCamPiRunner\r\n\r\n"
            ).encode("utf-8")
            sock.sendall(request)
            response = sock.recv(256).decode("utf-8", errors="ignore")
            return response.startswith("RTSP/") or "RTSP/" in response
    except Exception:
        return False


def discover_rtsp_port_scan_cameras(
    subnet_cidr="",
    ports=None,
    timeout_seconds=4.0,
    max_hosts=254,
    default_path="",
    interface_hint="",
    require_rtsp_handshake=True,
    connect_timeout_seconds=0.0,
):
    """Fallback discovery by scanning likely RTSP ports on local subnet.

    Returns:
        list[dict]: Camera entries with source='rtsp-port-scan'.
    """
    if ports is None:
        ports = [554, 8554]

    cidr = subnet_cidr or _interface_subnet_cidr(interface_hint) or _auto_subnet_cidr()
    if not cidr:
        return []

    if interface_hint and not subnet_cidr:
        print(f"RTSP scan using interface hint '{interface_hint}' -> subnet {cidr}")

    hosts = _candidate_hosts(cidr)
    if max_hosts > 0:
        hosts = hosts[: int(max_hosts)]

    target_count = max(1, len(hosts) * max(1, len(ports)))
    auto_connect_timeout = max(0.2, min(1.5, float(timeout_seconds) * 64.0 / float(target_count)))
    per_connect_timeout = (
        max(0.05, float(connect_timeout_seconds)) if float(connect_timeout_seconds) > 0 else auto_connect_timeout
    )

    print(
        "RTSP scan parameters:",
        f"subnet={cidr}",
        f"hosts={len(hosts)}",
        f"ports={ports}",
        f"handshake_required={require_rtsp_handshake}",
        f"connect_timeout={per_connect_timeout:.2f}s",
    )

    cameras = []
    seen_urls = set()
    stats = {"open_ports": 0, "handshake_failures": 0}
    stats_lock = threading.Lock()

    def _scan_target(host, port):
        if not _is_tcp_port_open(host, port, per_connect_timeout):
            return None

        with stats_lock:
            stats["open_ports"] += 1

        if require_rtsp_handshake and not _looks_like_rtsp_endpoint(host, port, per_connect_timeout):
            with stats_lock:
                stats["handshake_failures"] += 1
            return None

        if require_rtsp_handshake:
            return host, int(port)

        if _is_tcp_port_open(host, port, per_connect_timeout):
            return host, int(port)

        return None

    futures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as pool:
        for host in hosts:
            for port in ports:
                futures.append(pool.submit(_scan_target, host, port))

        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if not result:
                continue
            host, port = result
            url = _append_default_path_if_missing(f"rtsp://{host}:{port}", default_path)
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

    if not cameras:
        print(
            "RTSP scan found no cameras:",
            f"open_ports={stats['open_ports']}",
            f"handshake_failures={stats['handshake_failures']}",
        )

    return cameras


def discover_rtsp_port_scan_cameras_multi(
    subnet_cidrs,
    ports=None,
    timeout_seconds=4.0,
    max_hosts=254,
    default_path="",
    interface_hint="",
    require_rtsp_handshake=True,
    connect_timeout_seconds=0.0,
    retry_without_handshake=False,
):
    """Scan multiple subnets and combine discovered RTSP cameras.

    Returns:
        list[dict]: Deduplicated camera entries across all subnets.
    """
    merged = []
    seen_urls = set()

    for subnet in subnet_cidrs or []:
        subnet = (subnet or "").strip()
        if not subnet:
            continue

        print(f"RTSP scan multi-subnet pass: {subnet}")
        cameras = discover_rtsp_port_scan_cameras(
            subnet_cidr=subnet,
            ports=ports,
            timeout_seconds=timeout_seconds,
            max_hosts=max_hosts,
            default_path=default_path,
            interface_hint=interface_hint,
            require_rtsp_handshake=require_rtsp_handshake,
            connect_timeout_seconds=connect_timeout_seconds,
        )

        if not cameras and require_rtsp_handshake and retry_without_handshake:
            print(
                f"RTSP scan fallback active on {subnet}: retrying without RTSP handshake validation"
            )
            cameras = discover_rtsp_port_scan_cameras(
                subnet_cidr=subnet,
                ports=ports,
                timeout_seconds=timeout_seconds,
                max_hosts=max_hosts,
                default_path=default_path,
                interface_hint=interface_hint,
                require_rtsp_handshake=False,
                connect_timeout_seconds=connect_timeout_seconds,
            )
            for camera in cameras:
                camera["source"] = "rtsp-port-scan-unverified"
                camera["name"] = f"{camera.get('name', 'scan-camera')} (unverified)"

        for camera in cameras:
            url = camera.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            merged.append(camera)

    return merged
