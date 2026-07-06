from __future__ import annotations

import os
import socket

_ENABLED = False
_ORIGINAL_CONNECT = socket.socket.connect
_ORIGINAL_CONNECT_EX = socket.socket.connect_ex
_ORIGINAL_CREATE_CONNECTION = socket.create_connection


def _is_inet_address(address: object) -> bool:
    return isinstance(address, tuple) and len(address) >= 2


def enable_strict_offline_mode() -> None:
    """Block outbound TCP/UDP connections from this Python process.

    This is a defence-in-depth control. Operating-system firewall rules are still
    recommended for high-assurance environments.
    """
    global _ENABLED
    if _ENABLED:
        return

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

    def blocked_connect(sock: socket.socket, address: object):
        if sock.family in (socket.AF_INET, socket.AF_INET6) or _is_inet_address(address):
            raise OSError("Outbound network access is blocked by --offline-strict mode.")
        return _ORIGINAL_CONNECT(sock, address)

    def blocked_connect_ex(sock: socket.socket, address: object):
        if sock.family in (socket.AF_INET, socket.AF_INET6) or _is_inet_address(address):
            return 10013  # WSAEACCES on Windows; harmless on other platforms.
        return _ORIGINAL_CONNECT_EX(sock, address)

    def blocked_create_connection(*args, **kwargs):
        raise OSError("Outbound network access is blocked by --offline-strict mode.")

    socket.socket.connect = blocked_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = blocked_connect_ex  # type: ignore[method-assign]
    socket.create_connection = blocked_create_connection  # type: ignore[assignment]
    _ENABLED = True
