"""Thin synchronous wrapper around pycomm3. Always call from an executor thread."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

from .const import PLC_LOGIX, PLC_SLC

_LOGGER = logging.getLogger(__name__)


class PLCError(Exception):
    """Communication failure (connection-level)."""


class PLCWriteError(PLCError):
    """A write was rejected by the PLC."""


@dataclass
class TagValue:
    """Result of reading one tag."""

    value: Any
    error: str | None = None


def list_identity(path: str, timeout: float = 3.0) -> dict[str, Any]:
    """Send an EtherNet/IP ListIdentity (encapsulation 0x63) over TCP 44818 and parse the reply."""
    import socket
    import struct

    host = path.split("/", 1)[0]
    port = 44818
    if ":" in host:
        host, port_s = host.rsplit(":", 1)
        port = int(port_s)
    request = struct.pack("<HHII8sI", 0x0063, 0, 0, 0, b"\x00" * 8, 0)
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall(request)
        header = b""
        while len(header) < 24:
            chunk = sock.recv(24 - len(header))
            if not chunk:
                raise PLCError("connection closed during ListIdentity")
            header += chunk
        command, length, _session, status = struct.unpack_from("<HHII", header)
        if command != 0x0063 or status != 0:
            raise PLCError(f"ListIdentity rejected (command {command:#x}, status {status})")
        body = b""
        while len(body) < length:
            chunk = sock.recv(length - len(body))
            if not chunk:
                raise PLCError("truncated ListIdentity reply")
            body += chunk

    count = struct.unpack_from("<H", body, 0)[0]
    offset = 2
    for _ in range(count):
        item_type, item_len = struct.unpack_from("<HH", body, offset)
        offset += 4
        item = body[offset : offset + item_len]
        offset += item_len
        if item_type != 0x000C:
            continue
        # encap version(2) + sockaddr(16), then the CIP identity
        vendor, dev_type, prod_code, rev_major, rev_minor, _status, serial = struct.unpack_from(
            "<HHHBBHI", item, 18
        )
        name_len = item[32]
        name = item[33 : 33 + name_len].decode("ascii", errors="replace").strip()
        return {
            "vendor_id": vendor,
            "product_type": dev_type,
            "product_code": prod_code,
            "revision": f"{rev_major}.{rev_minor:02d}",
            "serial": f"{serial:08x}",
            "product_name": name,
        }
    raise PLCError("ListIdentity reply had no identity item")


class PLCClient:
    """One connection to one PLC, guarded by a lock."""

    def __init__(self, plc_type: str, path: str) -> None:
        if plc_type not in (PLC_LOGIX, PLC_SLC):
            raise ValueError(f"unknown PLC type {plc_type}")
        self.plc_type = plc_type
        self.path = path
        self.info: dict[str, Any] = {}
        self._driver: Any = None
        self._lock = threading.Lock()

    # --- connection -------------------------------------------------------
    def _make_driver(self) -> Any:
        if self.plc_type == PLC_LOGIX:
            from pycomm3 import LogixDriver

            return LogixDriver(self.path, init_tags=True, init_program_tags=True)
        from pycomm3 import SLCDriver

        return SLCDriver(self.path)

    def _ensure_connected(self) -> Any:
        if self._driver is not None and getattr(self._driver, "connected", False):
            return self._driver
        self._close_unlocked()
        try:
            driver = self._make_driver()
            if not driver.open():
                raise PLCError(f"could not open connection to {self.path}")
        except PLCError:
            raise
        except Exception as err:  # pycomm3 raises CommError and friends
            raise PLCError(f"connect to {self.path} failed: {err}") from err
        self._driver = driver
        self.info = self._identify(driver)
        _LOGGER.debug("Connected to %s: %s", self.path, self.info)
        return driver

    @staticmethod
    def _clean_identity(raw: Any) -> dict[str, Any]:
        """Keep simple values; flatten a {'major','minor'} revision into '5.11'."""
        out: dict[str, Any] = {}
        if not raw:
            return out
        for key, val in dict(raw).items():
            if key == "revision" and isinstance(val, dict) and "major" in val:
                out[key] = f"{val['major']}.{val.get('minor', 0)}"
            elif key == "serial" and isinstance(val, int):
                out[key] = f"{val:08x}"
            elif isinstance(val, (str, int, float)) and not isinstance(val, bool):
                out[key] = val.strip() if isinstance(val, str) else val
        return out

    def _identify(self, driver: Any) -> dict[str, Any]:
        info: dict[str, Any] = {}
        try:
            info.update(self._clean_identity(getattr(driver, "info", None)))
        except Exception:  # noqa: BLE001 - identity is best effort
            pass
        if self.plc_type == PLC_SLC and not info.get("product_name"):
            # SLC 5/05 / MicroLogix don't support the connected messaging pycomm3 uses for
            # module info, but every EtherNet/IP device answers ListIdentity.
            try:
                info.update(list_identity(self.path))
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("%s identity via ListIdentity failed: %s", self.path, err)
        return info

    def _close_unlocked(self) -> None:
        if self._driver is not None:
            try:
                self._driver.close()
            except Exception:  # noqa: BLE001
                pass
        self._driver = None

    def connect(self) -> dict[str, Any]:
        """Open (or reuse) the connection and return PLC identity info."""
        with self._lock:
            self._ensure_connected()
            return dict(self.info)

    def close(self) -> None:
        with self._lock:
            self._close_unlocked()

    # --- data -------------------------------------------------------------
    def read(self, tags: list[str]) -> dict[str, TagValue]:
        """Read all tags in one request. Per-tag errors are returned, not raised."""
        with self._lock:
            driver = self._ensure_connected()
            if not tags:
                return {}
            try:
                result = driver.read(*tags)
            except Exception as err:
                self._close_unlocked()
                raise PLCError(f"read failed: {err}") from err
            if not isinstance(result, list):
                result = [result]
            out: dict[str, TagValue] = {}
            for name, tag in zip(tags, result):
                if tag is None:
                    out[name] = TagValue(None, "no response")
                elif tag.error:
                    out[name] = TagValue(None, str(tag.error))
                else:
                    out[name] = TagValue(tag.value)
            # A total failure on every tag usually means the connection is dead.
            if out and all(v.error for v in out.values()) and not getattr(driver, "connected", True):
                self._close_unlocked()
                raise PLCError(f"all reads failed, first error: {next(iter(out.values())).error}")
            return out

    def write(self, tag: str, value: Any) -> None:
        """Write one tag. Raises PLCWriteError if the PLC rejects it."""
        with self._lock:
            driver = self._ensure_connected()
            try:
                result = driver.write((tag, value))
            except Exception as err:
                self._close_unlocked()
                raise PLCError(f"write {tag} failed: {err}") from err
            if isinstance(result, list):
                result = result[0] if result else None
            if result is None:
                raise PLCWriteError(f"write {tag}: no response")
            if result.error:
                raise PLCWriteError(f"write {tag}={value!r} rejected: {result.error}")
            _LOGGER.info("Wrote %s = %r to %s", tag, value, self.path)
