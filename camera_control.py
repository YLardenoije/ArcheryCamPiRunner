"""Optional camera control helpers (best-effort ONVIF PTZ zoom/focus)."""

import time


def apply_zoom_focus_onvif(host, zoom_value, focus_value, username="", password="", port=80):
    """Best-effort ONVIF zoom/focus command.

    zoom_value and focus_value are expected in [-1.0, 1.0].
    Returns (success: bool, message: str).
    """
    if not host:
        return False, "Missing host"

    if not username or not password:
        return False, "ONVIF credentials are not configured"

    try:
        from onvif import ONVIFCamera
    except Exception:
        return False, "python-onvif-zeep is not installed"

    try:
        camera = ONVIFCamera(host, int(port), username, password)
        media_service = camera.create_media_service()
        ptz_service = camera.create_ptz_service()

        profiles = media_service.GetProfiles()
        if not profiles:
            return False, "No ONVIF profiles available"

        profile = profiles[0]
        profile_token = profile.token

        move_request = ptz_service.create_type("ContinuousMove")
        move_request.ProfileToken = profile_token
        move_request.Velocity = {
            "PanTilt": {"x": 0.0, "y": 0.0},
            "Zoom": {"x": float(zoom_value)},
        }
        ptz_service.ContinuousMove(move_request)
        time.sleep(0.3)

        stop_request = ptz_service.create_type("Stop")
        stop_request.ProfileToken = profile_token
        stop_request.PanTilt = True
        stop_request.Zoom = True
        ptz_service.Stop(stop_request)

        try:
            imaging_service = camera.create_imaging_service()
            source_token = profile.VideoSourceConfiguration.SourceToken
            focus_move = imaging_service.create_type("Move")
            focus_move.VideoSourceToken = source_token
            focus_move.Focus = {"Continuous": {"Speed": float(focus_value)}}
            imaging_service.Move(focus_move)
            time.sleep(0.2)
            imaging_service.Stop({"VideoSourceToken": source_token, "Focus": True})
        except Exception:
            # Focus control is optional across vendors.
            pass

        return True, "PTZ command applied"
    except Exception as exc:
        return False, f"ONVIF command failed: {exc}"
