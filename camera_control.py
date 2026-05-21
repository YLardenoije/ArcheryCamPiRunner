"""Optional camera control helpers (best-effort ONVIF PTZ zoom/focus)."""

import time
import traceback

# Ports to probe when the configured port fails to return a valid ONVIF response.
# Many cameras serve an HTML admin page on 80 while ONVIF is on 8080 / 2020 etc.
_ONVIF_FALLBACK_PORTS = [8080, 2020, 8000, 8899, 80]
_UNRELIABLE_STATUS_HOSTS = set()


def _try_get_zoom_pos(ptz_service, profile_token):
    """Return current normalised zoom position [0..1] or None if unavailable."""
    try:
        status = ptz_service.GetStatus({"ProfileToken": profile_token})
        if status is None or status.Position is None or status.Position.Zoom is None:
            return None
        return float(status.Position.Zoom.x)
    except Exception as exc:
        print(f"PTZ: GetStatus failed: {exc}")
        return None


def _connect_onvif(ONVIFCamera, host, port, username, password):
    """Create ONVIFCamera on *port* and return it, or raise on failure."""
    print(f"PTZ: trying ONVIF connect to {host}:{port}")
    return ONVIFCamera(host, int(port), username, password)


def apply_zoom_focus_onvif(
    host,
    zoom_value,
    focus_value,
    username="",
    password="",
    port=80,
    zoom_range_seconds=5.0,
    focus_range_seconds=3.0,
    zoom_in_speed=0.5,
    apply_zoom=True,
    apply_focus=True,
    **_ignored,
):
    """Simulated-absolute ONVIF zoom/focus.

    zoom_value and focus_value are in [0.0, 1.0] (absolute position).
    zoom  0.0 = widest / 1.0 = most zoomed in.
    focus 0.0 = nearest / 1.0 = farthest (infinity).

    Simulates absolute positioning by:
      1. Zooming fully out  (ContinuousMove zoom=-1 for zoom_range_seconds).
      2. Zooming in for     zoom_value * zoom_range_seconds.
    Same pattern applied for focus.  Only needs to be run once per position.
    Returns (success: bool, message: str).
    """
    print(f"PTZ: apply_zoom_focus_onvif host={host!r} port={port} zoom={zoom_value} focus={focus_value} apply_zoom={apply_zoom} apply_focus={apply_focus} has_creds={bool(username and password)}")

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

        if apply_zoom:
            stop_req = ptz_service.create_type("Stop")
            stop_req.ProfileToken = profile_token
            stop_req.PanTilt = False
            stop_req.Zoom = True

            zoom_move = ptz_service.create_type("ContinuousMove")
            zoom_move.ProfileToken = profile_token
            zoom_move.Velocity = {"PanTilt": {"x": 0.0, "y": 0.0}, "Zoom": {"x": -1.0}}

            safe_zoom_in_speed = max(0.05, min(1.0, float(zoom_in_speed)))
            initial_pos = _try_get_zoom_pos(ptz_service, profile_token)
            print(f"PTZ: GetStatus initial zoom position={initial_pos}")
            host_key = f"{host}:{try_port}"
            if host_key in _UNRELIABLE_STATUS_HOSTS:
                print(f"PTZ: GetStatus previously marked unreliable for {host_key}; skipping feedback mode")
                use_feedback = False
            else:
                use_feedback = initial_pos is not None
            fallback_due_to_stuck_status = False

            if use_feedback:
                # --- Feedback mode: stop on reported position, but detect stale status and bail out. ---
                deadline = time.time() + float(zoom_range_seconds) * 2.5
                print("PTZ: zoom out to wide end (feedback mode)...")
                ptz_service.ContinuousMove(zoom_move)
                while time.time() < deadline:
                    pos = _try_get_zoom_pos(ptz_service, profile_token)
                    if pos is None or pos <= 0.02:
                        break
                    time.sleep(0.1)
                ptz_service.Stop(stop_req)

                if zoom_value > 0.01:
                    zoom_move.Velocity["Zoom"]["x"] = 1.0
                    deadline = time.time() + float(zoom_range_seconds) * 2.5
                    print(f"PTZ: zoom in to {zoom_value:.4f} (feedback mode)...")
                    ptz_service.ContinuousMove(zoom_move)

                    stagnant_reads = 0
                    last_pos = _try_get_zoom_pos(ptz_service, profile_token)
                    while time.time() < deadline:
                        pos = _try_get_zoom_pos(ptz_service, profile_token)
                        if pos is None:
                            fallback_due_to_stuck_status = True
                            print("PTZ: feedback aborted; GetStatus unavailable during move")
                            break
                        if pos >= zoom_value - 0.02:
                            break

                        if last_pos is not None and abs(pos - last_pos) < 0.001:
                            stagnant_reads += 1
                        else:
                            stagnant_reads = 0
                        last_pos = pos

                        if stagnant_reads >= 10:
                            fallback_due_to_stuck_status = True
                            _UNRELIABLE_STATUS_HOSTS.add(host_key)
                            print("PTZ: feedback aborted; GetStatus appears stuck")
                            break
                        time.sleep(0.1)
                    ptz_service.Stop(stop_req)

                final = _try_get_zoom_pos(ptz_service, profile_token)
                print(f"PTZ: zoom positioning complete (feedback, final={final})")

            if (not use_feedback) or fallback_due_to_stuck_status:
                # --- Timing fallback: zoom out for fixed time, then zoom in proportionally ---
                print(f"PTZ: zoom reset — fully out at speed=1.0 ({zoom_range_seconds:.1f}s, timing fallback)")
                zoom_move.Velocity["Zoom"]["x"] = -1.0
                ptz_service.ContinuousMove(zoom_move)
                time.sleep(float(zoom_range_seconds))
                ptz_service.Stop(stop_req)

                if zoom_value > 0.01:
                    zoom_in_time = float(zoom_value) * float(zoom_range_seconds) / safe_zoom_in_speed
                    zoom_move.Velocity["Zoom"]["x"] = safe_zoom_in_speed
                    print(f"PTZ: zoom in {zoom_value:.4f} at speed {safe_zoom_in_speed} ({zoom_in_time:.1f}s, timing fallback)")
                    ptz_service.ContinuousMove(zoom_move)
                    time.sleep(zoom_in_time)
                    ptz_service.Stop(stop_req)

                print("PTZ: zoom positioning complete (timing fallback)")

        if apply_focus:
            try:
                print("PTZ: creating imaging service for focus")
                imaging_service = camera.create_imaging_service()
                source_token = profile.VideoSourceConfiguration.SourceToken
                print(f"PTZ: imaging source token={source_token!r}")
                focus_move = imaging_service.create_type("Move")
                focus_move.VideoSourceToken = source_token
                # Step 3 – focus fully near to get a known starting position.
                focus_move.Focus = {"Continuous": {"Speed": -1.0}}
                print(f"PTZ: simulated-absolute focus — fully near ({focus_range_seconds:.1f}s)")
                imaging_service.Move(focus_move)
                time.sleep(float(focus_range_seconds))
                imaging_service.Stop({"VideoSourceToken": source_token, "Focus": True})
                # Step 4 – focus out proportionally.
                if focus_value > 0.01:
                    focus_in_time = float(focus_value) * float(focus_range_seconds)
                    focus_move.Focus = {"Continuous": {"Speed": 1.0}}
                    print(f"PTZ: simulated-absolute focus — out {focus_value:.2f} ({focus_in_time:.1f}s)")
                    imaging_service.Move(focus_move)
                    time.sleep(focus_in_time)
                    imaging_service.Stop({"VideoSourceToken": source_token, "Focus": True})
                print("PTZ: focus positioning complete")
            except Exception as focus_exc:
                print(f"PTZ: focus control skipped (optional, not supported by this camera): {focus_exc}")

        print("PTZ: all commands applied successfully")
        return True, "PTZ command applied"
    except Exception as exc:
        print(f"PTZ: ONVIF command failed: {exc}")
        traceback.print_exc()
        return False, f"ONVIF command failed: {exc}"
