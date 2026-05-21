"""Main entry point for the kiosk application."""
import sys
import signal
import threading
import time
import tkinter as tk

import config
from camera_discovery import (
    discover_onvif_ws_cameras,
    discover_rtsp_cameras,
    discover_rtsp_port_scan_cameras,
    discover_rtsp_port_scan_cameras_multi,
)
from vlc_player import VLCPlayer
from gui import KioskGUI
from web_interface import WebInterface

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

    if not discovered_cameras and config.ENABLE_DISCOVERY_FALLBACKS:
        print("Activating fallback 2/2: RTSP subnet port scan")
        if getattr(config, "RTSP_SCAN_SUBNETS", None):
            print(f"RTSP fallback multi-subnet mode: {config.RTSP_SCAN_SUBNETS}")
            discovered_cameras = discover_rtsp_port_scan_cameras_multi(
                subnet_cidrs=config.RTSP_SCAN_SUBNETS,
                ports=config.RTSP_SCAN_PORTS,
                timeout_seconds=config.RTSP_SCAN_FALLBACK_TIMEOUT,
                max_hosts=config.RTSP_SCAN_MAX_HOSTS,
                default_path=config.RTSP_DEFAULT_PATH,
                interface_hint=config.RTSP_SCAN_INTERFACE_HINT,
                require_rtsp_handshake=config.RTSP_SCAN_REQUIRE_RTSP_HANDSHAKE,
                connect_timeout_seconds=config.RTSP_SCAN_CONNECT_TIMEOUT,
                retry_without_handshake=config.RTSP_SCAN_RETRY_WITHOUT_HANDSHAKE,
                path_candidates=config.RTSP_SCAN_PATH_CANDIDATES,
            )
        else:
            discovered_cameras = discover_rtsp_port_scan_cameras(
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
        if discovered_cameras:
            print("Discovered cameras via RTSP scan fallback:")
            for camera in discovered_cameras:
                print(f" - {camera['name']}: {camera['url']}")

    if not discovered_cameras and config.ENABLE_DISCOVERY_FALLBACKS:
        print("No cameras found by zeroconf or fallback methods")
    else:
        if not config.ENABLE_ZEROCONF_DISCOVERY:
            print("Zeroconf discovery disabled")

    boot_rtsp_url = discovered_cameras[0]["url"] if discovered_cameras else ""

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
    )
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    # Start Flask in background thread
    flask_thread = threading.Thread(target=web.run, daemon=True)
    flask_thread.start()

    watchdog_state = {
        "consecutive_failures": 0,
        "restart_in_progress": False,
        "last_restart_ts": 0.0,
    }

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

        try:
            state = vlc_player.player.get_state()
        except Exception as exc:
            print("Watchdog: failed to read VLC state:", exc)
            watchdog_state["consecutive_failures"] += 1
            if watchdog_state["consecutive_failures"] >= threshold:
                _restart_stream_async("state-unavailable")
            return

        state_text = str(state).lower()
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
        else:
            print("No discovered stream available at launch; waiting for a camera selection")

    root.after(100, start_initial_stream)
    root.after(max(1000, int(float(getattr(config, "STREAM_WATCHDOG_INTERVAL_SECONDS", 5)) * 1000)), _watchdog_tick)
    
    # Start Tkinter main loop
    root.mainloop()
