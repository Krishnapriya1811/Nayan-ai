#pragma once

#include <Arduino.h>

// Keep custom enums in a header so the Arduino IDE's auto-generated function
// prototypes (inserted after includes) can see these types.

enum LedMode : uint8_t {
  LED_IDLE_OFF = 0,
  LED_FAST_BLINK,
  LED_SLOW_BLINK,
  LED_SOLID_ON
};

enum BuzzerMode : uint8_t {
  BUZZER_OFF = 0,
  BUZZER_FAST_BEEP,
  BUZZER_SLOW_BEEP,
  BUZZER_SOLID_ON
};
