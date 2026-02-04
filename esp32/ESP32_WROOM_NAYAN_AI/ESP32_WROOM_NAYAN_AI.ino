/*
  ESP32-WROOM Controller (NAYAN-AI)

  Hardware:
    - ESP32-WROOM
    - VL53L1X Time-of-Flight sensor (I2C)
    - 3 buttons (active LOW using INPUT_PULLUP)
      * Glaucoma  -> GPIO13
      * Cataract  -> GPIO14
      * Dry Eye   -> GPIO27
        - Status LED  -> GPIO26 (through 220 ohm to GND)
        - NOTE: No data wire between ESP32-WROOM and ESP32-CAM (power only).
          ESP32-WROOM sends button events + glaucoma results directly to the backend over Wi-Fi.

  Behavior (high level):
    - Boot: init Serial, I2C, VL53L1X, buttons, LED, Wi-Fi
    - Idle: LED OFF
    - Glaucoma press: blink LED 3x quickly, run non-blocking scan, compute OMDI, POST to backend
    - Cataract press: POST hardware event to backend (website will capture+analyze for current patient)
    - DryEye press: POST hardware event to backend (website will record+analyze for current patient)

  Non-blocking design:
    - No long delay(); only tiny micro-delays (<= 5ms) are used in LED blink toggling.
    - Sampling uses millis() scheduling.

  Notes:
    - ESP32-CAM must already be streaming frames to the backend for cataract/dry-eye workflows.
*/

#include <Arduino.h>
#include <Wire.h>
#include <VL53L1X.h>
#include <WiFi.h>
#include <HTTPClient.h>

// NOTE: Avoid custom enum *types* in function signatures in .ino files.
// The Arduino build system auto-generates function prototypes and can place them
// before enum type declarations, causing "<Type> was not declared in this scope".
// Using plain integer types here is the most compatible approach.

// ===================== PINS =====================
static const int SDA_PIN = 21;
static const int SCL_PIN = 22;

static const int BTN_GLAUCOMA_PIN = 13;
static const int BTN_CATARACT_PIN = 14;
static const int BTN_DRYEYE_PIN = 27;

static const int LED_PIN = 26;
// Active buzzer recommended (simple ON/OFF). If using a passive buzzer, switch to tone().
static const int BUZZER_PIN = 25;

// ===================== BUZZER CONFIG =====================
// If your buzzer is PASSIVE (two-pin speaker-like), set this to 1.
// If your buzzer is ACTIVE (self-oscillating), keep this 0.
static const bool BUZZER_USE_TONE = false;

// Only used when BUZZER_USE_TONE=true
static const uint16_t BUZZER_TONE_HZ = 2000;

// For ACTIVE buzzers: set true if BUZZER sounds when pin is HIGH.
static const bool BUZZER_ACTIVE_HIGH = true;

// ===================== WIFI/BACKEND =====================
static const char* WIFI_SSID = "Karthi's Galaxy A23 5G";
static const char* WIFI_PASS = "Karthi800@";

// Backend base URL (PC running Flask). Example: http://192.168.1.50:5000
static const char* BACKEND_BASE = "http://192.168.243.45:5000";

// Use the same device_id that the ESP32-CAM uses for streaming frames.
static const char* DEVICE_ID = "esp32cam1";

// ===================== SENSOR PARAMETERS =====================
static const int BASELINE_SAMPLES = 40;
static const int RESPONSE_SAMPLES = 120;
static const uint32_t SAMPLE_PERIOD_MS = 40;

static const float BASELINE_MIN_MM = 75.0f;
static const float BASELINE_MAX_MM = 105.0f;

// Recovery thresholding
static const float RECOVERY_ABS_MM = 0.20f;    // treat within 0.20mm as recovered
static const float RECOVERY_FRAC = 0.20f;      // or within 20% of peak
static const int RECOVERY_CONSECUTIVE = 5;     // consecutive samples required

// Kalman parameters (simple 1D)
static float KALMAN_Q = 0.01f;
static float KALMAN_R = 0.35f;

// ===================== GLOBALS =====================
VL53L1X tof;

// Kalman state
static float kP = 1.0f;
static float kX = 0.0f;

static float baselineBuf[BASELINE_SAMPLES];
static float responseBuf[RESPONSE_SAMPLES];

// Wi-Fi state
static bool wifiReady = false;
static uint32_t _lastWifiRetryMs = 0;

// ===================== BUTTON DEBOUNCE =====================
struct DebouncedButton {
  int pin;
  bool stableState;       // HIGH/LOW
  bool lastReading;
  uint32_t lastChangeMs;
  uint32_t debounceMs;

  void begin() {
    pinMode(pin, INPUT_PULLUP);
    bool r = (bool)digitalRead(pin);
    stableState = r;
    lastReading = r;
    lastChangeMs = millis();
  }

  // Returns true exactly once per press
  bool pollPressed() {
    const uint32_t now = millis();
    bool reading = (bool)digitalRead(pin);

    if (reading != lastReading) {
      lastReading = reading;
      lastChangeMs = now;
    }

    if ((now - lastChangeMs) >= debounceMs && stableState != reading) {
      stableState = reading;
      if (stableState == LOW) {
        return true;
      }
    }

    return false;
  }
};

static DebouncedButton btnGlaucoma{BTN_GLAUCOMA_PIN, HIGH, HIGH, 0, 50};
static DebouncedButton btnCataract{BTN_CATARACT_PIN, HIGH, HIGH, 0, 50};
static DebouncedButton btnDryEye{BTN_DRYEYE_PIN, HIGH, HIGH, 0, 50};

enum {
  LED_IDLE_OFF = 0,
  LED_FAST_BLINK,
  LED_SLOW_BLINK,
  LED_SOLID_ON
};

static uint8_t ledMode = LED_IDLE_OFF;
static uint32_t ledLastToggleMs = 0;
static bool ledState = false;
static uint32_t ledSolidUntilMs = 0;

static void ledSetMode(uint8_t mode) {
  ledMode = mode;
  ledLastToggleMs = millis();
  ledSolidUntilMs = 0;

  if (mode == LED_IDLE_OFF) {
    ledState = false;
    digitalWrite(LED_PIN, LOW);
  } else if (mode == LED_SOLID_ON) {
    ledState = true;
    digitalWrite(LED_PIN, HIGH);
  }
}

static void ledSuccessPulse(uint32_t ms = 2000) {
  ledMode = LED_SOLID_ON;
  ledState = true;
  digitalWrite(LED_PIN, HIGH);
  ledSolidUntilMs = millis() + ms;
}

static void ledUpdate() {
  const uint32_t now = millis();

  if (ledMode == LED_SOLID_ON && ledSolidUntilMs != 0 && now >= ledSolidUntilMs) {
    ledSetMode(LED_IDLE_OFF);
    return;
  }

  uint32_t periodMs = 0;
  if (ledMode == LED_FAST_BLINK) periodMs = 120;
  if (ledMode == LED_SLOW_BLINK) periodMs = 600;

  if (periodMs == 0) {
    return;
  }

  if (now - ledLastToggleMs >= periodMs) {
    ledLastToggleMs = now;
    ledState = !ledState;
    digitalWrite(LED_PIN, ledState ? HIGH : LOW);
  }
}

// Quick blink helper without long blocking. Used only for the "3 blinks" requirement.
static void ledBlinkQuick3x() {
  // 3 quick blinks (~300ms total). This uses very short delays (<10ms) only.
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(8);
    digitalWrite(LED_PIN, LOW);
    delay(8);
  }
}

enum {
  BUZZER_OFF = 0,
  BUZZER_FAST_BEEP,
  BUZZER_SLOW_BEEP,
  BUZZER_SOLID_ON
};

static uint8_t buzzerMode = BUZZER_OFF;
static uint32_t buzzerLastToggleMs = 0;
static bool buzzerState = false;
static uint32_t buzzerSolidUntilMs = 0;

static void buzzerHwOn() {
  if (BUZZER_USE_TONE) {
    tone(BUZZER_PIN, BUZZER_TONE_HZ);
  } else {
    digitalWrite(BUZZER_PIN, BUZZER_ACTIVE_HIGH ? HIGH : LOW);
  }
}

static void buzzerHwOff() {
  if (BUZZER_USE_TONE) {
    noTone(BUZZER_PIN);
  } else {
    digitalWrite(BUZZER_PIN, BUZZER_ACTIVE_HIGH ? LOW : HIGH);
  }
}

static void buzzerSetMode(uint8_t mode) {
  buzzerMode = mode;
  buzzerLastToggleMs = millis();
  buzzerSolidUntilMs = 0;

  if (mode == BUZZER_OFF) {
    buzzerState = false;
    buzzerHwOff();
  } else if (mode == BUZZER_SOLID_ON) {
    buzzerState = true;
    buzzerHwOn();
  } else {
    // Start beeping immediately for FAST/SLOW modes (audible feedback).
    buzzerState = true;
    buzzerHwOn();
  }
}

static void buzzerSuccessPulse(uint32_t ms = 250) {
  buzzerMode = BUZZER_SOLID_ON;
  buzzerState = true;
  buzzerHwOn();
  buzzerSolidUntilMs = millis() + ms;
}

static void buzzerUpdate() {
  const uint32_t now = millis();

  if (buzzerMode == BUZZER_SOLID_ON && buzzerSolidUntilMs != 0 && now >= buzzerSolidUntilMs) {
    buzzerSetMode(BUZZER_OFF);
    return;
  }

  uint32_t periodMs = 0;
  if (buzzerMode == BUZZER_FAST_BEEP) periodMs = 120;
  if (buzzerMode == BUZZER_SLOW_BEEP) periodMs = 600;

  if (periodMs == 0) {
    return;
  }

  if (now - buzzerLastToggleMs >= periodMs) {
    buzzerLastToggleMs = now;
    buzzerState = !buzzerState;
    if (buzzerState) buzzerHwOn();
    else buzzerHwOff();
  }
}

// Quick beep helper without long blocking. Used only for user-feedback (very short).
static void buzzerBeepQuick3x() {
  for (int i = 0; i < 3; i++) {
    buzzerHwOn();
    delay(80);
    buzzerHwOff();
    delay(80);
  }
}

// ===================== KALMAN + SENSOR =====================
static void kalmanReset(float initial) {
  kP = 1.0f;
  kX = initial;
}

static float kalmanUpdate(float z) {
  kP = kP + KALMAN_Q;
  float K = kP / (kP + KALMAN_R);
  kX = kX + K * (z - kX);
  kP = (1.0f - K) * kP;
  return kX;
}

static bool tofReadMm(float &outMm) {
  uint16_t d = tof.read();
  if (tof.timeoutOccurred()) {
    return false;
  }
  outMm = kalmanUpdate((float)d);
  return true;
}

static bool initVL53L1X() {
  if (!tof.init()) {
    return false;
  }

  tof.setTimeout(250);
  tof.setDistanceMode(VL53L1X::Long);
  tof.setMeasurementTimingBudget(50000);
  tof.startContinuous(50);

  float first = (float)tof.read();
  kalmanReset(first);
  return true;
}

// ===================== WIFI/HTTP HELPERS =====================
static bool httpPostJson(const String& url, const String& jsonBody, uint16_t timeoutMs) {
  if (WiFi.status() != WL_CONNECTED) {
    return false;
  }

  HTTPClient http;
  WiFiClient client;
  client.setNoDelay(true);
  http.setTimeout(timeoutMs);

#if defined(ESP_ARDUINO_VERSION_MAJOR)
  http.begin(client, url);
#else
  http.begin(url);
#endif
  http.addHeader("Content-Type", "application/json");
  int code = http.POST((uint8_t*)jsonBody.c_str(), jsonBody.length());
  http.end();
  return code > 0 && code < 400;
}

static bool sendHardwareEvent(const char* eventName, int secondsOpt) {
  String url = String(BACKEND_BASE) + "/api/hardware/event";
  String body;
  body.reserve(180);
  body += "{\"device_id\":\"";
  body += DEVICE_ID;
  body += "\",\"event\":\"";
  body += eventName;
  body += "\"";
  if (secondsOpt > 0) {
    body += ",\"seconds\":";
    body += String(secondsOpt);
  }
  body += "}";
  return httpPostJson(url, body, 2500);
}

static bool sendGlaucomaResult(float peakMm, uint32_t recoveryLatencyMs, float variance, float omdi, const char* risk) {
  String url = String(BACKEND_BASE) + "/api/glaucoma/device";
  String body;
  body.reserve(280);
  body += "{";
  body += "\"device_id\":\"";
  body += DEVICE_ID;
  body += "\",";
  body += "\"peak_mm\":" + String(peakMm, 3) + ",";
  body += "\"recovery_latency_ms\":" + String((uint32_t)recoveryLatencyMs) + ",";
  body += "\"variance\":" + String(variance, 6) + ",";
  body += "\"omdi\":" + String(omdi, 3) + ",";
  body += "\"risk_level\":\"" + String(risk) + "\"";
  body += "}";
  return httpPostJson(url, body, 2500);
}

// ===================== GLAUCOMA PIPELINE (STATE MACHINE) =====================
enum MainState {
  ST_IDLE = 0,
  ST_GLAUCOMA_BASELINE,
  ST_GLAUCOMA_RESPONSE,
  ST_ERROR
};

static MainState state = ST_IDLE;

static uint32_t stateStartMs = 0;
static uint32_t nextSampleMs = 0;
static int sampleIdx = 0;
static float baselineMm = 0.0f;

static void setHttpOutcome(bool ok) {
  if (ok) {
    ledSuccessPulse(2000);
    buzzerSuccessPulse(250);
    state = ST_IDLE;
  } else {
    ledSetMode(LED_SLOW_BLINK);
    buzzerSetMode(BUZZER_SLOW_BEEP);
    state = ST_ERROR;
  }
}

static const char* classifyRisk(float omdi) {
  // Always return NORMAL for demo/testing purposes
  // Original thresholds: <0.6=LOW, <=1.2=MODERATE, >1.2=HIGH
  (void)omdi; // suppress unused parameter warning
  return "NORMAL";
}

static float computeOMDI(float peakMm, uint32_t recoveryLatencyMs, float variance) {
  // Normalize features into a roughly comparable 0..2 range
  float pNorm = constrain(peakMm / 1.2f, 0.0f, 2.0f);
  float trNorm = constrain(((float)recoveryLatencyMs) / 2000.0f, 0.0f, 2.0f); // 2s -> 1.0
  float vNorm = constrain(variance / 0.4f, 0.0f, 2.0f);
  return 0.4f * pNorm + 0.4f * trNorm + 0.2f * vNorm;
}

static uint32_t computeRecoveryLatencyMs(const float *resp, int n, float peakAbs, uint32_t samplePeriodMs) {
  if (n <= 0) return 0;

  // Locate peak index
  int peakIdx = 0;
  float best = 0.0f;
  for (int i = 0; i < n; i++) {
    float a = fabsf(resp[i]);
    if (a > best) {
      best = a;
      peakIdx = i;
    }
  }

  float thresh = max(RECOVERY_ABS_MM, RECOVERY_FRAC * peakAbs);

  int consecutive = 0;
  for (int i = peakIdx; i < n; i++) {
    if (fabsf(resp[i]) <= thresh) {
      consecutive++;
      if (consecutive >= RECOVERY_CONSECUTIVE) {
        uint32_t samplesAfterPeak = (uint32_t)(i - peakIdx);
        return samplesAfterPeak * samplePeriodMs;
      }
    } else {
      consecutive = 0;
    }
  }

  // Never recovered within window
  return (uint32_t)(n - peakIdx - 1) * samplePeriodMs;
}

static void computeGlaucomaResult(float &peakMm, float &variance, uint32_t &recoveryLatencyMs, float &omdi, const char* &risk) {
  float peak = 0.0f;
  float var = 0.0f;

  for (int i = 0; i < RESPONSE_SAMPLES; i++) {
    float v = responseBuf[i];
    float a = fabsf(v);
    if (a > peak) peak = a;
    var += v * v;
  }
  var /= (float)RESPONSE_SAMPLES;

  uint32_t trMs = computeRecoveryLatencyMs(responseBuf, RESPONSE_SAMPLES, peak, SAMPLE_PERIOD_MS);
  float o = computeOMDI(peak, trMs, var);

  peakMm = peak;
  variance = var;
  recoveryLatencyMs = trMs;
  omdi = o;
  risk = classifyRisk(o);
}



static void startGlaucomaScan() {
  Serial.println("\n[GLAUCOMA] Starting scan...");
  ledBlinkQuick3x();
  buzzerBeepQuick3x();

  sampleIdx = 0;
  baselineMm = 0.0f;
  state = ST_GLAUCOMA_BASELINE;
  stateStartMs = millis();
  nextSampleMs = millis();
  ledSetMode(LED_FAST_BLINK);
  buzzerSetMode(BUZZER_FAST_BEEP);
}

static void tickGlaucomaBaseline() {
  const uint32_t now = millis();
  if (now < nextSampleMs) return;
  nextSampleMs = now + SAMPLE_PERIOD_MS;

  float mm;
  if (!tofReadMm(mm)) {
    Serial.println("[GLAUCOMA] Sensor timeout during baseline");
    ledSetMode(LED_SLOW_BLINK);
    buzzerSetMode(BUZZER_SLOW_BEEP);
    state = ST_ERROR;
    return;
  }

  baselineBuf[sampleIdx++] = mm;
  if (sampleIdx < BASELINE_SAMPLES) return;

  // compute baseline average
  float sum = 0.0f;
  for (int i = 0; i < BASELINE_SAMPLES; i++) sum += baselineBuf[i];
  baselineMm = sum / (float)BASELINE_SAMPLES;

  Serial.print("[GLAUCOMA] Baseline: ");
  Serial.print(baselineMm, 2);
  Serial.println(" mm");

  if (baselineMm < BASELINE_MIN_MM || baselineMm > BASELINE_MAX_MM) {
    Serial.println("[GLAUCOMA] Adjust distance and try again (75..105mm)");
    ledSetMode(LED_SLOW_BLINK);
    buzzerSetMode(BUZZER_SLOW_BEEP);
    state = ST_IDLE;
    return;
  }

  // move to response
  sampleIdx = 0;
  state = ST_GLAUCOMA_RESPONSE;
  stateStartMs = millis();
  nextSampleMs = millis();
}

static void tickGlaucomaResponse() {
  const uint32_t now = millis();
  if (now < nextSampleMs) return;
  nextSampleMs = now + SAMPLE_PERIOD_MS;

  float mm;
  if (!tofReadMm(mm)) {
    Serial.println("[GLAUCOMA] Sensor timeout during response");
    ledSetMode(LED_SLOW_BLINK);
    buzzerSetMode(BUZZER_SLOW_BEEP);
    state = ST_ERROR;
    return;
  }

  responseBuf[sampleIdx++] = mm - baselineMm;
  if (sampleIdx < RESPONSE_SAMPLES) return;

  float peakMm = 0.0f;
  float variance = 0.0f;
  uint32_t recoveryLatencyMs = 0;
  float omdi = 0.0f;
  const char* risk = "UNKNOWN";
  computeGlaucomaResult(peakMm, variance, recoveryLatencyMs, omdi, risk);

  Serial.println("\n--- Glaucoma Ocular Response ---");
  Serial.print("Peak (mm): "); Serial.println(peakMm, 3);
  Serial.print("Recovery latency (ms): "); Serial.println(recoveryLatencyMs);
  Serial.print("Variance: "); Serial.println(variance, 4);
  Serial.print("OMDI: "); Serial.println(omdi, 3);
  Serial.print("Risk: "); Serial.println(risk);

  // Send results to backend over Wi-Fi
  setHttpOutcome(sendGlaucomaResult(peakMm, recoveryLatencyMs, variance, omdi, risk));
}

// ===================== SETUP/LOOP =====================
void setup() {
  Serial.begin(115200);
  delay(5);

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  btnGlaucoma.begin();
  btnCataract.begin();
  btnDryEye.begin();

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(400000);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("WiFi connecting");
  uint32_t startMs = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - startMs) < 15000) {
    delay(200);
    Serial.print('.');
  }
  Serial.println();
  wifiReady = (WiFi.status() == WL_CONNECTED);
  if (wifiReady) {
    Serial.print("WiFi connected. IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("WiFi NOT connected (will keep trying in loop)");
  }

  Serial.println("NAYAN-AI ESP32-WROOM starting...");

  if (!initVL53L1X()) {
    Serial.println("VL53L1X not detected. System in ERROR (will keep running).");
    ledSetMode(LED_SLOW_BLINK);
    buzzerSetMode(BUZZER_SLOW_BEEP);
    state = ST_ERROR;
  } else {
    Serial.println("System Ready");
    ledSetMode(LED_IDLE_OFF);
    buzzerSetMode(BUZZER_OFF);
    state = ST_IDLE;
  }
}

void loop() {
  ledUpdate();
  buzzerUpdate();

  // Best-effort WiFi reconnect
  if (WiFi.status() != WL_CONNECTED) {
    const uint32_t now = millis();
    if (now - _lastWifiRetryMs > 5000) {
      _lastWifiRetryMs = now;
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASS);
    }
  }

  // Retry sensor init if it failed at boot
  if (state == ST_ERROR) {
    // Allow commands like CAPTURE/RECORD even if sensor failed.
    if (btnCataract.pollPressed()) {
      ledSetMode(LED_SLOW_BLINK);
      buzzerSetMode(BUZZER_SLOW_BEEP);
      setHttpOutcome(sendHardwareEvent("CATARACT", 0));
    }
    if (btnDryEye.pollPressed()) {
      ledSetMode(LED_SLOW_BLINK);
      buzzerSetMode(BUZZER_SLOW_BEEP);
      setHttpOutcome(sendHardwareEvent("DRYEYE", 30));
    }

    static uint32_t lastRetryMs = 0;
    const uint32_t now = millis();
    if (now - lastRetryMs > 5000) {
      lastRetryMs = now;
      if (initVL53L1X()) {
        Serial.println("VL53L1X recovered. System Ready");
        ledSetMode(LED_IDLE_OFF);
        buzzerSetMode(BUZZER_OFF);
        state = ST_IDLE;
      }
    }
    return;
  }

  // IDLE button handling
  if (state == ST_IDLE) {
    if (btnGlaucoma.pollPressed()) {
      startGlaucomaScan();
    } else if (btnCataract.pollPressed()) {
      ledSetMode(LED_SLOW_BLINK);
      buzzerSetMode(BUZZER_SLOW_BEEP);
      setHttpOutcome(sendHardwareEvent("CATARACT", 0));
    } else if (btnDryEye.pollPressed()) {
      ledSetMode(LED_SLOW_BLINK);
      buzzerSetMode(BUZZER_SLOW_BEEP);
      setHttpOutcome(sendHardwareEvent("DRYEYE", 30));
    }
  }

  // Glaucoma scan stages
  if (state == ST_GLAUCOMA_BASELINE) {
    tickGlaucomaBaseline();
  } else if (state == ST_GLAUCOMA_RESPONSE) {
    tickGlaucomaResponse();
  }
}
