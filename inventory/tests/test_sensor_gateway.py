from email.message import Message
from io import BytesIO
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from config.sensor_gateway import SensorGateway


class SensorGatewayProxyTests(SimpleTestCase):
    def post_through_gateway(self, forwarded_proto):
        handler = SensorGateway.__new__(SensorGateway)
        handler.path = "/api/v1/dispositivos/me/ciclos"
        handler.headers = Message()
        handler.headers["Content-Length"] = "2"
        handler.headers["Content-Type"] = "application/json"
        handler.headers["Host"] = "icchocolate.lat"
        handler.headers["Authorization"] = "Bearer test-token"
        if forwarded_proto:
            handler.headers["X-Forwarded-Proto"] = forwarded_proto
        handler.rfile = BytesIO(b"{}")
        handler.wfile = BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()

        upstream = Mock()
        upstream.getresponse.return_value.status = 201
        upstream.getresponse.return_value.read.return_value = b"{}"
        with patch("config.sensor_gateway.HTTPConnection", return_value=upstream):
            handler.do_POST()
        handler.send_response.assert_called_once_with(201)
        return upstream.request.call_args.args[3]

    def test_https_origin_is_forwarded_to_django(self):
        headers = self.post_through_gateway("https")
        self.assertEqual(headers["X-Forwarded-Proto"], "https")
        self.assertEqual(headers["Host"], "icchocolate.lat")
        self.assertEqual(headers["Authorization"], "Bearer test-token")

    def test_plain_http_is_not_marked_as_https(self):
        headers = self.post_through_gateway("http")
        self.assertNotIn("X-Forwarded-Proto", headers)
