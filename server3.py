"""Main entry point for the kiosk application."""
import sys
import signal
import threading
import time
import tkinter as tk

import config
from camera_control import apply_zoom_focus_onvif
from camera_settings import CameraSettingsStore
from camera_discovery import (
    discover_onvif_ws_cameras,
    discover_rtsp_cameras,
    discover_rtsp_port_scan_cameras,
    discover_rtsp_port_scan_cameras_multi,
    resolve_mac_for_host,
)
from vlc_player import VLCPlayer
from gui import KioskGUI
from web_interface import WebInterface


def _merge_cameras(base_cameras, extra_cameras):
    """Merge camera lists by URL while preserving existing metadata."""
    merged = list(base_cameras or [])
    by_url = {}
    for camera in merged:
        url = (camera.get("url") or "").strip()
        if url:
            by_url[url] = camera

    for camera in extra_cameras or []:
        url = (camera.get("url") or "").strip()
        if not url:
            continue

        if url in by_url:
            existing = by_url[url]
            # Preserve user naming/roles from earlier sources, but fill gaps.
            for key in ("host", "port", "service_type", "source"):
                if not existing.get(key) and camera.get(key):
                    existing[key] = camera.get(key)
            continue

        by_url[url] = camera
        merged.append(camera)

    return merged

def shutdown(*args):
    """Shutdown the application gracefully."""
    print("Shutting down...")
    try:
        vlc_player.stop()
    except:
        pass
    root.destroy()
    sys.exit(0)
if __name__ == "__main__":
    settings_store = CameraSettingsStore(config.CAMERA_SETTINGS_FILE)
    discovered_cameras = []
    if config.ENABLE_ZEROCONF_DISCOVERY:
        print(
            "Zeroconf discovery enabled for service types:",
            ", ".join(config.ZEROCONF_SERVICE_TYPES),
            f"(timeout={config.ZEROCONF_DISCOVERY_TIMEOUT}s)",
        )
        discovered_cameras = discover_rtsp_cameras(
            config.ZEROCONF_SERVICE_TYPES,
            timeout_seconds=config.ZEROCONF_DISCOVERY_TIMEOUT,
            default_path=config.RTSP_DEFAULT_PATH,
        )
        if discovered_cameras:
            print("Discovered RTSP cameras via zeroconf:")
            for camera in discovered_cameras:
                print(f" - {camera['name']}: {camera['url']}")
        else:
            print("No zeroconf RTSP cameras discovered on launch; check whether the cameras advertise mDNS/zeroconf services")

    if not discovered_cameras and config.ENABLE_DISCOVERY_FALLBACKS:
        print("Activating fallback 1/2: ONVIF WS-Discovery")
        discovered_cameras = discover_onvif_ws_cameras(
            timeout_seconds=config.ONVIF_FALLBACK_TIMEOUT,
            default_path=config.RTSP_DEFAULT_PATH,
        )
        if discovered_cameras:
            print("Discovered cameras via ONVIF WS-Discovery fallback:")
            for camera in discovered_cameras:
                print(f" - {camera['name']}: {camera['url']}")

    scan_always_merge = bool(getattr(config, "RTSP_SCAN_ALWAYS_MERGE", False))
    if config.ENABLE_DISCOVERY_FALLBACKS and (scan_always_merge or not discovered_cameras):
        print("Activating fallback 2/2: RTSP subnet port scan")
        scan_passes = max(1, int(getattr(config, "RTSP_SCAN_BOOT_PASSES", 1)))
        scan_delay = max(0.0, float(getattr(config, "RTSP_SCAN_BOOT_PASS_DELAY_SECONDS", 1.0)))

        for pass_idx in range(scan_passes):
            if pass_idx > 0 and scan_delay > 0.0:
                print(f"RTSP boot rescan waiting {scan_delay:.1f}s before pass {pass_idx + 1}/{scan_passes}")
                time.sleep(scan_delay)

            if getattr(config, "RTSP_SCAN_SUBNETS", None):
                print(f"RTSP fallback multi-subnet mode (pass {pass_idx + 1}/{scan_passes}): {config.RTSP_SCAN_SUBNETS}")
                scanned = discover_rtsp_port_scan_cameras_multi(
                    subnet_cidrs=config.RTSP_SCAN_SUBNETS,
                    ports=config.RTSP_SCAN_PORTS,
                    timeout_seconds=config.RTSP_SCAN_FALLBACK_TIMEOUT,
                    max_hosts=config.RTSP_SCAN_MAX_HOSTS,
                    default_path=config.RTSP_DEFAULT_PATH,
                    interface_hint=config.RTSP_SCAN_INTERFACE_HINT,
                    require_rtsp_handshake=config.RTSP_SCAN_REQUIRE_RTSP_HANDSHAKE,
                    connect_timeout_seconds=config.RTSP_SCAN_CONNECT_TIMEOUT,
                    retry_without_handshake=config.RTSP_SCAN_RETRY_WITHOUT_HANDSHAKE,
                    retry_without_handshake_always=getattr(config, "RTSP_SCAN_RETRY_WITHOUT_HANDSHAKE_ALWAYS", True),
                    path_candidates=config.RTSP_SCAN_PATH_CANDIDATES,
                )
            else:
                scanned = discover_rtsp_port_scan_cameras(
                    subnet_cidr=config.RTSP_SCAN_SUBNET,
                    ports=config.RTSP_SCAN_PORTS,
                    timeout_seconds=config.RTSP_SCAN_FALLBACK_TIMEOUT,
                    max_hosts=config.RTSP_SCAN_MAX_HOSTS,
                    default_path=config.RTSP_DEFAULT_PATH,
                    interface_hint=config.RTSP_SCAN_INTERFACE_HINT,
                    require_rtsp_handshake=config.RTSP_SCAN_REQUIRE_RTSP_HANDSHAKE,
                    connect_timeout_seconds=config.RTSP_SCAN_CONNECT_TIMEOUT,
                    path_candidates=config.RTSP_SCAN_PATH_CANDIDATES,
                )

            before = len(discovered_cameras)
            discovered_cameras = _merge_cameras(discovered_cameras, scanned)
            added = len(discovered_cameras) - before
            print(f"RTSP scan pass {pass_idx + 1}/{scan_passes}: found={len(scanned)} added={added} total={len(discovered_cameras)}")

        if discovered_cameras:
            print("Discovered cameras after RTSP scan merge:")
            for camera in discovered_cameras:
                print(f" - {camera['name']}: {camera['url']}")

    if not discovered_cameras and config.ENABLE_DISCOVERY_FALLBACKS:
        print("No cameras found by zeroconf or fallback methods")
    else:
        if not config.ENABLE_ZEROCONF_DISCOVERY:
            print("Zeroconf discovery disabled")

    for camera in discovered_cameras:
        host = camera.get("host", "")
        camera["mac"] = resolve_mac_for_host(host)

    settings_store.apply_to_cameras(discovered_cameras)
    startup_camera = settings_store.choose_startup_camera(discovered_cameras)
    boot_rtsp_url = startup_camera.get("url", "") if startup_camera else ""

    if startup_camera:
        print(
            "Startup camera selected:",
            startup_camera.get("name", "camera"),
            startup_camera.get("url", ""),
            f"(role={startup_camera.get('role', 'none')}, mac={startup_camera.get('mac', '')})",
        )

    # Create Tkinter root window
    root = tk.Tk()
    
    # Initialize VLC player
    vlc_player = VLCPlayer()
    
    # Initialize GUI
    gui = KioskGUI(root, vlc_player)
    
    # Initialize web interface
    web = WebInterface(
        gui,
        vlc_player,
        shutdown,
        initial_rtsp_url=boot_rtsp_url,
        initial_cameras=discovered_cameras,
        settings_store=settings_store,
        apply_ptz_fn=lambda camera, zoom, focus, **kwargs: apply_zoom_focus_onvif(
            camera.get("host", ""),
            zoom,
            focus,
            username=config.ONVIF_USERNAME,
            password=config.ONVIF_PASSWORD,
            port=config.ONVIF_PORT,
            zoom_range_seconds=getattr(config, "ONVIF_FULL_ZOOM_TIME_SECONDS", 5.0),
            focus_range_seconds=getattr(config, "ONVIF_FULL_FOCUS_TIME_SECONDS", 3.0),
            zoom_in_speed=getattr(config, "ONVIF_ZOOM_IN_SPEED", 1.0),
            zoom_reset_seconds=getattr(config, "ONVIF_FULL_ZOOM_RESET_TIME_SECONDS", getattr(config, "ONVIF_FULL_ZOOM_TIME_SECONDS", 5.0)),
            zoom_in_full_seconds=getattr(config, "ONVIF_FULL_ZOOM_IN_TIME_SECONDS", getattr(config, "ONVIF_FULL_ZOOM_TIME_SECONDS", 5.0)),
            zoom_final_nudge_seconds=getattr(config, "ONVIF_ZOOM_FINAL_NUDGE_SECONDS", 0.0),
            zoom_final_nudge_pause_seconds=getattr(config, "ONVIF_ZOOM_FINAL_NUDGE_PAUSE_SECONDS", 0.2),
            use_status_feedback=getattr(config, "ONVIF_USE_STATUS_FEEDBACK", True),
            **kwargs,
        ),
    )
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    # Start Flask in background thread
    flask_thread = threading.Thread(target=web.run, daemon=True)
    flask_thread.start()

    def _discovery_refresh_loop():
        if not getattr(config, "DISCOVERY_REFRESH_ENABLED", True):
            return
        if not config.ENABLE_DISCOVERY_FALLBACKS:
            return

        attempts = max(1, int(getattr(config, "DISCOVERY_REFRESH_ATTEMPTS", 6)))
        interval = max(1.0, float(getattr(config, "DISCOVERY_REFRESH_INTERVAL_SECONDS", 20.0)))

        for attempt in range(1, attempts + 1):
            time.sleep(interval)
            try:
                if getattr(config, "RTSP_SCAN_SUBNETS", None):
                    print(f"Discovery refresh {attempt}/{attempts}: scanning {config.RTSP_SCAN_SUBNETS}")
                    scanned = discover_rtsp_port_scan_cameras_multi(
                        subnet_cidrs=config.RTSP_SCAN_SUBNETS,
                        ports=config.RTSP_SCAN_PORTS,
                        timeout_seconds=config.RTSP_SCAN_FALLBACK_TIMEOUT,
                        max_hosts=config.RTSP_SCAN_MAX_HOSTS,
                        default_path=config.RTSP_DEFAULT_PATH,
                        interface_hint=config.RTSP_SCAN_INTERFACE_HINT,
                        require_rtsp_handshake=config.RTSP_SCAN_REQUIRE_RTSP_HANDSHAKE,
                        connect_timeout_seconds=config.RTSP_SCAN_CONNECT_TIMEOUT,
                        retry_without_handshake=config.RTSP_SCAN_RETRY_WITHOUT_HANDSHAKE,
                        retry_without_handshake_always=getattr(config, "RTSP_SCAN_RETRY_WITHOUT_HANDSHAKE_ALWAYS", True),
                        path_candidates=config.RTSP_SCAN_PATH_CANDIDATES,
                    )
                else:
                    scanned = discover_rtsp_port_scan_cameras(
                        subnet_cidr=config.RTSP_SCAN_SUBNET,
                        ports=config.RTSP_SCAN_PORTS,
                        timeout_seconds=config.RTSP_SCAN_FALLBACK_TIMEOUT,
                        max_hosts=config.RTSP_SCAN_MAX_HOSTS,
                        default_path=config.RTSP_DEFAULT_PATH,
                        interface_hint=config.RTSP_SCAN_INTERFACE_HINT,
                        require_rtsp_handshake=config.RTSP_SCAN_REQUIRE_RTSP_HANDSHAKE,
                        connect_timeout_seconds=config.RTSP_SCAN_CONNECT_TIMEOUT,
                        path_candidates=config.RTSP_SCAN_PATH_CANDIDATES,
                    )

                before = len(web.camera_choices)
                merged = _merge_cameras(web.camera_choices, scanned)
                added = len(merged) - before
                if added > 0:
                    for camera in merged:
                        host = camera.get("host", "")
                        if host and not camera.get("mac"):
                            camera["mac"] = resolve_mac_for_host(host)
                    settings_store.apply_to_cameras(merged)
                    web.update_cameras(merged, selected_url=web.rtsp_url)
                    print(f"Discovery refresh {attempt}/{attempts}: added={added} total={len(merged)}")
                else:
                    print(f"Discovery refresh {attempt}/{attempts}: no new cameras")
            except Exception as exc:
                print(f"Discovery refresh {attempt}/{attempts} error: {exc}")

    threading.Thread(target=_discovery_refresh_loop, daemon=True).start()

    watchdog_state = {
        "consecutive_failures": 0,
        "restart_in_progress": False,
        "last_restart_ts": 0.0,
    }

    # VLC state is polled on a dedicated background thread so that a blocked/deadlocked
    # libvlc call never freezes the Tk main event loop.
    _vlc_state_cache = {"state_text": "unknown", "updated_at": 0.0}
    _vlc_state_lock = threading.Lock()

    def _vlc_state_poller():
        """Background thread: polls VLC state every 2 s and caches the result."""
        while True:
            time.sleep(2)
            try:
                state = vlc_player.player.get_state()
                state_text = str(state).lower()
            except Exception:
                state_text = "error"
            with _vlc_state_lock:
                _vlc_state_cache["state_text"] = state_text
                _vlc_state_cache["updated_at"] = time.time()

    threading.Thread(target=_vlc_state_poller, daemon=True).start()

    def _current_stream_url():
        return (getattr(web, "rtsp_url", "") or "").strip()

    def _restart_stream_async(reason):
        url = _current_stream_url()
        if not url:
            return

        if watchdog_state["restart_in_progress"]:
            return

        watchdog_state["restart_in_progress"] = True

        def _do_restart():
            try:
                print(f"Watchdog: restarting stream ({reason}) -> {url}")
                try:
                    vlc_player.stop()
                except Exception:
                    pass
                time.sleep(0.3)
                win_id = gui.get_video_container_id()
                vlc_player.embed_to_window(win_id)
                vlc_player.start_media(url)
                watchdog_state["last_restart_ts"] = time.time()
                watchdog_state["consecutive_failures"] = 0
            except Exception as exc:
                print("Watchdog: restart failed:", exc)
            finally:
                watchdog_state["restart_in_progress"] = False

        threading.Thread(target=_do_restart, daemon=True).start()

    def _watchdog_tick():
        if not getattr(config, "STREAM_WATCHDOG_ENABLED", True):
            return

        interval_ms = max(1000, int(float(getattr(config, "STREAM_WATCHDOG_INTERVAL_SECONDS", 5)) * 1000))
        threshold = max(1, int(getattr(config, "STREAM_WATCHDOG_FAILURE_THRESHOLD", 3)))
        root.after(interval_ms, _watchdog_tick)

        if gui.is_showing_image:
            watchdog_state["consecutive_failures"] = 0
            return

        url = _current_stream_url()
        if not url:
            watchdog_state["consecutive_failures"] = 0
            return

        # Read the cached state written by _vlc_state_poller (off main thread).
        # If the cache is stale (poller itself blocked > 15 s), treat as error.
        with _vlc_state_lock:
            state_text = _vlc_state_cache["state_text"]
            cache_age = time.time() - _vlc_state_cache["updated_at"]

        if cache_age > 15:
            state_text = "error"
            print(f"Watchdog: VLC state cache stale ({cache_age:.0f}s) — treating as error")
        if "playing" in state_text or "opening" in state_text or "buffering" in state_text:
            watchdog_state["consecutive_failures"] = 0
            return

        if "error" in state_text or "ended" in state_text or "stopped" in state_text:
            watchdog_state["consecutive_failures"] += 1
            print(
                "Watchdog: unhealthy VLC state",
                state,
                f"({watchdog_state['consecutive_failures']}/{threshold})",
            )
            if watchdog_state["consecutive_failures"] >= threshold:
                _restart_stream_async(f"state={state}")
        else:
            # Unknown/idle states are tolerated briefly.
            watchdog_state["consecutive_failures"] += 1
            if watchdog_state["consecutive_failures"] >= threshold:
                _restart_stream_async(f"unknown-state={state}")
    
    # Embed VLC and start streaming
    def start_initial_stream():
        gui.embed_vlc()
        if boot_rtsp_url:
            vlc_player.start_media(boot_rtsp_url)

            if startup_camera and bool(getattr(config, "BOOT_REAPPLY_ZOOM_ON_STARTUP", True)):
                def _boot_reapply_zoom():
                    try:
                        delay = max(0.0, float(getattr(config, "BOOT_REAPPLY_ZOOM_DELAY_SECONDS", 2.0)))
                        attempts = max(1, int(getattr(config, "BOOT_REAPPLY_ZOOM_ATTEMPTS", 2)))
                        retry_delay = max(0.0, float(getattr(config, "BOOT_REAPPLY_ZOOM_RETRY_DELAY_SECONDS", 5.0)))
                        print(
                            "Boot PTZ reapply scheduled:",
                            f"delay={delay:.1f}s",
                            f"attempts={attempts}",
                            f"retry_delay={retry_delay:.1f}s",
                        )
                        if delay > 0.0:
                            time.sleep(delay)

                        ptz = startup_camera.get("ptz", {}) or {}
                        zoom = max(0.0, min(1.0, float(ptz.get("zoom", 0.0))))
                        focus = max(0.0, min(1.0, float(ptz.get("focus", 0.0))))
                        print(
                            "Boot PTZ reapply target:",
                            f"camera={startup_camera.get('name', 'camera')}",
                            f"host={startup_camera.get('host', '')}",
                            f"zoom={zoom:.4f}",
                        )

                        for attempt in range(1, attempts + 1):
                            if attempt > 1 and retry_delay > 0.0:
                                time.sleep(retry_delay)

                            print(f"Boot PTZ reapply attempt {attempt}/{attempts}")
                            ok, msg = web._apply_ptz(
                                startup_camera,
                                zoom,
                                focus,
                                apply_zoom=True,
                                apply_focus=False,
                            )
                            print("Boot PTZ reapply:", "ok" if ok else "failed", msg)
                            if ok:
                                break
                    except Exception as exc:
                        print(f"Boot PTZ reapply error: {exc}")

                threading.Thread(target=_boot_reapply_zoom, daemon=True).start()
            elif startup_camera:
                print("Boot PTZ reapply skipped: disabled by config")
            else:
                print("Boot PTZ reapply skipped: no startup camera selected")
        else:
            print("No discovered stream available at launch; waiting for a camera selection")

    root.after(100, start_initial_stream)
    root.after(max(1000, int(float(getattr(config, "STREAM_WATCHDOG_INTERVAL_SECONDS", 5)) * 1000)), _watchdog_tick)
    
    # Start Tkinter main loop
    root.mainloop()
