#pragma once

#include <stdint.h>

struct GlaucomaResult {
  float peakMm;
  float variance;
  uint32_t recoveryLatencyMs;
  float omdi;
  const char* risk;
};
