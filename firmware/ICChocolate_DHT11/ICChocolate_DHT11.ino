#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>
#include <esp_system.h>
#include <math.h>
#include "secrets.h"

constexpr uint8_t DHT_PIN = 4;
constexpr uint8_t ATTEMPTS = 4;
constexpr unsigned long SAMPLE_GAP_MS = 10000;
constexpr unsigned long CYCLE_MS = 60000;
constexpr unsigned long WIFI_TIMEOUT_MS = 12000;
constexpr char INGEST_URL[] = "http://192.168.18.244:8000/api/sensor/lecturas/";

DHT dht(DHT_PIN, DHT11);

String newReadingId() {
  uint8_t bytes[16];
  esp_fill_random(bytes, sizeof(bytes));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  char value[37];
  snprintf(value, sizeof(value),
           "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
           bytes[0], bytes[1], bytes[2], bytes[3], bytes[4], bytes[5], bytes[6], bytes[7],
           bytes[8], bytes[9], bytes[10], bytes[11], bytes[12], bytes[13], bytes[14], bytes[15]);
  return String(value);
}

bool connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return true;
  Serial.println("Wi-Fi desconectado; intentando reconectar...");
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < WIFI_TIMEOUT_MS) {
    delay(500);
    Serial.print('.');
  }
  Serial.println();
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Sin Wi-Fi. Se intentará de nuevo en el próximo ciclo.");
    return false;
  }
  Serial.print("Wi-Fi conectado. IP del ESP32: ");
  Serial.println(WiFi.localIP());
  return true;
}

bool sendReading(const String &body) {
  if (!connectWiFi()) return false;
  HTTPClient http;
  http.setTimeout(8000);
  if (!http.begin(INGEST_URL)) {
    Serial.println("No se pudo iniciar HTTP.");
    return false;
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", String("Bearer ") + DEVICE_TOKEN);
  int status = http.POST(body);
  if (status == 201 || status == 200) {
    Serial.printf("Lectura recibida por ICChocolate (HTTP %d).\n", status);
    http.end();
    return true;
  }
  if (status < 0) Serial.printf("Error de conexión HTTP: %s\n", http.errorToString(status).c_str());
  else Serial.printf("El servidor rechazó la lectura: HTTP %d, %s\n", status, http.getString().c_str());
  http.end();
  return false;
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("ICChocolate DHT11 iniciando...");
  dht.begin();
  WiFi.mode(WIFI_STA);
  connectWiFi();
}

void loop() {
  unsigned long cycleStart = millis();
  float temperatureSum = 0;
  float humiditySum = 0;
  uint8_t valid = 0;

  for (uint8_t i = 0; i < ATTEMPTS; ++i) {
    float humidity = dht.readHumidity();
    float temperature = dht.readTemperature();
    if (isnan(temperature) || isnan(humidity) || temperature < 0 || temperature > 50 || humidity < 20 || humidity > 90) {
      Serial.printf("Intento %u/4: lectura inválida del DHT11.\n", i + 1);
    } else {
      temperatureSum += temperature;
      humiditySum += humidity;
      ++valid;
      Serial.printf("Intento %u/4: %.1f °C, %.1f %% HR.\n", i + 1, temperature, humidity);
    }
    if (i + 1 < ATTEMPTS) delay(SAMPLE_GAP_MS);
  }

  if (valid == 0) {
    Serial.println("Ninguna muestra válida; no se enviará una lectura inventada.");
  } else {
    float meanTemperature = temperatureSum / valid;
    float meanHumidity = humiditySum / valid;
    String readingId = newReadingId();
    String body = String("{\"reading_id\":\"") + readingId +
                  "\",\"temperature_c\":" + String(meanTemperature, 2) +
                  ",\"humidity_percent\":" + String(meanHumidity, 2) +
                  ",\"sample_count\":" + String(valid) + "}";
    Serial.printf("Promedio de %u muestra(s): %.2f °C, %.2f %% HR. Enviando...\n", valid, meanTemperature, meanHumidity);
    for (uint8_t retry = 1; retry <= 3; ++retry) {
      if (sendReading(body)) break;
      if (retry < 3) {
        Serial.printf("Reintento HTTP %u/3 en 5 segundos.\n", retry + 1);
        delay(5000);
      }
    }
  }

  unsigned long elapsed = millis() - cycleStart;
  if (elapsed < CYCLE_MS) delay(CYCLE_MS - elapsed);
}
