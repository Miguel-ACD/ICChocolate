#pragma once
#include <WiFi.h>
#include <WiFiUdp.h>

// Arduino-ESP32's built-in DNS cache keeps only one A record. Read the full
// response so a failed Funnel relay does not block the other public relay.
static bool skipDnsName(const uint8_t *packet, size_t length, size_t &position) {
  while (position < length) {
    uint8_t label = packet[position++];
    if (label == 0) return true;
    if ((label & 0xc0) == 0xc0) {
      if (position >= length) return false;
      ++position;
      return true;
    }
    if ((label & 0xc0) != 0 || position + label > length) return false;
    position += label;
  }
  return false;
}

static uint8_t resolveAllIPv4(const String &host, IPAddress *addresses, uint8_t capacity) {
  IPAddress dns = WiFi.dnsIP();
  if (dns == IPAddress(0, 0, 0, 0) || capacity == 0) return 0;
  uint8_t query[256] = {0x49, 0x43, 0x01, 0x00, 0x00, 0x01};
  size_t used = 12;
  int start = 0;
  while (start < host.length()) {
    int dot = host.indexOf('.', start);
    if (dot < 0) dot = host.length();
    int labelLength = dot - start;
    if (labelLength < 1 || labelLength > 63 || used + labelLength + 6 > sizeof(query)) return 0;
    query[used++] = static_cast<uint8_t>(labelLength);
    memcpy(query + used, host.c_str() + start, labelLength);
    used += labelLength;
    start = dot + 1;
  }
  query[used++] = 0;
  query[used++] = 0;
  query[used++] = 1;  // A
  query[used++] = 0;
  query[used++] = 1;  // IN

  WiFiUDP udp;
  if (!udp.begin(0) || !udp.beginPacket(dns, 53)) return 0;
  udp.write(query, used);
  if (!udp.endPacket()) return 0;
  int packetLength = 0;
  unsigned long started = millis();
  while (packetLength == 0 && millis() - started < 2500) {
    packetLength = udp.parsePacket();
    if (packetLength == 0) delay(20);
  }
  if (packetLength < 12 || packetLength > 512) return 0;
  uint8_t response[512];
  int length = udp.read(response, packetLength);
  if (length < 12 || response[0] != 0x49 || response[1] != 0x43 ||
      (response[2] & 0x80) == 0 || (response[3] & 0x0f) != 0) return 0;
  uint16_t questions = (response[4] << 8) | response[5];
  uint16_t answers = (response[6] << 8) | response[7];
  size_t position = 12;
  for (uint16_t i = 0; i < questions; ++i) {
    if (!skipDnsName(response, length, position) || position + 4 > static_cast<size_t>(length)) return 0;
    position += 4;
  }
  uint8_t count = 0;
  for (uint16_t i = 0; i < answers && count < capacity; ++i) {
    if (!skipDnsName(response, length, position) || position + 10 > static_cast<size_t>(length)) break;
    uint16_t type = (response[position] << 8) | response[position + 1];
    uint16_t klass = (response[position + 2] << 8) | response[position + 3];
    uint16_t dataLength = (response[position + 8] << 8) | response[position + 9];
    position += 10;
    if (position + dataLength > static_cast<size_t>(length)) break;
    if (type == 1 && klass == 1 && dataLength == 4) {
      IPAddress ip(response[position], response[position + 1], response[position + 2], response[position + 3]);
      bool duplicate = false;
      for (uint8_t j = 0; j < count; ++j) if (addresses[j] == ip) duplicate = true;
      if (!duplicate) addresses[count++] = ip;
    }
    position += dataLength;
  }
  return count;
}
