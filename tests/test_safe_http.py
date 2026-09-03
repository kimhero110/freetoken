import socket
import unittest
from unittest.mock import patch

from scripts.safe_http import get_public_text, validate_public_https_url


class FakeHeaders(dict):
    def get_content_charset(self):
        return "utf-8"


class FakeResponse:
    status = 200
    headers = FakeHeaders({"content-type": "text/html"})

    def read(self, _size):
        return b"safe body"


class FakeConnection:
    def __init__(self, hostname, port, endpoint, timeout):
        self.hostname = hostname
        self.endpoint = endpoint

    def request(self, method, target, headers):
        return None

    def getresponse(self):
        return FakeResponse()

    def close(self):
        return None


class SafeHttpTests(unittest.TestCase):
    def test_rejects_non_https_and_authenticated_urls(self):
        for url in ("http://example.com", "https://user:pass@example.com"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_public_https_url(url)

    def test_rejects_private_and_loopback_destinations(self):
        for address in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"):
            family = socket.AF_INET6 if ":" in address else socket.AF_INET
            resolved = [(family, socket.SOCK_STREAM, 6, "", (address, 443))]
            with self.subTest(address=address), patch(
                "scripts.safe_http.socket.getaddrinfo", return_value=resolved
            ), self.assertRaises(ValueError):
                validate_public_https_url("https://example.com/source")

    def test_accepts_a_public_https_destination(self):
        resolved = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        with patch("scripts.safe_http.socket.getaddrinfo", return_value=resolved):
            validate_public_https_url("https://example.com/source")

    def test_request_connects_to_the_validated_ip(self):
        resolved = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        connections = []

        def connection_factory(*args):
            connection = FakeConnection(*args)
            connections.append(connection)
            return connection

        with patch("scripts.safe_http.socket.getaddrinfo", return_value=resolved), patch(
            "scripts.safe_http._PinnedHTTPSConnection", side_effect=connection_factory
        ):
            self.assertEqual(get_public_text("https://example.com/source"), "safe body")
        self.assertEqual(connections[0].hostname, "example.com")
        self.assertEqual(connections[0].endpoint[3], "93.184.216.34")


if __name__ == "__main__":
    unittest.main()
