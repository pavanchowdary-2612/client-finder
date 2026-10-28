import ipaddress
import re
import socket
from urllib.parse import urlparse


def is_public_http_url(url: str) -> bool:
    """Validate that a URL is a legitimate public HTTP/HTTPS URL, mitigating SSRF risks."""
    parsed = urlparse(url)
    host = parsed.hostname
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
        return False
    if host.lower() in {"localhost", "localhost.localdomain"}:
        return False
    try:
        addresses = (
            [ipaddress.ip_address(host)]
            if re.fullmatch(r"[0-9.]+", host)
            else [ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, None)]
        )
        return bool(addresses) and all(address.is_global for address in addresses)
    except (ValueError, socket.gaierror, OSError):
        return False
