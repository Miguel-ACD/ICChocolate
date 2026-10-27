#include <WiFi.h>
#include <HTTPClient.h>
#include <NetworkClientSecure.h>
#include <time.h>
#include <DHT.h>
#include <esp_system.h>
#include <math.h>
#include "dns_addresses.h"
#include "sensor_math.h"
#include "secrets.h"
#include "letsencrypt_roots.h"
#ifndef REMOTE_INGEST_URL
#define REMOTE_INGEST_URL ""
#endif

constexpr uint8_t DHT_PIN = 4;
constexpr uint8_t ATTEMPTS = 4;
constexpr unsigned long SAMPLE_GAP_MS = 10000;
constexpr unsigned long CYCLE_MS = 60000;
constexpr unsigned long WIFI_TIMEOUT_MS = 12000;
constexpr char LOCAL_INGEST_URL[] = "http://192.168.18.244:8000/api/v1/dispositivos/me/ciclos";

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

bool ensureClock() {
  if (time(nullptr) >= 1700000000) return true;
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  unsigned long started = millis();
  while (time(nullptr) < 1700000000 && millis() - started < 12000) delay(250);
  if (time(nullptr) < 1700000000) {
    Serial.println("Sin hora de red; se reintentará HTTPS en el próximo ciclo.");
    return false;
  }
  return true;
}

bool sendRemoteReading(const String &body) {
  String url = REMOTE_INGEST_URL;
  if (!url.startsWith("https://")) {
    Serial.println("La URL remota debe usar HTTPS.");
    return false;
  }
  int pathStart = url.indexOf('/', 8);
  String authority = pathStart < 0 ? url.substring(8) : url.substring(8, pathStart);
  String path = pathStart < 0 ? "/" : url.substring(pathStart);
  int colon = authority.lastIndexOf(':');
  String host = colon < 0 ? authority : authority.substring(0, colon);
  uint16_t port = colon < 0 ? 443 : static_cast<uint16_t>(authority.substring(colon + 1).toInt());
  if (host.isEmpty() || port == 0) return false;

  IPAddress candidates[6];
  uint8_t count = resolveAllIPv4(host, candidates, 6);
  if (count == 0) {
    Serial.println("DNS completo no disponible; se probará el resolver integrado.");
    if (WiFi.hostByName(host.c_str(), candidates[0])) count = 1;
  }
  if (count == 0) {
    Serial.println("Funnel no devolvió direcciones IPv4.");
    return false;
  }
  String headers = String("POST ") + path + " HTTP/1.1\r\nHost: " + host +
                   "\r\nAuthorization: Bearer " + DEVICE_TOKEN +
                   "\r\nContent-Type: application/json\r\nContent-Length: " + String(body.length()) +
                   "\r\nConnection: close\r\n\r\n";
  for (uint8_t i = 0; i < count; ++i) {
    NetworkClientSecure client;
    client.setHandshakeTimeout(8);
    client.setTimeout(8000);
    Serial.printf("Funnel %u/%u: %s; memoria libre: %u bytes.\n",
                  i + 1, count, candidates[i].toString().c_str(), ESP.getFreeHeap());
    if (!client.connect(candidates[i], port, host.c_str(), LETS_ENCRYPT_ROOTS, nullptr, nullptr)) {
      char detail[128] = {};
      int code = client.lastError(detail, sizeof(detail));
      Serial.printf("Falló TLS: %d %s.\n", code, detail);
      client.stop();
      continue;
    }
    if (client.print(headers) != headers.length() || client.print(body) != body.length()) {
      Serial.println("No se pudo enviar la solicitud HTTPS.");
      client.stop();
      continue;
    }
    String statusLine = client.readStringUntil('\n');
    client.stop();
    int firstSpace = statusLine.indexOf(' ');
    int status = firstSpace < 0 ? 0 : statusLine.substring(firstSpace + 1).toInt();
    if (status == 201 || status == 200) {
      Serial.printf("Lectura recibida por ICChocolate (HTTP %d).\n", status);
      return true;
    }
    if (status >= 400 && status < 500) {
      Serial.printf("El servidor rechazó la lectura: HTTP %d.\n", status);
      return false;
    }
    Serial.printf("Funnel no respondió correctamente: %s\n", statusLine.c_str());
  }
  return false;
}

bool sendReading(const String &body) {
  if (!connectWiFi()) return false;
  if (REMOTE_INGEST_URL[0] != '\0') {
    if (!ensureClock()) return false;
    return sendRemoteReading(body);
  }
  HTTPClient http;
  http.setTimeout(8000);
  if (!http.begin(LOCAL_INGEST_URL)) return false;
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", String("Bearer ") + DEVICE_TOKEN);
  int status = http.POST(body);
  if (status == 201 || status == 200) Serial.printf("Lectura recibida por ICChocolate (HTTP %d).\n", status);
  else if (status < 0) Serial.printf("Error de conexión HTTP: %s\n", http.errorToString(status).c_str());
  else Serial.printf("El servidor rechazó la lectura: HTTP %d.\n", status);
  http.end();
  return status == 201 || status == 200;
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
  time_t cycleEpoch = time(nullptr);
  float temperatures[ATTEMPTS] = {};
  float humidities[ATTEMPTS] = {};
  uint8_t valid = 0;

  for (uint8_t i = 0; i < ATTEMPTS; ++i) {
    float humidity = dht.readHumidity();
    float temperature = dht.readTemperature();
    if (isnan(temperature) || isnan(humidity) || temperature < 0 || temperature > 50 || humidity < 20 || humidity > 90) {
      Serial.printf("Intento %u/4: lectura inválida del DHT11.\n", i + 1);
    } else {
      temperatures[valid] = temperature;
      humidities[valid] = humidity;
      ++valid;
      Serial.printf("Intento %u/4: %.1f °C, %.1f %% HR.\n", i + 1, temperature, humidity);
    }
    if (i + 1 < ATTEMPTS) delay(SAMPLE_GAP_MS);
  }

  String cycleId = newReadingId();
  String body = String("{\"version\":1,\"ciclo_id\":\"") + cycleId + "\",";
  if (valid == ATTEMPTS) {
    float meanTemperature = averageFour(temperatures[0], temperatures[1], temperatures[2], temperatures[3]);
    float meanHumidity = averageFour(humidities[0], humidities[1], humidities[2], humidities[3]);
    body += String("\"estado\":\"VALIDO\",\"muestras_validas\":4,\"temperatura_c\":") +
            String(meanTemperature, 2) + ",\"humedad_pct\":" + String(meanHumidity, 2);
    Serial.printf("Promedio de 4 muestras: %.2f °C, %.2f %% HR. Enviando...\n", meanTemperature, meanHumidity);
  } else {
    body += String("\"estado\":\"INVALIDO\",\"muestras_validas\":") + String(valid) +
            ",\"temperatura_c\":null,\"humedad_pct\":null,\"error_codigo\":\"SENSOR_LECTURA\"";
    Serial.printf("Ciclo inválido: %u/4 muestras. Se envía estado sin promedio.\n", valid);
  }
  if (cycleEpoch >= 1700000000) {
    struct tm utc;
    gmtime_r(&cycleEpoch, &utc);
    char timestamp[25];
    strftime(timestamp, sizeof(timestamp), "%Y-%m-%dT%H:%M:%SZ", &utc);
    body += String(",\"ciclo_en\":\"") + timestamp + "\"";
  }
  body += "}";
  for (uint8_t retry = 1; retry <= 3; ++retry) {
    if (sendReading(body)) break;
    if (retry < 3) {
      Serial.printf("Reintento HTTP %u/3 en 5 segundos.\n", retry + 1);
      delay(5000);
    }
  }

  unsigned long elapsed = millis() - cycleStart;
  if (elapsed < CYCLE_MS) delay(CYCLE_MS - elapsed);
}
