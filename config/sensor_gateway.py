"""Expose only the ESP32 ingest endpoint behind Tailscale Funnel."""

import os
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

INGEST_PATH = "/api/sensor/lecturas/"
MAX_BODY = 1024
UPSTREAM_HOST = os.getenv("SENSOR_UPSTREAM_HOST", "127.0.0.1")
UPSTREAM_PORT = int(os.getenv("SENSOR_UPSTREAM_PORT", "8001"))
LISTEN_HOST = os.getenv("SENSOR_GATEWAY_HOST", "127.0.0.1")
LISTEN_PORT = int(os.getenv("SENSOR_GATEWAY_PORT", "8002"))


class SensorGateway(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != INGEST_PATH:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self.send_error(411)
            return
        if not 0 <= length <= MAX_BODY:
            self.send_error(413)
            return
        if self.headers.get("Content-Type") != "application/json":
            self.send_error(415)
            return
        body = self.rfile.read(length)
        connection = HTTPConnection(UPSTREAM_HOST, UPSTREAM_PORT, timeout=10)
        try:
            connection.request(
                "POST", INGEST_PATH, body,
                {"Content-Type": "application/json",
                 "Authorization": self.headers.get("Authorization", ""),
                 "Host": "127.0.0.1:8001"},
            )
            upstream = connection.getresponse()
            response_body = upstream.read(MAX_BODY + 1)
            self.send_response(upstream.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)
        except OSError:
            self.send_error(502)
        finally:
            connection.close()

    def do_GET(self):
        self.send_error(404)

    def log_message(self, format_string, *args):
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), SensorGateway)
    server.daemon_threads = True
    server.serve_forever()
