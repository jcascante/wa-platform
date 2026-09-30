"""Blocks a tenant webhook_url from pointing at internal infrastructure (SSRF). The only check
that existed before this (schemas/tenant.py's https requirement) doesn't stop a URL like
https://10.42.0.5:5432/ from reaching the platform's own VPC — and the worker sends the tenant's
own reply back over WhatsApp, so a successful hit would leak whatever that internal response
contains."""

import ipaddress
import socket


class UnsafeWebhookHost(ValueError):
    pass


def _is_public_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def assert_public_host(hostname: str) -> None:
    """Resolves `hostname` and raises if any resolved address is non-public. Called both when a
    tenant sets their webhook (schemas/tenant.py, catches the obvious case up front) and again
    immediately before every forward (workers/message_processor.py) — DNS can point somewhere
    different by the time we actually connect (rebinding), so the check at send time is the one
    that actually matters for defense."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise UnsafeWebhookHost(f"could not resolve webhook host: {hostname}") from exc
    for *_rest, sockaddr in infos:
        ip = str(sockaddr[0])
        if not _is_public_ip(ip):
            raise UnsafeWebhookHost(f"webhook host resolves to a non-public address: {ip}")
