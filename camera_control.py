"""Optional camera control helpers (best-effort ONVIF PTZ zoom/focus)."""

import time
import traceback


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

    try:
        print(f"PTZ: connecting to camera {host}:{port}")
        camera = ONVIFCamera(host, int(port), username, password)

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
