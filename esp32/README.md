# ESP32-CAM integration (NAYAN-AI)

This project already supports image upload for cataract via the web UI (`/api/cataract/upload`). For **ESP32-CAM**, the backend now also supports a device-friendly endpoint that accepts **raw JPEG bytes**.

## Backend endpoints

- `GET /api/camera/esp32/ping`
- `POST /api/camera/esp32/frame` (upload latest camera frame, no patient needed)
- `GET /api/camera/esp32/latest` (returns latest frame URL)
- `POST /api/camera/esp32/cataract/latest` (website-triggered: analyze latest frame for a patient)
- `POST /api/camera/esp32/dryeye/latest` (website-triggered: analyze last N seconds from recent frames)

### Recommended flow (best for website integration)

1) ESP32 uploads frames continuously:

- `POST /api/camera/esp32/frame?device_id=esp32cam1`

2) Website triggers inference for the currently selected patient:

- `POST /api/camera/esp32/cataract/latest` with JSON: `{ "patient_id": 1, "device_id": "esp32cam1" }`

### Dry eye flow (ESP32 frame sequence)

1) ESP32 uploads frames continuously (same as cataract):

- `POST /api/camera/esp32/frame?device_id=esp32cam1`

2) Website triggers dry-eye analysis for the selected patient using the last N seconds of frames:

- `POST /api/camera/esp32/dryeye/latest` with JSON: `{ "patient_id": 1, "device_id": "esp32cam1", "seconds": 30 }`

### Legacy direct inference

`POST /api/camera/esp32/cataract` still works, but requires `patient_id` on the request.

Supported payload styles:

1) **Raw JPEG** (recommended for ESP32-CAM)
- URL: `http://<PC-IP>:5000/api/camera/esp32/cataract?patient_id=<id>`
- Headers: `Content-Type: image/jpeg`
- Body: raw JPEG bytes

2) **multipart/form-data**
- Fields: `patient_id`, `image`

3) **JSON base64**
- JSON: `{ "patient_id": 1, "frame": "<base64>" }`

### Optional device token (recommended)

If you set an environment variable on the backend:

- `ESP32_DEVICE_TOKEN=your-secret-token`

then ESP32 requests must include:

- header `X-Device-Token: your-secret-token` **or** query param `?token=your-secret-token`

## Firmware

Use the Arduino sketch in:
- `esp32/ESP32_CAM_NAYAN_AI/ESP32_CAM_NAYAN_AI.ino`

### ESP32-WROOM controller (UART + VL53L1X)

If you are using an **ESP32-WROOM** as the main controller (buttons + VL53L1X) and an **ESP32-CAM** as the camera node, use:

- `esp32/ESP32_WROOM_NAYAN_AI/ESP32_WROOM_NAYAN_AI.ino`

This sketch:
- Debounces 3 buttons (Glaucoma/Cataract/Dry Eye)
- Drives a single status LED (idle/process/success/error)
- Runs VL53L1X sampling + Kalman filtering for glaucoma response and computes OMDI
- Sends commands/results to ESP32-CAM over UART

### UART command protocol (WROOM -> CAM)

Commands (single line, `\n` terminated):
- `CAPTURE_IMAGE`
- `RECORD_VIDEO:30` (seconds 10..60)
- `GLAUCOMA_RESULT,peak_mm=...,tr_ms=...,var=...,omdi=...,risk=...`

Responses (CAM -> WROOM):
- `ACK:<command>`
- `ERR:<command>:<message>`

### Wiring note (UART)

On **ESP32-CAM**, the simplest UART pins are the default programming UART:
- CAM RX: `GPIO3` (U0RXD)
- CAM TX: `GPIO1` (U0TXD)

On **ESP32-WROOM**, the sketch defaults to:
- WROOM RX2: `GPIO16`
- WROOM TX2: `GPIO17`

Adjust the WROOM pins in the sketch if your wiring differs.

Notes:
- Use your laptop IPv4 address (same Wi-Fi) in `SERVER_URL`.
- Keep framesize around VGA/SVGA for stability; the backend resizes to the model input size.
- Ensure Windows Firewall allows inbound TCP on port 5000.

### Flash / torch (ESP32-CAM)

The onboard white LED (flash) can be enabled in the sketch:

- File: `esp32/ESP32_CAM_NAYAN_AI/ESP32_CAM_NAYAN_AI.ino`
- Set `FLASH_MODE = FLASH_TORCH` to keep the light ON
- Or set `FLASH_MODE = FLASH_CAPTURE_ONLY` to turn ON only during capture (recommended if you see resets)
- Adjust `FLASH_BRIGHTNESS` (0..255)
