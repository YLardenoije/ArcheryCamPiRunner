"""Persistent per-camera settings keyed by MAC address."""

import json
import os
import threading


class CameraSettingsStore:
    """Store camera settings on disk using MAC addresses as stable keys."""

    def __init__(self, file_path):
        self.file_path = file_path
        self._lock = threading.Lock()
        self._data = {"cameras": {}}
        self._load()

    @staticmethod
    def normalize_mac(mac):
        """Normalize MAC strings into lowercase colon-separated form."""
        value = (mac or "").strip().lower().replace("-", ":")
        parts = [p for p in value.split(":") if p]
        if len(parts) != 6:
            return ""
        for part in parts:
            if len(part) != 2:
                return ""
            try:
                int(part, 16)
            except ValueError:
                return ""
        return ":".join(parts)

    def _load(self):
        with self._lock:
            try:
                if not os.path.exists(self.file_path):
                    return
                with open(self.file_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict) and isinstance(loaded.get("cameras"), dict):
                    self._data = loaded
            except Exception:
                # Keep defaults if the settings file is unreadable.
                self._data = {"cameras": {}}

    def _save(self):
        with self._lock:
            folder = os.path.dirname(self.file_path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, sort_keys=True)

    def get_settings(self, mac):
        key = self.normalize_mac(mac)
        if not key:
            return {}
        return dict(self._data.get("cameras", {}).get(key, {}))

    def set_settings(self, mac, name=None, role=None, zoom=None, focus=None):
        """Create or update camera settings for a MAC address."""
        key = self.normalize_mac(mac)
        if not key:
            return False

        cameras = self._data.setdefault("cameras", {})
        existing = dict(cameras.get(key, {}))

        if name is not None:
            cleaned = str(name).strip()
            if cleaned:
                existing["name"] = cleaned
            elif "name" in existing:
                existing.pop("name", None)

        if role is not None:
            normalized_role = str(role).strip().lower()
            if normalized_role in ("", "none"):
                existing.pop("role", None)
            elif normalized_role in ("primary", "secondary"):
                # Enforce single assignment per role.
                for other_key, camera_data in cameras.items():
                    if other_key == key:
                        continue
                    if camera_data.get("role") == normalized_role:
                        camera_data.pop("role", None)
                existing["role"] = normalized_role

        if zoom is not None or focus is not None:
            ptz = dict(existing.get("ptz", {}))
            if zoom is not None:
                ptz["zoom"] = float(zoom)
            if focus is not None:
                ptz["focus"] = float(focus)
            existing["ptz"] = ptz

        cameras[key] = existing
        self._save()
        return True

    def apply_to_cameras(self, cameras):
        """Apply stored names/roles/ptz settings to discovered cameras in place."""
        for camera in cameras or []:
            mac = self.normalize_mac(camera.get("mac", ""))
            if not mac:
                camera.setdefault("role", "")
                camera.setdefault("ptz", {"zoom": 0.0, "focus": 0.0})
                continue

            saved = self.get_settings(mac)
            if saved.get("name"):
                camera["name"] = saved["name"]
            camera["role"] = saved.get("role", "")
            ptz_saved = saved.get("ptz", {}) or {}
            camera["ptz"] = {
                "zoom": float(ptz_saved.get("zoom", 0.0)),
                "focus": float(ptz_saved.get("focus", 0.0)),
            }

    def choose_startup_camera(self, cameras):
        """Return selected startup camera honoring primary/secondary preferences."""
        if not cameras:
            return None

        by_role = {"primary": None, "secondary": None}
        for camera in cameras:
            role = str(camera.get("role", "")).strip().lower()
            if role in by_role and by_role[role] is None:
                by_role[role] = camera

        if by_role["primary"]:
            return by_role["primary"]
        if by_role["secondary"]:
            return by_role["secondary"]
        return cameras[0]
