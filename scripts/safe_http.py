import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urljoin, urlparse

import requests


MAX_RESPONSE_BYTES = 2 * 1024 * 1024
ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def resolve_public_https_url(url):
    if not isinstance(url, str) or any(ord(char) < 32 for char in url):
        raise ValueError("source URL contains invalid characters")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("only unauthenticated HTTPS URLs are allowed")
    try:
        port = parsed.port or 443
        addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, ValueError) as exc:
        raise ValueError(f"cannot resolve source host: {parsed.hostname}") from exc
    if not addresses:
        raise ValueError("source host resolved to no addresses")

    resolved = []
    for family, socktype, proto, _, address in addresses:
        ip = ipaddress.ip_address(address[0])
        if not ip.is_global:
            raise ValueError(f"source host resolves to a non-public address: {ip}")
        endpoint = (family, socktype, proto, str(ip))
        if endpoint not in resolved:
            resolved.append(endpoint)
    return parsed, resolved


def validate_public_https_url(url):
    resolve_public_https_url(url)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, hostname, port, endpoint, timeout):
        super().__init__(hostname, port=port, timeout=timeout, context=ssl.create_default_context())
        self._endpoint = endpoint

    def connect(self):
        family, socktype, proto, ip = self._endpoint
        sock = socket.socket(family, socktype, proto)
        sock.settimeout(self.timeout)
        try:
            address = (ip, self.port, 0, 0) if family == socket.AF_INET6 else (ip, self.port)
            sock.connect(address)
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def _open_pinned(parsed, endpoints, headers, timeout):
    request_headers = {key: value for key, value in (headers or {}).items() if key.lower() != "host"}
    request_headers["Accept-Encoding"] = "identity"
    target = parsed.path or "/"
    if parsed.query:
        target += f"?{parsed.query}"
    last_error = None
    for endpoint in endpoints:
        connection = _PinnedHTTPSConnection(parsed.hostname, parsed.port or 443, endpoint, timeout)
        try:
            connection.request("GET", target, headers=request_headers)
            return connection, connection.getresponse()
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            connection.close()
            last_error = exc
    raise requests.ConnectionError(f"unable to connect to validated source host: {last_error}")


def get_public_text(url, headers=None, timeout=20, max_redirects=3):
    current = url
    for _ in range(max_redirects + 1):
        parsed, endpoints = resolve_public_https_url(current)
        connection, response = _open_pinned(parsed, endpoints, headers, timeout)
        try:
            if response.status in REDIRECT_STATUSES:
                location = response.headers.get("location")
                if not location:
                    raise requests.RequestException("redirect response has no location")
                current = urljoin(current, location)
                continue
            if response.status >= 400:
                raise requests.HTTPError(f"source returned HTTP {response.status}")
            content_type = response.headers.get("content-type", "").lower()
            if not any(content_type.startswith(value) for value in ALLOWED_CONTENT_TYPES):
                raise requests.RequestException(f"unsupported content type: {content_type or 'missing'}")
            content_encoding = response.headers.get("content-encoding", "identity").lower()
            if content_encoding not in ("", "identity"):
                raise requests.RequestException(f"unsupported content encoding: {content_encoding}")
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise requests.RequestException("source response exceeds 2 MiB")
            encoding = response.headers.get_content_charset() or "utf-8"
            return body.decode(encoding, errors="replace")
        finally:
            connection.close()
    raise requests.TooManyRedirects(f"source exceeded {max_redirects} redirects")
