"""Optional camera control helpers (best-effort ONVIF PTZ zoom/focus)."""

import time
import traceback

# Ports to probe when the configured port fails to return a valid ONVIF response.
# Many cameras serve an HTML admin page on 80 while ONVIF is on 8080 / 2020 etc.
_ONVIF_FALLBACK_PORTS = [8080, 2020, 8000, 8899, 80]


def _connect_onvif(ONVIFCamera, host, port, username, password):
    """Create ONVIFCamera on *port* and return it, or raise on failure."""
    print(f"PTZ: trying ONVIF connect to {host}:{port}")
    return ONVIFCamera(host, int(port), username, password)


def apply_zoom_focus_onvif(host, zoom_value, focus_value, username="", password="", port=80):
    """Best-effort ONVIF zoom/focus command.

    zoom_value and focus_value are expected in [-1.0, 1.0].
    Returns (success: bool, message: str).
    """
    print(f"PTZ: apply_zoom_focus_onvif host={host!r} port={port} zoom={zoom_value} focus={focus_value} has_creds={bool(username and password)}")

    if not host:
        msg = "PTZ: missing host, skipping"
        print(msg)
        return False, "Missing host"

    if not username or not password:
        msg = "PTZ: ONVIF credentials not configured (set ONVIF_USERNAME and ONVIF_PASSWORD in config.py)"
        print(msg)
        return False, "ONVIF credentials are not configured"

    try:
        from onvif import ONVIFCamera
        print("PTZ: onvif module loaded")
    except Exception as exc:
        msg = f"PTZ: python-onvif-zeep import failed: {exc}"
        print(msg)
        return False, "python-onvif-zeep is not installed"

    # Build ordered port list: configured port first, then common fallbacks.
    configured_port = int(port)
    ports_to_try = [configured_port] + [p for p in _ONVIF_FALLBACK_PORTS if p != configured_port]

    camera = None
    for try_port in ports_to_try:
        try:
            camera = _connect_onvif(ONVIFCamera, host, try_port, username, password)
            print(f"PTZ: ONVIF connected successfully on port {try_port}")
            break
        except Exception as conn_exc:
            print(f"PTZ: port {try_port} failed: {conn_exc}")

    if camera is None:
        msg = f"ONVIF connect failed on all tried ports {ports_to_try}"
        print(f"PTZ: {msg}")
        return False, msg

    try:
        print("PTZ: creating media service")
        media_service = camera.create_media_service()

        print("PTZ: creating PTZ service")
        ptz_service = camera.create_ptz_service()

        print("PTZ: fetching profiles")
        profiles = media_service.GetProfiles()
        if not profiles:
            print("PTZ: no ONVIF profiles returned by camera")
            return False, "No ONVIF profiles available"

        profile = profiles[0]
        profile_token = profile.token
        print(f"PTZ: using profile token={profile_token!r}")

        move_request = ptz_service.create_type("ContinuousMove")
        move_request.ProfileToken = profile_token
        move_request.Velocity = {
            "PanTilt": {"x": 0.0, "y": 0.0},
            "Zoom": {"x": float(zoom_value)},
        }
        print(f"PTZ: sending ContinuousMove zoom={zoom_value}")
        ptz_service.ContinuousMove(move_request)
        time.sleep(0.3)

        stop_request = ptz_service.create_type("Stop")
        stop_request.ProfileToken = profile_token
        stop_request.PanTilt = True
        stop_request.Zoom = True
        print("PTZ: sending Stop (zoom)")
        ptz_service.Stop(stop_request)
        print("PTZ: zoom command complete")

        try:
            print("PTZ: creating imaging service for focus")
            imaging_service = camera.create_imaging_service()
            source_token = profile.VideoSourceConfiguration.SourceToken
            print(f"PTZ: imaging source token={source_token!r}")
            focus_move = imaging_service.create_type("Move")
            focus_move.VideoSourceToken = source_token
            focus_move.Focus = {"Continuous": {"Speed": float(focus_value)}}
            print(f"PTZ: sending focus Move speed={focus_value}")
            imaging_service.Move(focus_move)
            time.sleep(0.2)
            imaging_service.Stop({"VideoSourceToken": source_token, "Focus": True})
            print("PTZ: focus command complete")
        except Exception as focus_exc:
            print(f"PTZ: focus control skipped (optional, not supported by this camera): {focus_exc}")

        print("PTZ: all commands applied successfully")
        return True, "PTZ command applied"
    except Exception as exc:
        print(f"PTZ: ONVIF command failed: {exc}")
        traceback.print_exc()
        return False, f"ONVIF command failed: {exc}"
