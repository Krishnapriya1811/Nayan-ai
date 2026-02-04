/*
  ESP32-CAM -> NAYAN-AI uploader (Camera + Torch + 2 Buttons)

  Main stream (continuous frames):
    POST http://<PC-IP>:5000/api/camera/esp32/frame?device_id=esp32cam1&quiet=1

  Two buttons send "hardware events" to the backend so the laptop UI can act
  without mouse/keyboard:
    POST http://<PC-IP>:5000/api/hardware/event

  Suggested mapping used here:
    - Dry Eye button -> button id 1
    - Cataract button -> button id 3

  Optional (recommended) shared token:
    - Backend env var: ESP32_DEVICE_TOKEN=...
    - Add query param: &token=...
      OR header: X-Device-Token: ...

  Board settings (Arduino IDE):
    - Board: AI Thinker ESP32-CAM
    - PSRAM: Enabled

  Wiring (ESP32-CAM-MB programmer):
    - Plug ESP32-CAM into MB, connect via USB.
*/

#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>

// ===================== FLASH / TORCH =====================
// Set to 0 to completely disable the ESP32-CAM flash LED (GPIO4).
// This avoids turning on the bright onboard LED and frees the pin from PWM usage.
#define ENABLE_FLASH 1

// UART command protocol (from ESP32-WROOM):
//   - CAPTURE_IMAGE
//   - RECORD_VIDEO[:<seconds>]
//   - GLAUCOMA_RESULT,<csv...>   (accepted + ACKed; forwarding optional)
// Responses:
//   - ACK:<command>
//   - ERR:<command>:<message>


#define BTN_DRYEYE_GPIO 13
#define BTN_CATARACT_GPIO 14

// Buttons are typically connected to the ESP32-WROOM in the new wiring.
// Keep this optional so the same ESP32-CAM firmware can be reused.
#define ENABLE_LOCAL_BUTTONS 0

static const int HW_BTN_DRYEYE_ID = 1;
static const int HW_BTN_CATARACT_ID = 3;

static const uint32_t BTN_DEBOUNCE_MS = 60;
static uint32_t _btnLastMsDryeye = 0;
static uint32_t _btnLastMsCataract = 0;
static int _btnLastStateDryeye = HIGH;
static int _btnLastStateCataract = HIGH;

#define FLASH_GPIO_NUM 4
#define FLASH_ACTIVE_HIGH 1

#define FLASH_PWM_FREQ_HZ 5000
#define FLASH_PWM_RES_BITS 8

#define FLASH_LEDC_CHANNEL LEDC_CHANNEL_1
#define FLASH_LEDC_TIMER   LEDC_TIMER_1

enum FlashMode {
  FLASH_OFF = 0,
  FLASH_TORCH = 1,        // always on
  FLASH_CAPTURE_ONLY = 2  // on just before capture, off after
};

// Default to OFF when flash is disabled.
FlashMode FLASH_MODE = ENABLE_FLASH ? FLASH_TORCH : FLASH_OFF;
uint8_t FLASH_BRIGHTNESS = 180;

const char* WIFI_SSID = "Karthi's Galaxy A23 5G";
const char* WIFI_PASS = "Karthi800@";

const char* SERVER_URL = "http://192.168.243.45:5000/api/camera/esp32/frame?device_id=esp32cam1&quiet=1";

// Optional: trigger backend capture/record endpoints when commanded over UART.
// These endpoints exist in backend/app.py.
const char* CAPTURE_URL = "http://192.168.243.45:5000/api/camera/esp32/capture?device_id=esp32cam1";
const char* RECORD_URL  = "http://192.168.243.45:5000/api/camera/esp32/record";
const char* GLAUCOMA_INGEST_URL = "http://192.168.243.45:5000/api/glaucoma/device";

const char* HW_EVENT_URL = "http://192.168.243.45:5000/api/hardware/event";

const uint32_t STREAM_INTERVAL_MS = 100;

static uint32_t _lastStreamMs = 0;

static String _uartLine;
static const size_t UART_LINE_MAX = 220;

static void uartSendAck(const String& cmd) {
  Serial.print("ACK:");
  Serial.println(cmd);
}

static void uartSendErr(const String& cmd, const String& msg) {
  Serial.print("ERR:");
  Serial.print(cmd);
  Serial.print(":");
  Serial.println(msg);
}

static bool httpPostJson(const char* url, const String& jsonBody, uint16_t timeoutMs) {
  if (WiFi.status() != WL_CONNECTED) {
    return false;
  }

  HTTPClient http;
  static WiFiClient wifiClient;
  wifiClient.setNoDelay(true);
  http.setReuse(true);
  http.setTimeout(timeoutMs);

#if defined(ESP_ARDUINO_VERSION_MAJOR)
  http.begin(wifiClient, url);
#else
  http.begin(url);
#endif
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Connection", "keep-alive");
  int code = http.POST((uint8_t*)jsonBody.c_str(), jsonBody.length());
  http.end();

  return code > 0 && code < 400;
}

static bool triggerBackendCapture() {
  if (WiFi.status() != WL_CONNECTED) {
    return false;
  }
  HTTPClient http;
  static WiFiClient wifiClient;
  wifiClient.setNoDelay(true);
  http.setReuse(true);
  http.setTimeout(4000);
#if defined(ESP_ARDUINO_VERSION_MAJOR)
  http.begin(wifiClient, CAPTURE_URL);
#else
  http.begin(CAPTURE_URL);
#endif
  int code = http.POST("");
  http.end();
  return code > 0 && code < 400;
}

static bool triggerBackendRecord(uint16_t seconds) {
  seconds = (uint16_t)constrain(seconds, 10, 60);
  String body;
  body.reserve(96);
  body += "{\"device_id\":\"esp32cam1\",\"seconds\":";
  body += String(seconds);
  body += "}";
  return httpPostJson(RECORD_URL, body, 12000);
}

static void handleUartCommandLine(String line) {
  line.trim();
  if (!line.length()) {
    return;
  }

  // Normalize to simplify matching
  String cmd = line;
  cmd.toUpperCase();

  if (cmd == "CAPTURE_IMAGE") {
    bool ok = triggerBackendCapture();
    if (ok) uartSendAck("CAPTURE_IMAGE");
    else uartSendErr("CAPTURE_IMAGE", "backend_or_wifi_failed");
    return;
  }

  if (cmd.startsWith("RECORD_VIDEO")) {
    uint16_t seconds = 30;
    int colon = cmd.indexOf(':');
    if (colon > 0 && colon + 1 < (int)cmd.length()) {
      seconds = (uint16_t)cmd.substring(colon + 1).toInt();
      if (seconds == 0) seconds = 30;
    }
    bool ok = triggerBackendRecord(seconds);
    if (ok) uartSendAck("RECORD_VIDEO");
    else uartSendErr("RECORD_VIDEO", "backend_or_wifi_failed");
    return;
  }

  // Accept glaucoma results (WROOM->CAM) so the WROOM can treat this as a delivery channel.
  // Forward to backend (/api/glaucoma/device). Backend uses device_id->patient binding.
  if (cmd.startsWith("GLAUCOMA_RESULT")) {
    Serial.print("[WROOM] ");
    Serial.println(line);

    // Parse: GLAUCOMA_RESULT,peak_mm=...,tr_ms=...,var=...,omdi=...,risk=...
    String json;
    json.reserve(220);
    json += '{';
    json += "\"device_id\":\"esp32cam1\"";

    int comma = line.indexOf(',');
    if (comma > 0 && comma + 1 < (int)line.length()) {
      String rest = line.substring(comma + 1);
      rest.trim();

      int start = 0;
      while (start < (int)rest.length()) {
        int end = rest.indexOf(',', start);
        if (end < 0) end = (int)rest.length();
        String kv = rest.substring(start, end);
        kv.trim();
        int eq = kv.indexOf('=');
        if (eq > 0) {
          String k = kv.substring(0, eq);
          String v = kv.substring(eq + 1);
          k.trim();
          v.trim();

          // normalize keys to backend expected fields
          k.toLowerCase();
          if (k == "tr_ms") k = "recovery_latency_ms";
          if (k == "var") k = "variance";
          if (k == "risk") k = "risk_level";

          json += ',';
          json += '"' + k + '"' + ':';

          // risk_level is a string; everything else is numeric
          if (k == "risk_level") {
            json += '"' + v + '"';
          } else {
            json += v;
          }
        }
        start = end + 1;
      }
    }
    json += '}';

    // Best-effort send to backend (does not block UART ACK)
    (void)httpPostJson(GLAUCOMA_INGEST_URL, json, 2000);
    uartSendAck("GLAUCOMA_RESULT");
    return;
  }

  uartSendErr(line, "unknown_command");
}

static void pollUartCommands() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      if (_uartLine.length()) {
        handleUartCommandLine(_uartLine);
        _uartLine = "";
      }
      continue;
    }
    if (_uartLine.length() < UART_LINE_MAX) {
      _uartLine += c;
    } else {
      // line too long; flush
      _uartLine = "";
    }
  }
}

#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

static bool initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;

  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  if (psramFound()) {
    config.frame_size = FRAMESIZE_QVGA;
    config.jpeg_quality = 14;
    config.fb_count = 2;
  } else {
    config.frame_size = FRAMESIZE_QVGA;
    config.jpeg_quality = 14;
    config.fb_count = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    return false;
  }

  sensor_t* s = esp_camera_sensor_get();
  if (s) {
    s->set_vflip(s, 0);
    s->set_hmirror(s, 0);
  }

  return true;
}

static void flashSetup() {
#if ENABLE_FLASH
  pinMode(FLASH_GPIO_NUM, OUTPUT);
  digitalWrite(FLASH_GPIO_NUM, FLASH_ACTIVE_HIGH ? LOW : HIGH);

#if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
  ledcAttach(FLASH_GPIO_NUM, FLASH_PWM_FREQ_HZ, FLASH_PWM_RES_BITS);
  ledcWrite(FLASH_GPIO_NUM, 0);
#elif defined(ARDUINO_ARCH_ESP32)
  ledcSetup(FLASH_LEDC_CHANNEL, FLASH_PWM_FREQ_HZ, FLASH_PWM_RES_BITS);
  ledcAttachPin(FLASH_GPIO_NUM, FLASH_LEDC_CHANNEL);
  ledcWrite(FLASH_LEDC_CHANNEL, 0);
#endif
#else
  // Flash disabled: do not touch GPIO4 at all.
#endif
}

static void flashOn(uint8_t brightness) {
#if ENABLE_FLASH
  uint8_t duty = FLASH_ACTIVE_HIGH ? brightness : (uint8_t)(255 - brightness);

#if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
  ledcWrite(FLASH_GPIO_NUM, duty);
#elif defined(ARDUINO_ARCH_ESP32)
  ledcWrite(FLASH_LEDC_CHANNEL, duty);
#else
  digitalWrite(FLASH_GPIO_NUM, FLASH_ACTIVE_HIGH ? HIGH : LOW);
#endif
#else
  (void)brightness;
#endif
}

static void flashOff() {
#if ENABLE_FLASH
#if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
  ledcWrite(FLASH_GPIO_NUM, FLASH_ACTIVE_HIGH ? 0 : 255);
#elif defined(ARDUINO_ARCH_ESP32)
  ledcWrite(FLASH_LEDC_CHANNEL, FLASH_ACTIVE_HIGH ? 0 : 255);
#else
  digitalWrite(FLASH_GPIO_NUM, FLASH_ACTIVE_HIGH ? LOW : HIGH);
#endif
#endif
}

static bool connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  Serial.print("Connecting to WiFi");
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    if (millis() - start > 20000) {
      Serial.println("\nWiFi connect timeout");
      return false;
    }
  }

  Serial.println("\nWiFi connected");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());
  return true;
}

static void buttonsSetup() {
#if ENABLE_LOCAL_BUTTONS
  pinMode(BTN_DRYEYE_GPIO, INPUT_PULLUP);
  pinMode(BTN_CATARACT_GPIO, INPUT_PULLUP);
  _btnLastStateDryeye = digitalRead(BTN_DRYEYE_GPIO);
  _btnLastStateCataract = digitalRead(BTN_CATARACT_GPIO);
#endif
}

static void postHardwareButtonEvent(int buttonId) {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  HTTPClient http;
  static WiFiClient wifiClient;
  wifiClient.setNoDelay(true);
  http.setReuse(true);
  http.setTimeout(1500);

#if defined(ESP_ARDUINO_VERSION_MAJOR)
  http.begin(wifiClient, HW_EVENT_URL);
#else
  http.begin(HW_EVENT_URL);
#endif
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Connection", "keep-alive");

  String body;
  body.reserve(160);
  body += '{';
  body += "\"device_id\":\"esp32cam1\",";
  body += "\"event\":\"button\",";
  body += "\"button\":" + String(buttonId) + ',';
  body += "\"action\":\"press\",";
  body += "\"ts\":" + String((uint32_t)time(nullptr));
  body += '}';

  int code = http.POST((uint8_t*)body.c_str(), body.length());
  if (code <= 0) {
  }
  http.end();
}

static void handleButtons() {
#if ENABLE_LOCAL_BUTTONS
  const int sDry = digitalRead(BTN_DRYEYE_GPIO);
  const int sCat = digitalRead(BTN_CATARACT_GPIO);
  const uint32_t now = millis();

  if (_btnLastStateDryeye == HIGH && sDry == LOW) {
    if (now - _btnLastMsDryeye > BTN_DEBOUNCE_MS) {
      _btnLastMsDryeye = now;
      postHardwareButtonEvent(HW_BTN_DRYEYE_ID);
      Serial.println("Button: DRY EYE");
    }
  }

  if (_btnLastStateCataract == HIGH && sCat == LOW) {
    if (now - _btnLastMsCataract > BTN_DEBOUNCE_MS) {
      _btnLastMsCataract = now;
      postHardwareButtonEvent(HW_BTN_CATARACT_ID);
      Serial.println("Button: CATARACT");
    }
  }

  _btnLastStateDryeye = sDry;
  _btnLastStateCataract = sCat;
#endif
}

static void postSnapshot() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi not connected");
    return;
  }

#if ENABLE_FLASH
  if (FLASH_MODE == FLASH_CAPTURE_ONLY) {
    flashOn(FLASH_BRIGHTNESS);
    delay(60);
  }
#endif

  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Camera capture failed");
#if ENABLE_FLASH
    if (FLASH_MODE == FLASH_CAPTURE_ONLY) {
      flashOff();
    }
#endif
    return;
  }

  if (fb->format != PIXFORMAT_JPEG) {
    Serial.println("Frame is not JPEG; check PIXFORMAT_JPEG");
    esp_camera_fb_return(fb);
    return;
  }

  static uint32_t frameCounter = 0;

  HTTPClient http;
  static WiFiClient wifiClient;
  wifiClient.setNoDelay(true);
  http.setReuse(true);
  http.setTimeout(8000);
#if defined(ESP_ARDUINO_VERSION_MAJOR)
  http.begin(wifiClient, SERVER_URL);
#else
  http.begin(SERVER_URL);
#endif
  http.addHeader("Content-Type", "image/jpeg");
  http.addHeader("Connection", "keep-alive");

  int code = http.POST(fb->buf, fb->len);
  frameCounter++;

  if (code <= 0) {
    Serial.printf("HTTP POST failed: %s\n", http.errorToString(code).c_str());
  } else if ((frameCounter % 30) == 0) {
    Serial.printf("Frames sent: %lu (last HTTP %d)\n", (unsigned long)frameCounter, code);
  }

  http.end();
  esp_camera_fb_return(fb);

#if ENABLE_FLASH
  if (FLASH_MODE == FLASH_CAPTURE_ONLY) {
    flashOff();
  }
#endif
}

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(false);

  _uartLine.reserve(UART_LINE_MAX);

  flashSetup();

  if (!initCamera()) {
    Serial.println("Camera init failed; rebooting in 5s");
    delay(5000);
    ESP.restart();
  }

  if (!connectWiFi()) {
    Serial.println("WiFi failed; rebooting in 5s");
    delay(5000);
    ESP.restart();
  }

  buttonsSetup();

  // Flash/torch intentionally disabled by default.
  // If you re-enable it, FLASH_MODE will control behavior.
#if ENABLE_FLASH
  if (FLASH_MODE == FLASH_TORCH) {
    flashOn(FLASH_BRIGHTNESS);
    Serial.println("Flash: TORCH ON");
  } else if (FLASH_MODE == FLASH_CAPTURE_ONLY) {
    Serial.println("Flash: CAPTURE ONLY");
  } else {
    Serial.println("Flash: OFF");
  }
#else
  Serial.println("Flash: DISABLED");
#endif

  Serial.printf("Ready. Streaming frames every %lu ms...\n", (unsigned long)STREAM_INTERVAL_MS);
}

void loop() {
  pollUartCommands();
  handleButtons();

  const uint32_t now = millis();
  if (now - _lastStreamMs >= STREAM_INTERVAL_MS) {
    _lastStreamMs = now;
    postSnapshot();
  }
}
