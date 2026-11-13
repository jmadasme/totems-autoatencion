"""Detección y manejo del PAX IM30 de Getnet por USB/Serial.

El IM30 se expone como 3 interfaces CDC-ACM:
    /dev/serial/by-id/usb-PAX_IM30_1640353821-if00 -> ttyACM0 (AT / posible ModemManager)
    /dev/serial/by-id/usb-PAX_IM30_1640353821-if02 -> ttyACM1 (57600 8N1)
    /dev/serial/by-id/usb-PAX_IM30_1640353821-if04 -> ttyACM2 (57600 8N1)

El protocolo serie exacto de Getnet Integrated POS es propietario/no público.
Por eso esta capa implementa un **framing configurable** (delimitadores, largo y
checksum) para dejar preparado el adaptador al protocolo/SDK oficial. El modo
simulación (`GETNET_MODE=simulation`) NO depende de este framing.
"""
from __future__ import annotations

import glob
import os
import struct
import time
from dataclasses import dataclass
from typing import Optional

try:  # pragma: no cover - dependencia dura en runtime
    import serial
    from serial.tools import list_ports
except Exception:  # pragma: no cover
    serial = None  # type: ignore
    list_ports = None  # type: ignore

from config import SerialFraming

PAX_VID = 0x2FB8
PAX_PID = 0x225E
PRODUCT_HINT = "IM30"
SERIAL_BY_ID_GLOB = "/dev/serial/by-id/*"

# Interfaz preferida -> sufijo by-id. if02 = ttyACM1 (data), if04 = ttyACM2.
DEFAULT_INTERFACE = "if02"


class SerialTransportError(Exception):
    """Error genérico de transporte serie."""


class PortBusyError(SerialTransportError):
    """El puerto está ocupado (p. ej. por ModemManager)."""


class TerminalNotConnected(SerialTransportError):
    """No se detectó ningún IM30 conectado."""


# --------------------------------------------------------------------------- #
#  Framing configurable
# --------------------------------------------------------------------------- #
_DELIM_MAP = {
    "": None,
    "none": None,
    "STX": 0x02,
    "ETX": 0x03,
    "EOT": 0x04,
    "ENQ": 0x05,
    "ACK": 0x06,
    "NAK": 0x15,
}


def _resolve_delimiter(value: str) -> Optional[int]:
    if value is None:
        return None
    v = str(value).strip()
    if v == "":
        return None
    upper = v.upper()
    if upper in _DELIM_MAP:
        return _DELIM_MAP[upper]
    if v.lower().startswith("0x"):
        return int(v, 16) & 0xFF
    if v.isdigit():
        return int(v) & 0xFF
    # carácter único
    if len(v) == 1:
        return ord(v)
    return None


def lrc(data: bytes) -> int:
    """Longitudinal Redundancy Check (XOR)."""
    checksum = 0
    for b in data:
        checksum ^= b
    return checksum & 0xFF


def checksum_sum(data: bytes) -> int:
    return sum(data) & 0xFF


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def compute_checksum(data: bytes, kind: str) -> bytes:
    kind = (kind or "none").lower()
    if kind == "none":
        return b""
    if kind == "lrc":
        return bytes([lrc(data)])
    if kind == "sum":
        return bytes([checksum_sum(data)])
    if kind == "crc16":
        return struct.pack("<H", crc16_modbus(data))
    raise ValueError(f"Checksum desconocido: {kind}")


@dataclass
class Framing:
    """Construye/parsea tramas según configuración (protocolo propietario)."""

    start_delimiter: str = "STX"
    end_delimiter: str = "ETX"
    include_length: bool = True
    checksum: str = "lrc"

    @classmethod
    def from_config(cls, cfg: SerialFraming) -> "Framing":
        return cls(
            start_delimiter=cfg.start_delimiter,
            end_delimiter=cfg.end_delimiter,
            include_length=cfg.include_length,
            checksum=cfg.checksum,
        )

    @property
    def start_byte(self) -> Optional[int]:
        return _resolve_delimiter(self.start_delimiter)

    @property
    def end_byte(self) -> Optional[int]:
        return _resolve_delimiter(self.end_delimiter)

    def encode(self, payload: bytes) -> bytes:
        body = bytearray()
        if self.include_length:
            body += struct.pack(">H", len(payload) & 0xFFFF)
        body += payload
        body += compute_checksum(bytes(body), self.checksum)
        frame = bytearray()
        if self.start_byte is not None:
            frame.append(self.start_byte)
        frame += body
        if self.end_byte is not None:
            frame.append(self.end_byte)
        return bytes(frame)

    def decode(self, frame: bytes) -> bytes:
        """Extrae el payload validando delimitadores, largo y checksum.

        El checksum cubre el "body" completo (largo + payload), igual que en
        `encode`, para que ambos extremos sean consistentes.
        """
        data = bytes(frame)
        if self.start_byte is not None and data[:1] == bytes([self.start_byte]):
            data = data[1:]
        if self.end_byte is not None and data[-1:] == bytes([self.end_byte]):
            data = data[:-1]

        csum_len = len(compute_checksum(b"", self.checksum))
        if csum_len:
            if len(data) < csum_len:
                raise SerialTransportError("Trama demasiado corta (checksum)")
            body, tail = data[:-csum_len], data[-csum_len:]
            if tail != compute_checksum(body, self.checksum):
                raise SerialTransportError("Checksum inválido")
        else:
            body = data

        if self.include_length:
            if len(body) < 2:
                raise SerialTransportError("Trama demasiado corta (largo)")
            (length,) = struct.unpack(">H", body[:2])
            payload = body[2:]
            if len(payload) < length:
                raise SerialTransportError("Trama incompleta")
            payload = payload[:length]
        else:
            payload = body
        return payload

    def expected_total_length(self, buf: bytes) -> Optional[int]:
        """Longitud total esperada de la trama a partir del buffer parcial.

        Solo aplica cuando NO hay delimitador de fin y `include_length` está
        activo (es el único modo en que hace falta calcular la terminación).
        Ubica el campo de longitud tras el delimitador de inicio (si existe) y
        suma la longitud REAL del checksum (0/1/2 bytes según `checksum`).

        Devuelve None si aún no hay bytes suficientes para leer la longitud.
        """
        if self.end_byte is not None or not self.include_length:
            return None
        offset = 1 if self.start_byte is not None else 0
        if len(buf) < offset + 2:
            return None
        (length,) = struct.unpack(">H", bytes(buf[offset : offset + 2]))
        csum_len = len(compute_checksum(b"", self.checksum))
        return offset + 2 + length + csum_len


# --------------------------------------------------------------------------- #
#  Detección de puertos
# --------------------------------------------------------------------------- #
@dataclass
class Im30Port:
    by_id: str
    device: str
    interface: str
    description: str = ""
    hwid: str = ""
    is_im30: bool = True

    def to_dict(self) -> dict:
        return {
            "by_id": self.by_id,
            "device": self.device,
            "interface": self.interface,
            "description": self.description,
            "hwid": self.hwid,
            "is_im30": self.is_im30,
            "exists": os.path.exists(self.device),
            "accessible": os.access(self.device, os.R_OK | os.W_OK),
        }


def _interface_from_by_id(path: str) -> str:
    name = os.path.basename(path)
    if "-if" in name:
        return "if" + name.rsplit("-if", 1)[1]
    return ""


def find_im30_ports() -> list[Im30Port]:
    """Busca el IM30 por by-id (fuente principal) y por VID/PID (fallback)."""
    found: dict[str, Im30Port] = {}

    for link in sorted(glob.glob(SERIAL_BY_ID_GLOB)):
        name = os.path.basename(link)
        if PRODUCT_HINT not in name and "PAX" not in name.upper():
            continue
        try:
            device = os.path.realpath(link)
        except OSError:
            device = ""
        found[device] = Im30Port(
            by_id=link,
            device=device,
            interface=_interface_from_by_id(link),
            description="PAX IM30 (by-id)",
        )

    # Fallback: enumeración por VID/PID cuando no hay by-id.
    if list_ports is not None:
        for p in list_ports.comports():
            is_pax = getattr(p, "vid", None) == PAX_VID and getattr(p, "pid", None) == PAX_PID
            if not is_pax:
                continue
            if p.device in found:
                continue
            found[p.device] = Im30Port(
                by_id="",
                device=p.device,
                interface="",
                description=p.description or "PAX IM30",
                hwid=p.hwid or "",
            )

    return list(found.values())


def detect_im30_port(preference: str = DEFAULT_INTERFACE) -> Optional[Im30Port]:
    """Devuelve el mejor puerto del IM30.

    Prioriza la interfaz `preference` (if02 por defecto). Si no aparece, usa
    la primera interfaz no-if00 (evitando ACM0 ocupado por ModemManager).
    """
    ports = find_im30_ports()
    if not ports:
        return None
    for p in ports:
        if p.interface == preference:
            return p
    for p in ports:
        if p.interface and p.interface != "if00":
            return p
    return ports[0]


def describe_ports() -> dict:
    """Diagnóstico de puertos IM30 para /api/terminal/status."""
    ports = find_im30_ports()
    return {
        "detected": bool(ports),
        "count": len(ports),
        "ports": [p.to_dict() for p in ports],
    }


# --------------------------------------------------------------------------- #
#  Transporte serie
# --------------------------------------------------------------------------- #
class SerialTransport:
    """Transporte serie con apertura, framing, timeouts y reconexión."""

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 57600,
        framing: Optional[Framing] = None,
        preference: str = DEFAULT_INTERFACE,
        read_timeout: float = 2.0,
        write_timeout: float = 2.0,
        inter_byte_timeout: float = 0.5,
    ):
        self.port = port
        self.baudrate = baudrate
        self.framing = framing or Framing()
        self.preference = preference
        self.read_timeout = read_timeout
        self.write_timeout = write_timeout
        self.inter_byte_timeout = inter_byte_timeout
        self._serial = None  # type: ignore

    # -- lifecycle ---------------------------------------------------------
    def resolve_port(self) -> str:
        if self.port:
            return self.port
        detected = detect_im30_port(self.preference)
        if detected is None:
            raise TerminalNotConnected(
                "No se detectó el PAX IM30. Verifique el cable USB y los permisos "
                "sobre /dev/ttyACM*."
            )
        self.port = detected.device
        return self.port

    def open(self):
        if serial is None:  # pragma: no cover
            raise SerialTransportError("pyserial no está instalado")
        port = self.resolve_port()
        try:
            self._serial = serial.Serial(
                port=port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.read_timeout,
                write_timeout=self.write_timeout,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
            self._serial.inter_byte_timeout = self.inter_byte_timeout
        except serial.SerialException as exc:  # type: ignore[attr-defined]
            msg = str(exc)
            if "busy" in msg.lower() or "resource" in msg.lower():
                raise PortBusyError(
                    f"Puerto {port} ocupado ({msg}). Deshabilite ModemManager para "
                    "/dev/ttyACM* (regla udev) o use otra interfaz."
                ) from exc
            raise SerialTransportError(f"No se pudo abrir {port}: {msg}") from exc
        return self._serial

    @property
    def is_open(self) -> bool:
        return bool(self._serial is not None and getattr(self._serial, "is_open", False))

    def close(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

    def reconnect(self) -> None:
        self.close()
        time.sleep(0.2)
        self.open()

    # -- I/O ---------------------------------------------------------------
    def write_frame(self, payload: bytes) -> None:
        if not self.is_open:
            self.open()
        frame = self.framing.encode(payload)
        try:
            self._serial.write(frame)  # type: ignore[union-attr]
            self._serial.flush()  # type: ignore[union-attr]
        except Exception as exc:  # pragma: no cover - hardware
            raise SerialTransportError(f"Error de escritura serie: {exc}") from exc

    def read_frame(self, timeout: Optional[float] = None) -> bytes:
        if not self.is_open:
            self.open()
        end = self.framing.end_byte
        start = self.framing.start_byte
        deadline = time.monotonic() + (timeout if timeout is not None else self.read_timeout)
        buf = bytearray()
        started = False
        try:
            while time.monotonic() < deadline:
                chunk = self._serial.read(1)  # type: ignore[union-attr]
                if not chunk:
                    if started and not self.framing.include_length and end is None:
                        break
                    continue
                b = chunk[0]
                if not started and start is not None:
                    if b != start:
                        continue
                    started = True
                    buf.append(b)
                    continue
                started = True
                buf.append(b)
                if end is not None and b == end:
                    break
                if end is None and self.framing.include_length:
                    total = self.framing.expected_total_length(bytes(buf))
                    if total is not None and len(buf) >= total:
                        break
        except Exception as exc:  # pragma: no cover - hardware
            raise SerialTransportError(f"Error de lectura serie: {exc}") from exc
        if not buf:
            raise SerialTransportError("Timeout esperando respuesta del IM30")
        return bytes(buf)

    def request(self, payload: bytes, timeout: Optional[float] = None) -> bytes:
        """Envía una trama y espera la respuesta, decodificada a payload."""
        self.write_frame(payload)
        frame = self.read_frame(timeout=timeout)
        return self.framing.decode(frame)
