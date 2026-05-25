"""Visual multi-Pi dashboard for remote kiosk control."""

import json
import ipaddress
import re
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from flask import Flask, jsonify, render_template_string, request

import config
from camera_discovery import resolve_mac_for_host
from pi_registry import PiRegistryStore


DASHBOARD_HTML = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pi Control Board</title>
<style>
:root{
  --bg:#08111f;
  --bg2:#0f1d31;
  --panel:#0f1726;
  --panel2:#15233a;
  --text:#eef4ff;
  --muted:#93a4c3;
  --line:rgba(255,255,255,.09);
  --accent:#ffb545;
  --accent2:#69e0c0;
  --danger:#ff6b6b;
  --good:#6ce28f;
}
*{box-sizing:border-box}
body{
  margin:0;
  color:var(--text);
  font-family:"Trebuchet MS","Segoe UI",sans-serif;
  background:
    radial-gradient(circle at top left, rgba(255,181,69,.18), transparent 24%),
    radial-gradient(circle at top right, rgba(105,224,192,.14), transparent 25%),
    linear-gradient(160deg, var(--bg), var(--bg2));
  min-height:100vh;
}
.container{max-width:1320px;margin:0 auto;padding:24px}
.hero{
  display:flex;align-items:flex-end;justify-content:space-between;gap:16px;
  padding:24px;border:1px solid var(--line);border-radius:24px;
  background:rgba(10,18,31,.78);backdrop-filter:blur(10px);
  box-shadow:0 18px 44px rgba(0,0,0,.28);
}
.hero h1{margin:0;font-size:2rem;letter-spacing:.02em}
.hero p{margin:.35rem 0 0;color:var(--muted);max-width:62ch;line-height:1.45}
.badge{
  display:inline-flex;align-items:center;gap:8px;padding:8px 12px;border-radius:999px;
  background:rgba(255,255,255,.06);border:1px solid var(--line);color:var(--muted);font-size:.92rem;
}
.grid{display:grid;grid-template-columns:1.05fr .95fr;gap:18px;margin-top:18px}
.card{
  border:1px solid var(--line);border-radius:22px;background:rgba(10,18,31,.72);
  box-shadow:0 16px 38px rgba(0,0,0,.22);overflow:hidden;
}
.card header{padding:18px 18px 0}
.card h2{margin:0 0 8px;font-size:1.1rem}
.card .sub{color:var(--muted);font-size:.92rem;line-height:1.4}
.card .body{padding:18px}
.toolbar{display:flex;flex-wrap:wrap;gap:10px;margin-top:14px}
button,.button,
input[type=text],input[type=url],input[type=number],textarea{
  border-radius:14px;border:1px solid var(--line);background:var(--panel2);color:var(--text);
  padding:11px 14px;font:inherit;
}
button,.button{cursor:pointer;font-weight:700;transition:transform .12s ease, border-color .12s ease, background .12s ease}
button:hover,.button:hover{transform:translateY(-1px);border-color:rgba(255,255,255,.18)}
button.primary{background:linear-gradient(135deg, var(--accent), #ff9d3f);color:#221400;border:none}
button.secondary{background:linear-gradient(135deg, rgba(105,224,192,.92), rgba(80,180,255,.75));color:#07141a;border:none}
button.ghost{background:transparent}
button.danger{background:linear-gradient(135deg, rgba(255,107,107,.95), rgba(204,69,69,.92));color:#220909;border:none}
.pi-form{display:grid;grid-template-columns:1.2fr 1.2fr 1fr auto;gap:10px}
.pi-list{display:flex;flex-direction:column;gap:12px}
.pi{padding:16px;border:1px solid var(--line);border-radius:18px;background:rgba(255,255,255,.03)}
.pi-top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}
.pi-name{font-size:1.05rem;font-weight:700}
.pi-meta{color:var(--muted);font-size:.88rem;margin-top:3px;word-break:break-word}
.pi-status{padding:6px 10px;border-radius:999px;font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em}
.pi-status.online{background:rgba(108,226,143,.16);color:var(--good);border:1px solid rgba(108,226,143,.22)}
.pi-status.offline{background:rgba(255,107,107,.12);color:var(--danger);border:1px solid rgba(255,107,107,.24)}
.pi-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.small{font-size:.85rem;color:var(--muted)}
textarea{min-height:130px;resize:vertical;width:100%}
.stack{display:grid;gap:10px}
.two-col{display:grid;grid-template-columns:1fr 140px;gap:10px}
.state-line{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.state-pill{padding:6px 10px;border:1px solid var(--line);border-radius:999px;background:rgba(255,255,255,.04);font-size:.85rem;color:var(--muted)}
@media (max-width: 1080px){.grid{grid-template-columns:1fr}.pi-form{grid-template-columns:1fr 1fr;}.pi-form button{grid-column:1/-1}}
@media (max-width: 720px){.hero{flex-direction:column;align-items:flex-start}.pi-form,.two-col{grid-template-columns:1fr}.toolbar{display:grid;grid-template-columns:1fr 1fr}.toolbar button{width:100%}}
</style>
</head>
<body>
<div class="container">
  <section class="hero">
    <div>
      <span class="badge">Multi-Pi Control Board</span>
      <h1>Broadcast commands, rename Pis by MAC, and run synchronized commercials.</h1>
      <p>Register each Raspberry Pi once using its MAC address. From here you can open its remote UI, push stream-role switches, trigger updates, and loop the same commercial image set across the whole fleet.</p>
    </div>
    <div class="badge" id="dashboard-summary">{{ pis|length }} registered Pis</div>
  </section>

  <div class="grid">
    <section class="card">
      <header>
        <h2>Registered Pis</h2>
        <div class="sub">Each Pi is stored by MAC address so names survive IP changes and DHCP churn.</div>
      </header>
      <div class="body">
        <form class="pi-form" onsubmit="return registerPi(event)">
          <input type="text" name="mac" placeholder="AA:BB:CC:DD:EE:FF" required>
          <input type="text" name="name" placeholder="Friendly name">
          <input type="url" name="api_base_url" placeholder="http://192.168.1.50:8080" required>
          <button class="primary" type="submit">Register Pi</button>
        </form>

        <div class="toolbar">
          <button class="secondary" type="button" onclick="discoverPis()">Discover Pis</button>
          <button class="secondary" type="button" onclick="broadcastCommand('show_stream')">Show Stream All</button>
          <button class="secondary" type="button" onclick="broadcastCommand('update')">Update All</button>
          <button class="secondary" type="button" onclick="broadcastCommand('primary')">Switch All to Primary</button>
          <button class="secondary" type="button" onclick="broadcastCommand('secondary')">Switch All to Secondary</button>
          <button class="ghost" type="button" onclick="refreshPis()">Refresh Status</button>
        </div>

        <div class="pi-list" id="pi-list">
          {% for pi in pis %}
          <article class="pi" data-mac="{{ pi.mac }}" data-ui-url="{{ pi.ui_url }}">
            <div class="pi-top">
              <div>
                <div class="pi-name">{{ pi.name }}</div>
                <div class="pi-meta">MAC: {{ pi.mac }}</div>
                <div class="pi-meta">API: {{ pi.api_base_url }}</div>
                <div class="pi-meta">UI: {{ pi.ui_url }}</div>
              </div>
              <div class="pi-status {{ 'online' if pi.online else 'offline' }}">{{ 'online' if pi.online else 'offline' }}</div>
            </div>
            <div class="pi-actions">
              <button type="button" onclick="openUi('{{ pi.mac }}')">Open UI</button>
              <button type="button" onclick="commandPi('{{ pi.mac }}', 'show_stream')">Show Stream</button>
              <button type="button" onclick="commandPi('{{ pi.mac }}', 'primary')">Primary</button>
              <button type="button" onclick="commandPi('{{ pi.mac }}', 'secondary')">Secondary</button>
              <button type="button" onclick="commandPi('{{ pi.mac }}', 'update')">Update</button>
            </div>
            <form class="two-col" onsubmit="return renamePi(event, '{{ pi.mac }}')">
              <input type="text" name="name" value="{{ pi.name }}" placeholder="Rename Pi">
              <button type="submit">Save Name</button>
            </form>
          </article>
          {% endfor %}
        </div>
      </div>
    </section>

    <aside class="card">
      <header>
        <h2>Commercials Loop</h2>
        <div class="sub">Enter the image names you want to cycle. Each image is pushed to every Pi. If a Pi does not have the image, it falls back to <strong>Logo.jpg</strong>.</div>
      </header>
      <div class="body stack">
        <textarea id="commercial-images" placeholder="Commercial1.jpg\nCommercial2.jpg\nCommercial3.jpg">{{ commercials_images }}</textarea>
        <div class="two-col">
          <input id="commercial-interval" type="number" min="1" step="1" value="{{ commercials_interval }}" aria-label="Seconds per image">
          <button class="primary" type="button" onclick="startCommercials()">Show Commercials</button>
        </div>
        <div class="toolbar">
          <button class="danger" type="button" onclick="stopCommercials()">Stop Loop</button>
          <button class="ghost" type="button" onclick="showLogoOnAll()">Show Logo on All</button>
        </div>
        <div class="state-line" id="commercials-state">
          <span class="state-pill">{{ commercials_state.status }}</span>
          <span class="state-pill">interval: {{ commercials_state.interval_seconds }}s</span>
          <span class="state-pill">images: {{ commercials_state.images|length }}</span>
        </div>
      </div>
    </aside>
  </div>
</div>

<script>
let _discoverBusy = false;

async function postJson(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body || {})
  });
  const text = await response.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch (error) { data = {ok: false, msg: text}; }
  if (!response.ok && !data.ok) data.status = response.status;
  return data;
}

async function registerPi(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const body = Object.fromEntries(new FormData(form).entries());
  const result = await postJson('/api/pis', body);
  if (!result.ok) {
    alert(result.msg || 'Unable to register Pi');
    return false;
  }
  form.reset();
  await refreshPis();
  return false;
}

async function renamePi(event, mac) {
  event.preventDefault();
  const body = Object.fromEntries(new FormData(event.currentTarget).entries());
  const result = await postJson('/api/pis/' + encodeURIComponent(mac) + '/rename', body);
  if (!result.ok) {
    alert(result.msg || 'Rename failed');
    return false;
  }
  await refreshPis();
  return false;
}

async function commandPi(mac, command) {
  const result = await postJson('/api/pis/' + encodeURIComponent(mac) + '/command/' + command, {});
  if (!result.ok) alert(result.msg || 'Command failed');
  return result;
}

async function broadcastCommand(command) {
  const result = await postJson('/api/broadcast/' + command, {});
  if (!result.ok) alert(result.msg || 'Broadcast failed');
  return result;
}

async function discoverPis(options) {
  const silent = !!(options && options.silent);
  if (_discoverBusy) return {ok: true, msg: 'Discovery already running'};
  _discoverBusy = true;
  const result = await postJson('/api/discover', {});
  if (!result.ok && !silent) {
    alert(result.msg || 'Discovery failed');
    _discoverBusy = false;
    return result;
  }
  await refreshPis();
  _discoverBusy = false;
  return result;
}

function openUi(mac) {
  const card = document.querySelector('.pi[data-mac="' + CSS.escape(mac) + '"]');
  if (!card) return;
  const uiUrl = card.dataset.uiUrl;
  if (!uiUrl) { alert('No remote UI URL configured for this Pi'); return; }
  window.open(uiUrl, '_blank', 'noopener');
}

async function startCommercials() {
  const images = document.getElementById('commercial-images').value;
  const intervalSeconds = parseInt(document.getElementById('commercial-interval').value || '4', 10);
  const result = await postJson('/api/commercials/start', {images: images, interval_seconds: intervalSeconds});
  if (!result.ok) alert(result.msg || 'Unable to start commercials');
  await refreshCommercialsState();
}

async function stopCommercials() {
  const result = await postJson('/api/commercials/stop', {});
  if (!result.ok) alert(result.msg || 'Unable to stop commercials');
  await refreshCommercialsState();
}

async function showLogoOnAll() {
  const result = await postJson('/api/broadcast/show_image', {image: 'Logo.jpg'});
  if (!result.ok) alert(result.msg || 'Unable to show logo');
}

async function refreshPis() {
  const response = await fetch('/api/pis');
  const data = await response.json();
  if (!data.ok) return;
  renderPis(data.pis || []);
}

function renderPis(pis) {
  const list = document.getElementById('pi-list');
  document.getElementById('dashboard-summary').textContent = pis.length + ' registered Pis';
  list.innerHTML = '';
  for (const pi of pis) {
    const article = document.createElement('article');
    article.className = 'pi';
    article.dataset.mac = pi.mac;
    article.dataset.uiUrl = pi.ui_url || '';
    article.innerHTML = `
      <div class="pi-top">
        <div>
          <div class="pi-name">${escapeHtml(pi.name || pi.mac)}</div>
          <div class="pi-meta">MAC: ${escapeHtml(pi.mac || '')}</div>
          <div class="pi-meta">API: ${escapeHtml(pi.api_base_url || '')}</div>
          <div class="pi-meta">UI: ${escapeHtml(pi.ui_url || '')}</div>
        </div>
        <div class="pi-status ${pi.online ? 'online' : 'offline'}">${pi.online ? 'online' : 'offline'}</div>
      </div>
      <div class="pi-actions">
        <button type="button" onclick="openUi('${pi.mac}')">Open UI</button>
        <button type="button" onclick="commandPi('${pi.mac}', 'show_stream')">Show Stream</button>
        <button type="button" onclick="commandPi('${pi.mac}', 'primary')">Primary</button>
        <button type="button" onclick="commandPi('${pi.mac}', 'secondary')">Secondary</button>
        <button type="button" onclick="commandPi('${pi.mac}', 'update')">Update</button>
      </div>
      <form class="two-col" onsubmit="return renamePi(event, '${pi.mac}')">
        <input type="text" name="name" value="${escapeAttr(pi.name || '')}" placeholder="Rename Pi">
        <button type="submit">Save Name</button>
      </form>`;
    list.appendChild(article);
  }
}

async function refreshCommercialsState() {
  const response = await fetch('/api/commercials/state');
  const data = await response.json();
  if (!data.ok) return;
  const state = document.getElementById('commercials-state');
  state.innerHTML = '';
  for (const pill of [data.status, 'interval: ' + data.interval_seconds + 's', 'images: ' + data.images.length]) {
    const span = document.createElement('span');
    span.className = 'state-pill';
    span.textContent = pill;
    state.appendChild(span);
  }
}

function escapeHtml(value) {
  const div = document.createElement('div');
  div.textContent = value;
  return div.innerHTML;
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/"/g, '&quot;');
}

refreshCommercialsState();
setInterval(function() { discoverPis({silent: true}); }, 30000);
</script>
</body>
</html>
"""


class PiDashboardApp:
    """Visual dashboard for managing multiple kiosk Pis."""

    def __init__(
        self,
        store=None,
        default_interval_seconds=None,
        logo_name="Logo.jpg",
        discovery_interval_seconds=None,
        auto_discovery_enabled=True,
    ):
        self.store = store or PiRegistryStore(config.DASHBOARD_REGISTRY_FILE)
        self.default_interval_seconds = float(
            default_interval_seconds
            if default_interval_seconds is not None
            else getattr(config, "DASHBOARD_DEFAULT_COMMERCIAL_INTERVAL_SECONDS", 4)
        )
        self.discovery_interval_seconds = float(
            discovery_interval_seconds
            if discovery_interval_seconds is not None
            else getattr(config, "DASHBOARD_DISCOVERY_INTERVAL_SECONDS", 30)
        )
        self.auto_discovery_enabled = bool(
            auto_discovery_enabled if auto_discovery_enabled is not None else True
        )
        self.logo_name = logo_name
        self._commercials_lock = threading.Lock()
        self._commercials_stop = threading.Event()
        self._commercials_thread = None
        self._discovery_lock = threading.Lock()
        self._discovery_stop = threading.Event()
        self._discovery_thread = None
        self._commercials_state = {
            "status": "idle",
            "interval_seconds": self.default_interval_seconds,
            "images": [],
        }
        self.app = Flask(__name__)
        self._setup_routes()
        if self.auto_discovery_enabled and self.discovery_interval_seconds > 0:
            self._start_background_discovery()

    def _setup_routes(self):
        self.app.route("/")(self.index)
        self.app.route("/api/pis", methods=["GET", "POST"])(self.pis_collection)
        self.app.route("/api/pis/<path:mac>/rename", methods=["POST"])(self.rename_pi)
        self.app.route("/api/pis/<path:mac>/command/<command>", methods=["POST"])(self.command_pi)
        self.app.route("/api/discover", methods=["POST"])(self.discover_pis)
        self.app.route("/api/broadcast/<command>", methods=["POST"])(self.broadcast_command)
        self.app.route("/api/broadcast/show_image", methods=["POST"])(self.broadcast_show_image)
        self.app.route("/api/commercials/start", methods=["POST"])(self.start_commercials)
        self.app.route("/api/commercials/stop", methods=["POST"])(self.stop_commercials)
        self.app.route("/api/commercials/state", methods=["GET"])(self.commercials_state)

    @staticmethod
    def _clean_text(value):
        return (value or "").strip()

    @staticmethod
    def _parse_images(raw_value):
        if isinstance(raw_value, list):
            values = raw_value
        else:
            text = str(raw_value or "")
            values = []
            for line in text.replace(",", "\n").splitlines():
                item = line.strip()
                if item:
                    values.append(item)
        seen = []
        for item in values:
            if item not in seen:
                seen.append(item)
        return seen

    @staticmethod
    def _join_path(base_url, path_suffix):
        base = (base_url or "").strip().rstrip("/")
        suffix = path_suffix.lstrip("/")
        return f"{base}/{suffix}"

    @staticmethod
    def _auto_local_subnet():
      """Best-effort local /24 subnet detection for discovery fallback."""
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

    @staticmethod
    def _candidate_hosts(subnet_cidr, max_hosts):
      """Return host IPs from a subnet CIDR string, clipped to max_hosts."""
      try:
        network = ipaddress.ip_network(subnet_cidr, strict=False)
      except Exception:
        return []
      hosts = [str(ip) for ip in network.hosts()]
      return hosts[:max(1, int(max_hosts))]

    @staticmethod
    def _parse_mac_from_arp(ip_addr):
      """Cross-platform fallback MAC lookup via arp command output."""
      try:
        result = subprocess.run(
          ["arp", "-a", ip_addr],
          capture_output=True,
          text=True,
          check=False,
        )
        text = (result.stdout or "") + "\n" + (result.stderr or "")
        match = re.search(r"([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}", text)
        if not match:
          return ""
        return match.group(0).lower().replace("-", ":")
      except Exception:
        return ""

    def _resolve_mac(self, ip_addr):
      """Try Linux neighbor table first, then generic arp fallback."""
      mac = resolve_mac_for_host(ip_addr)
      if mac:
        return mac
      return self._parse_mac_from_arp(ip_addr)

    def _discover_pi_candidates(self, timeout_seconds=1.2):
      """Probe configured subnets for reachable kiosk APIs and collect MACs."""
      subnets = list(getattr(config, "DASHBOARD_DISCOVERY_SUBNETS", []) or [])
      if not subnets:
        auto_subnet = self._auto_local_subnet()
        if auto_subnet:
          subnets = [auto_subnet]
      if not subnets:
        # Optional fallback for legacy configs that only define camera scan ranges.
        subnets = list(getattr(config, "RTSP_SCAN_SUBNETS", []) or [])

      port = int(getattr(config, "FLASK_PORT", 8080))
      max_hosts = int(getattr(config, "DASHBOARD_DISCOVERY_MAX_HOSTS", 254))
      api_path = "/get_primary_url"

      candidates = []
      seen_hosts = set()
      for subnet in subnets:
        for host in self._candidate_hosts(subnet, max_hosts):
          if host in seen_hosts:
            continue
          seen_hosts.add(host)
          candidates.append(host)

      def probe_host(host):
        base_url = f"http://{host}:{port}"
        result = self._request("GET", self._join_path(base_url, api_path), timeout=timeout_seconds)
        if not (result.get("ok") or result.get("status") == 404):
          return None

        # Try to ensure ARP/neigh has this host before MAC lookup.
        try:
          self._request("GET", base_url, timeout=timeout_seconds)
        except Exception:
          pass

        mac = self._resolve_mac(host)
        return {
          "host": host,
          "api_base_url": base_url,
          "ui_url": base_url,
          "mac": mac,
          "name": f"Pi {host}",
        }

      found = []
      with ThreadPoolExecutor(max_workers=max(1, min(32, len(candidates) or 1))) as executor:
        futures = [executor.submit(probe_host, host) for host in candidates]
        for future in futures:
          item = future.result()
          if item:
            found.append(item)
      return found

    def _register_discovered_pis(self, discovered):
      """Store discovered Pis keyed by MAC and report unresolved hosts."""
      added = 0
      unresolved = []
      for item in discovered:
        mac = self._clean_text(item.get("mac"))
        if not mac:
          unresolved.append(
            {
              "host": item.get("host", ""),
              "api_base_url": item.get("api_base_url", ""),
              "msg": "MAC not resolved",
            }
          )
          continue

        if self.store.upsert_pi(
          mac,
          name=item.get("name"),
          api_base_url=item.get("api_base_url"),
          ui_url=item.get("ui_url"),
        ):
          added += 1
      return added, unresolved

    def _run_discovery_cycle(self, timeout_seconds=1.2):
      """Run one discovery pass and persist results."""
      discovered = self._discover_pi_candidates(timeout_seconds=timeout_seconds)
      added, unresolved = self._register_discovered_pis(discovered)
      return {
        "found": len(discovered),
        "added": added,
        "unresolved": unresolved,
      }

    def _background_discovery_loop(self):
      """Periodic discovery loop to keep Pi registry fresh."""
      while not self._discovery_stop.is_set():
        try:
          with self._discovery_lock:
            self._run_discovery_cycle(timeout_seconds=1.2)
        except Exception as exc:
          print(f"Dashboard background discovery error: {exc}")
        wait_seconds = max(5.0, float(self.discovery_interval_seconds))
        if self._discovery_stop.wait(wait_seconds):
          break

    def _start_background_discovery(self):
      """Start periodic background discovery thread once."""
      if self._discovery_thread and self._discovery_thread.is_alive():
        return
      self._discovery_thread = threading.Thread(target=self._background_discovery_loop, daemon=True)
      self._discovery_thread.start()

    def _request(self, method, url, timeout=4.0):
        request_obj = Request(url, method=method)
        try:
            with urlopen(request_obj, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
                return {
                    "ok": True,
                    "status": response.status,
                    "body": body,
                }
        except HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            return {
                "ok": False,
                "status": exc.code,
                "body": body,
                "error": str(exc),
            }
        except URLError as exc:
            return {
                "ok": False,
                "status": 0,
                "body": "",
                "error": str(exc),
            }

    def _probe_pi(self, pi):
        url = self._join_path(pi.get("api_base_url", ""), "/get_primary_url")
        result = self._request("GET", url, timeout=2.0)
        return result["ok"] or result.get("status") == 404

    def _annotate_pi(self, pi):
        item = dict(pi)
        item["online"] = self._probe_pi(pi) if pi.get("api_base_url") else False
        item["ui_url"] = pi.get("ui_url") or pi.get("api_base_url", "")
        return item

    def _command_paths(self, command, image=None):
        command = (command or "").strip().lower()
        if command == "primary":
            return "/set_stream_to_primary_camera"
        if command == "secondary":
            return "/set_stream_to_secondary_camera"
        if command == "update":
            return "/update"
        if command == "show_stream":
            return "/show_stream"
        if command == "show_image" and image:
            return f"/show_image/{quote(image)}"
        return ""

    def _try_set_stream_for_role(self, pi, role):
        """Fallback flow for role switching when direct endpoint is unavailable."""
        role = (role or "").strip().lower()
        if role not in ("primary", "secondary"):
            return {"ok": False, "msg": "Invalid role"}

        role_url_path = f"/get_{role}_url"
        role_resp = self._request("GET", self._join_path(pi.get("api_base_url", ""), role_url_path), timeout=4.0)
        if not role_resp.get("ok"):
            return {
                "ok": False,
                "msg": role_resp.get("error") or f"Role lookup failed for {role}",
                "status": role_resp.get("status", 0),
            }

        try:
            payload = json.loads(role_resp.get("body") or "{}")
        except Exception:
            payload = {}

        target_url = (payload.get("url") or "").strip()
        if not target_url:
            return {"ok": False, "msg": f"No URL configured for {role}"}

        set_stream_url = self._join_path(
            pi.get("api_base_url", ""),
            f"/set_stream?url={quote(target_url, safe=':/?&=%')}",
        )
        set_resp = self._request("GET", set_stream_url, timeout=5.0)
        return {
            "ok": set_resp.get("ok", False),
            "msg": set_resp.get("error") or ("OK" if set_resp.get("ok") else "Role fallback stream switch failed"),
            "status": set_resp.get("status", 0),
            "fallback_used": True,
            "url": target_url,
        }

    def _send_command(self, pi, command, image=None):
        path = self._command_paths(command, image=image)
        if not path:
            return {"ok": False, "msg": f"Unsupported command: {command}"}

        if command == "show_image" and image:
            primary_result = self._request("GET", self._join_path(pi.get("api_base_url", ""), path), timeout=4.0)
            if primary_result["ok"]:
                return {
                    "ok": True,
                    "msg": f"Displayed {image}",
                    "image": image,
                    "fallback_used": False,
                }
            if primary_result.get("status") == 404 and image != self.logo_name:
                fallback_path = self._command_paths("show_image", image=self.logo_name)
                fallback_result = self._request("GET", self._join_path(pi.get("api_base_url", ""), fallback_path), timeout=4.0)
                return {
                    "ok": fallback_result["ok"],
                    "msg": "Fallback to Logo.jpg" if fallback_result["ok"] else fallback_result.get("error") or "Fallback failed",
                    "image": image,
                    "fallback_used": True,
                    "fallback_status": fallback_result.get("status", 0),
                }
            return {
                "ok": False,
                "msg": primary_result.get("error") or f"Failed to display {image}",
                "image": image,
                "fallback_used": False,
                "status": primary_result.get("status", 0),
            }

        result = self._request("GET", self._join_path(pi.get("api_base_url", ""), path), timeout=5.0)
        if command in ("primary", "secondary") and result.get("status") == 404:
          return self._try_set_stream_for_role(pi, command)
        return {
            "ok": result["ok"],
            "msg": result.get("error") or ("OK" if result["ok"] else "Command failed"),
            "status": result.get("status", 0),
        }

    def _broadcast(self, command, image=None):
        pis = self.store.list_pis()
        results = []
        with ThreadPoolExecutor(max_workers=max(1, min(8, len(pis) or 1))) as executor:
            futures = [executor.submit(self._send_command, pi, command, image) for pi in pis]
            for pi, future in zip(pis, futures):
                result = future.result()
                results.append({
                    "mac": pi.get("mac"),
                    "name": pi.get("name"),
                    **result,
                })
        ok = all(item.get("ok") for item in results) if results else False
        return {
            "ok": ok,
            "command": command,
            "results": results,
        }

    def _commercials_loop(self, images, interval_seconds):
        try:
            self._commercials_state = {
                "status": "running",
                "interval_seconds": interval_seconds,
                "images": list(images),
            }
            while not self._commercials_stop.is_set():
                for image in images:
                    if self._commercials_stop.is_set():
                        break
                    self._broadcast("show_image", image=image)
                    wait_deadline = time.time() + interval_seconds
                    while time.time() < wait_deadline and not self._commercials_stop.is_set():
                        time.sleep(0.1)
        finally:
            self._commercials_state = {
                "status": "idle",
                "interval_seconds": interval_seconds,
                "images": list(images),
            }
            self._commercials_stop.clear()
            self._commercials_thread = None

    def index(self):
        pis = [self._annotate_pi(pi) for pi in self.store.list_pis()]
        return render_template_string(
            DASHBOARD_HTML,
            pis=pis,
            commercials_images="\n".join(self._commercials_state.get("images", [])),
            commercials_interval=self._commercials_state.get("interval_seconds", self.default_interval_seconds),
            commercials_state=self._commercials_state,
        )

    def pis_collection(self):
        if request.method == "GET":
            pis = [self._annotate_pi(pi) for pi in self.store.list_pis()]
            return jsonify({"ok": True, "pis": pis})

        payload = request.get_json(silent=True) or request.form.to_dict(flat=True)
        mac = self._clean_text(payload.get("mac"))
        api_base_url = self._clean_text(payload.get("api_base_url"))
        name = self._clean_text(payload.get("name"))
        ui_url = self._clean_text(payload.get("ui_url"))
        if not mac:
            return jsonify({"ok": False, "msg": "Missing mac"}), 400
        if not api_base_url:
            return jsonify({"ok": False, "msg": "Missing api_base_url"}), 400
        if not self.store.upsert_pi(mac, name=name, api_base_url=api_base_url, ui_url=ui_url or None):
            return jsonify({"ok": False, "msg": "Unable to register pi"}), 400
        pi = self._annotate_pi(self.store.get_pi(mac))
        return jsonify({"ok": True, "pi": pi})

    def rename_pi(self, mac):
        payload = request.get_json(silent=True) or request.form.to_dict(flat=True)
        name = self._clean_text(payload.get("name"))
        if not name:
            return jsonify({"ok": False, "msg": "Missing name"}), 400
        if not self.store.rename_pi(mac, name):
            return jsonify({"ok": False, "msg": "Pi not found"}), 404
        return jsonify({"ok": True, "pi": self._annotate_pi(self.store.get_pi(mac))})

    def command_pi(self, mac, command):
        pi = self.store.get_pi(mac)
        if not pi:
            return jsonify({"ok": False, "msg": "Pi not found"}), 404
        payload = request.get_json(silent=True) or {}
        image = self._clean_text(payload.get("image")) or None
        result = self._send_command(pi, command, image=image)
        status = 200 if result.get("ok") else 502
        return jsonify(result), status

    def discover_pis(self):
        """Discover kiosk Pis on configured subnets and auto-register by MAC."""
        payload = request.get_json(silent=True) or {}
        timeout_seconds = float(payload.get("timeout_seconds", 1.2) or 1.2)
        with self._discovery_lock:
            stats = self._run_discovery_cycle(timeout_seconds=timeout_seconds)

        return jsonify(
            {
                "ok": True,
                "msg": "Discovery complete",
                "found": stats["found"],
                "added": stats["added"],
                "unresolved": stats["unresolved"],
            }
        )

    def broadcast_command(self, command):
        result = self._broadcast(command)
        status = 200 if result.get("ok") else 502
        return jsonify(result), status

    def broadcast_show_image(self):
        payload = request.get_json(silent=True) or {}
        image = self._clean_text(payload.get("image"))
        if not image:
            return jsonify({"ok": False, "msg": "Missing image"}), 400
        result = self._broadcast("show_image", image=image)
        status = 200 if result.get("ok") else 502
        return jsonify(result), status

    def start_commercials(self):
        payload = request.get_json(silent=True) or request.form.to_dict(flat=True)
        images = self._parse_images(payload.get("images", ""))
        if not images:
            return jsonify({"ok": False, "msg": "Missing images"}), 400
        try:
            interval_seconds = float(payload.get("interval_seconds", self.default_interval_seconds))
        except Exception:
            interval_seconds = self.default_interval_seconds
        interval_seconds = max(1.0, interval_seconds)

        with self._commercials_lock:
            if self._commercials_thread and self._commercials_thread.is_alive():
                return jsonify({"ok": False, "msg": "Commercials loop already running"}), 409
            self._commercials_stop.clear()
            self._commercials_thread = threading.Thread(
                target=self._commercials_loop,
                args=(images, interval_seconds),
                daemon=True,
            )
            self._commercials_thread.start()

        return jsonify({"ok": True, "msg": "Commercials started", "images": images, "interval_seconds": interval_seconds})

    def stop_commercials(self):
        self._commercials_stop.set()
        return jsonify({"ok": True, "msg": "Commercials stopping"})

    def commercials_state(self):
        return jsonify({"ok": True, **self._commercials_state})

    def run(self):
        self.app.run(host="0.0.0.0", port=getattr(config, "DASHBOARD_PORT", 8090), debug=False, use_reloader=False)


if __name__ == "__main__":
    PiDashboardApp().run()
