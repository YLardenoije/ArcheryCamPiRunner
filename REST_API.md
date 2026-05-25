# ArcheryCamPiRunner REST API Reference

This document describes the HTTP endpoints exposed by the kiosk web server.

## Base URL

- Local host: http://127.0.0.1:8080
- Network host: http://<pi-ip>:8080
- Port is configurable via `FLASK_PORT` in `config.py`

## Authentication

- No authentication is currently required.
- Deploy only on trusted networks, or place behind a reverse proxy with auth.

## Content Types

- JSON endpoints: `application/json`
- Form endpoints: `application/x-www-form-urlencoded` or `multipart/form-data`

## Endpoint Summary

- `GET /`: Main HTML control page.
- `POST /upload`: Upload an image.
- `GET /show_image/<name>`: Display an uploaded image on kiosk screen.
- `GET /delete/<name>`: Delete an uploaded image.
- `GET /show_stream`: Switch kiosk display to current RTSP stream.
- `GET /images/<name>`: Fetch image file contents.
- `GET /set_stream?url=<rtsp-url>`: Set active stream and restart player.
- `GET|POST /set_stream_to_primary_camera`: Set active stream to configured primary camera.
- `GET|POST /set_stream_to_secondary_camera`: Set active stream to configured secondary camera.
- `POST /camera_settings`: Update camera metadata and stored PTZ values.
- `POST /ptz_live`: Apply live PTZ command (JSON).
- `GET /get_primary_url`: Return configured primary camera URL.
- `GET /get_secondary_url`: Return configured secondary camera URL.
- `GET|POST /update`: Run update script on the device.
- `GET /kill`: Shut down kiosk application process.

## Detailed Endpoints

## GET /

Returns the HTML control interface.

- Success: `HTTP 200`, `text/html`

## POST /upload

Uploads an image into `UPLOAD_FOLDER`.

Request:
- Multipart form field: `file`

Allowed file extensions:
- `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.webp`, `.tif`, `.tiff`

Responses:
- Success: `HTTP 302` redirect to `/`
- Error: `HTTP 400` with message `No file uploaded`
- Error: `HTTP 400` with unsupported extension message

Example:

```bash
curl -X POST http://<pi-ip>:8080/upload -F "file=@target.webp"
```

## GET /show_image/<name>

Displays an uploaded image full-screen on the kiosk.

Responses:
- Success: `HTTP 302` redirect to `/`
- Error: `HTTP 404` if file not found

## GET /delete/<name>

Deletes an uploaded image.

Responses:
- Success: `HTTP 302` redirect to `/`
- Error: `HTTP 500` with deletion error text

## GET /show_stream

Switches kiosk display back to currently selected RTSP stream.

Responses:
- Success: `HTTP 302` redirect to `/`
- Error: `HTTP 400` with message `No camera selected`

## GET /images/<name>

Returns image bytes from `UPLOAD_FOLDER`.

Responses:
- Success: `HTTP 200` with image content

## GET /set_stream

Sets the active RTSP URL and restarts VLC in a background thread.
If the selected camera has stored PTZ values, PTZ is applied after stream restart.

Query parameters:
- `url` (required): RTSP URL

Responses:
- Success: `HTTP 302` redirect to `/`
- Error: `HTTP 400` with message `Missing url parameter`

Example:

```bash
curl "http://<pi-ip>:8080/set_stream?url=rtsp://192.168.100.198:554/11"
```

## GET|POST /set_stream_to_primary_camera

Sets active stream to the configured primary camera and schedules a background player restart.

Success response:
- `HTTP 200`
- JSON:

```json
{
  "ok": true,
  "msg": "Stream switch scheduled",
  "role": "primary",
  "url": "rtsp://192.168.100.198:554/11",
  "name": "main",
  "host": "192.168.100.198"
}
```

Failure response:
- `HTTP 404`
- JSON: `{"ok": false, "msg": "No primary camera configured"}`

Example:

```bash
curl http://<pi-ip>:8080/set_stream_to_primary_camera
```

## GET|POST /set_stream_to_secondary_camera

Sets active stream to the configured secondary camera and schedules a background player restart.

Success response:
- `HTTP 200`
- JSON:

```json
{
  "ok": true,
  "msg": "Stream switch scheduled",
  "role": "secondary",
  "url": "rtsp://192.168.10.103:554/11",
  "name": "secondary",
  "host": "192.168.10.103"
}
```

Failure response:
- `HTTP 404`
- JSON: `{"ok": false, "msg": "No secondary camera configured"}`

Example:

```bash
curl http://<pi-ip>:8080/set_stream_to_secondary_camera
```

## POST /camera_settings

Updates camera metadata and PTZ values in persistent storage (keyed by camera MAC when available).

Form fields:
- `url` (required): exact camera URL currently in camera list
- `name` (optional): friendly name
- `role`: `none`, `primary`, or `secondary`
- `zoom`: percentage value `0..100`
- `focus`: percentage value `0..100`
- `action`: `save` or `apply`

Behavior:
- Values are converted to `0..1` internally.
- `action=save` stores metadata and PTZ values only.
- `action=apply` stores values and also applies PTZ immediately.

Responses:
- Success: `HTTP 302` redirect to `/`
- Error: `HTTP 400` (missing URL)
- Error: `HTTP 404` (camera not found)

## POST /ptz_live

Primary endpoint for live remote PTZ control (JSON).

Request JSON:
- `url` (required): exact camera URL from active camera list
- `zoom`: normalized float `0..1`
- `focus`: normalized float `0..1`
- `changed`: `zoom`, `focus`, or `both`

Behavior:
- If `changed=zoom`, only zoom is applied.
- If `changed=focus`, only focus is applied.
- If `changed=both` (or omitted), both axes are applied.

Success response:
- `HTTP 200`
- JSON: `{"ok": true, "msg": "PTZ command applied"}`

Failure responses:
- `HTTP 404` if camera URL is unknown: `{"ok": false, "msg": "Camera not found"}`
- `HTTP 200` with `ok=false` for PTZ operation failures: `{"ok": false, "msg": "..."}`

Example:

```bash
curl -X POST http://<pi-ip>:8080/ptz_live \
  -H "Content-Type: application/json" \
  -d '{"url":"rtsp://192.168.100.198:554/11","zoom":0.2201,"focus":0.0,"changed":"zoom"}'
```

## GET /get_primary_url

Returns current primary camera selection.

Success response:
- `HTTP 200`
- JSON:

```json
{
  "ok": true,
  "role": "primary",
  "url": "rtsp://192.168.100.198:554/11",
  "name": "main",
  "host": "192.168.100.198"
}
```

Failure response:
- `HTTP 404`
- JSON: `{"ok": false, "msg": "No primary camera configured"}`

## GET /get_secondary_url

Returns current secondary camera selection.

Success response:
- `HTTP 200`
- JSON:

```json
{
  "ok": true,
  "role": "secondary",
  "url": "rtsp://192.168.10.103:554/11",
  "name": "secondary",
  "host": "192.168.10.103"
}
```

Failure response:
- `HTTP 404`
- JSON: `{"ok": false, "msg": "No secondary camera configured"}`

## GET|POST /update

Starts the local update script in a background thread and returns immediately.

Behavior:
- Tries `update.sh` first.
- Falls back to `update_app.sh` for backward compatibility.

Success response:
- `HTTP 200`
- JSON:

```json
{
  "ok": true,
  "msg": "Update started",
  "script": "update_app.sh"
}
```

Failure response:
- `HTTP 404`
- JSON: `{"ok": false, "msg": "Update script not found"}`

Example:

```bash
curl -X POST http://<pi-ip>:8080/update
```

## GET /kill

Triggers asynchronous application shutdown.

Responses:
- Success: `HTTP 200` with text `Shutting down kiosk application...`

## Notes for API Clients

- Most endpoints are HTML-control oriented and return redirects.
- For machine control, prefer `/ptz_live`, `/get_primary_url`, and `/get_secondary_url`.
- The camera URL in requests must match a currently discovered camera URL.
- Live UI uses a 1 second debounce before sending PTZ. API clients can choose their own pacing.
- The browser UI displays percentages, but `/ptz_live` expects normalized `0..1` floats.
