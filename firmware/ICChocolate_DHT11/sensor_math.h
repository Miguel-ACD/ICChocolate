#pragma once

constexpr float averageFour(float a, float b, float c, float d) {
  return (a + b + c + d) / 4.0f;
}

static_assert(averageFour(10.0f, 12.0f, 14.0f, 16.0f) == 13.0f,
              "El promedio de temperatura debe ser 13");
static_assert(averageFour(40.0f, 44.0f, 48.0f, 52.0f) == 46.0f,
              "El promedio de humedad debe ser 46");
