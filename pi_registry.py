"""Persistent registry for multi-Pi dashboard entries keyed by MAC address."""

import json
import os
import threading


class PiRegistryStore:
    """Store registered kiosk Pis on disk using MAC addresses as stable keys."""

    def __init__(self, file_path):
        self.file_path = file_path
        self._lock = threading.Lock()
        self._data = {"pis": {}}
        self._load()

    @staticmethod
    def normalize_mac(mac):
        """Normalize MAC strings into lowercase colon-separated form."""
        value = (mac or "").strip().lower().replace("-", ":")
        parts = [part for part in value.split(":") if part]
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

    @staticmethod
    def _clean_url(url):
        return (url or "").strip().rstrip("/")

    def _load(self):
        with self._lock:
            try:
                if not os.path.exists(self.file_path):
                    return
                with open(self.file_path, "r", encoding="utf-8") as handle:
                    loaded = json.load(handle)
                if isinstance(loaded, dict) and isinstance(loaded.get("pis"), dict):
                    self._data = loaded
            except Exception:
                self._data = {"pis": {}}

    def _save(self):
        with self._lock:
            folder = os.path.dirname(self.file_path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle, indent=2, sort_keys=True)

    def get_pi(self, mac):
        key = self.normalize_mac(mac)
        if not key:
            return {}
        return dict(self._data.get("pis", {}).get(key, {}))

    def list_pis(self):
        pis = []
        for key, record in self._data.get("pis", {}).items():
            item = dict(record)
            item["mac"] = key
            item["name"] = item.get("name") or key
            item["api_base_url"] = self._clean_url(item.get("api_base_url", ""))
            item["ui_url"] = self._clean_url(item.get("ui_url") or item["api_base_url"])
            pis.append(item)
        pis.sort(key=lambda item: (item.get("name", "").lower(), item.get("mac", "")))
        return pis

    def upsert_pi(self, mac, name=None, api_base_url=None, ui_url=None):
        key = self.normalize_mac(mac)
        if not key:
            return False

        pis = self._data.setdefault("pis", {})
        existing = dict(pis.get(key, {}))
        existing["mac"] = key

        if name is not None:
            cleaned_name = str(name).strip()
            if cleaned_name:
                existing["name"] = cleaned_name
            else:
                existing.pop("name", None)

        if api_base_url is not None:
            cleaned_api = self._clean_url(api_base_url)
            if cleaned_api:
                existing["api_base_url"] = cleaned_api
            else:
                existing.pop("api_base_url", None)

        if ui_url is not None:
            cleaned_ui = self._clean_url(ui_url)
            if cleaned_ui:
                existing["ui_url"] = cleaned_ui
            else:
                existing.pop("ui_url", None)

        if "ui_url" not in existing and existing.get("api_base_url"):
            existing["ui_url"] = existing["api_base_url"]

        pis[key] = existing
        self._save()
        return True

    def rename_pi(self, mac, new_name):
        key = self.normalize_mac(mac)
        if not key:
            return False
        if key not in self._data.setdefault("pis", {}):
            return False
        cleaned_name = str(new_name).strip()
        if not cleaned_name:
            return False
        self._data["pis"][key]["name"] = cleaned_name
        self._save()
        return True

    def remove_pi(self, mac):
        key = self.normalize_mac(mac)
        if not key:
            return False
        removed = self._data.setdefault("pis", {}).pop(key, None)
        if removed is None:
            return False
        self._save()
        return True
