import socket
import unittest
from unittest.mock import patch

from scripts.safe_http import get_public_text, pinned_public_https_request, validate_public_https_url


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

    def request(self, method, target, body=None, headers=None):
        self.method = method
        self.target = target
        self.body = body
        self.headers = headers
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

    def test_authenticated_json_post_is_bounded_and_pinned(self):
        resolved = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        connections = []

        def connection_factory(*args):
            connection = FakeConnection(*args)
            connection.getresponse = lambda: type("Response", (), {
                "status": 200,
                "headers": FakeHeaders({"content-type": "application/json"}),
                "read": lambda self, size: b'{"choices":[]}',
            })()
            connections.append(connection)
            return connection

        with patch("scripts.safe_http.socket.getaddrinfo", return_value=resolved), patch(
            "scripts.safe_http._PinnedHTTPSConnection", side_effect=connection_factory
        ):
            response = pinned_public_https_request(
                "https://example.com/chat/completions",
                method="POST",
                headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
                body=b"{}",
                allowed_content_types=("application/json",),
                max_response_bytes=1024,
                authenticated=True,
            )
        self.assertEqual(response.status, 200)
        self.assertEqual(connections[0].endpoint[3], "93.184.216.34")
        self.assertEqual(connections[0].body, b"{}")

    def test_post_does_not_retry_another_resolved_address(self):
        resolved = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.35", 443)),
        ]
        with patch("scripts.safe_http.socket.getaddrinfo", return_value=resolved), patch(
            "scripts.safe_http._PinnedHTTPSConnection", side_effect=OSError("connection failed")
        ) as connection, self.assertRaises(Exception):
            pinned_public_https_request(
                "https://example.com/chat/completions", method="POST", body=b"{}",
                allowed_content_types=("application/json",),
            )
        self.assertEqual(connection.call_count, 1)

    def test_rejects_host_override_and_oversized_body(self):
        with self.assertRaisesRegex(ValueError, "Host"):
            pinned_public_https_request(
                "https://example.com", headers={"Host": "attacker.test"},
                allowed_content_types=("application/json",),
            )
        with self.assertRaisesRegex(ValueError, "16 KiB"):
            pinned_public_https_request(
                "https://example.com", method="POST", body=b"x" * (16 * 1024 + 1),
                allowed_content_types=("application/json",),
            )

    def test_authenticated_redirect_is_rejected_without_second_request(self):
        resolved = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        connection = FakeConnection("example.com", 443, resolved[0], 10)
        connection.getresponse = lambda: type("Response", (), {
            "status": 307,
            "headers": FakeHeaders({"content-type": "application/json", "location": "https://other.test/"}),
            "read": lambda self, size: b"",
        })()
        with patch("scripts.safe_http.socket.getaddrinfo", return_value=resolved), patch(
            "scripts.safe_http._PinnedHTTPSConnection", return_value=connection
        ), self.assertRaisesRegex(Exception, "cannot redirect"):
            pinned_public_https_request(
                "https://example.com", headers={"Authorization": "Bearer secret"},
                allowed_content_types=("application/json",), authenticated=True,
            )

    def test_text_redirect_drops_sensitive_headers(self):
        resolved = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        responses = [
            type("Response", (), {
                "status": 302,
                "headers": FakeHeaders({"content-type": "text/html", "location": "https://example.com/final"}),
                "read": lambda self, size: b"",
            })(),
            FakeResponse(),
        ]
        connections = []

        def connection_factory(*args):
            connection = FakeConnection(*args)
            connection.getresponse = lambda: responses.pop(0)
            connections.append(connection)
            return connection

        with patch("scripts.safe_http.socket.getaddrinfo", return_value=resolved), patch(
            "scripts.safe_http._PinnedHTTPSConnection", side_effect=connection_factory
        ):
            self.assertEqual(
                get_public_text("https://example.com/start", headers={"Authorization": "Bearer secret"}),
                "safe body",
            )
        self.assertIn("Authorization", connections[0].headers)
        self.assertNotIn("Authorization", connections[1].headers)


if __name__ == "__main__":
    unittest.main()
