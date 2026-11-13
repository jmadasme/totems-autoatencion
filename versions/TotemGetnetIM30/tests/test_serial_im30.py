"""Pruebas del transporte serie y detección real del PAX IM30."""
from __future__ import annotations

import pytest

from serial_im30 import (
    Framing,
    checksum_sum,
    compute_checksum,
    crc16_modbus,
    describe_ports,
    detect_im30_port,
    find_im30_ports,
    lrc,
)


def test_lrc_checksum():
    assert lrc(b"\x01\x02\x03") == (0x01 ^ 0x02 ^ 0x03)
    assert lrc(b"") == 0


def test_sum_and_crc():
    assert checksum_sum(b"\x01\x02") == 3
    assert isinstance(crc16_modbus(b"123456789"), int)
    assert compute_checksum(b"abc", "none") == b""
    assert len(compute_checksum(b"abc", "lrc")) == 1
    assert len(compute_checksum(b"abc", "crc16")) == 2


def test_framing_roundtrip():
    framing = Framing(start_delimiter="STX", end_delimiter="ETX", include_length=True, checksum="lrc")
    payload = b'{"Operation":"Polling"}'
    frame = framing.encode(payload)
    assert frame[0] == 0x02
    assert frame[-1] == 0x03
    assert framing.decode(frame) == payload


def test_framing_roundtrip_no_delimiters():
    framing = Framing(start_delimiter="", end_delimiter="", include_length=False, checksum="sum")
    payload = b"HELLO"
    frame = framing.encode(payload)
    assert framing.decode(frame) == payload


def test_framing_bad_checksum():
    from serial_im30 import SerialTransportError

    framing = Framing(start_delimiter="STX", end_delimiter="ETX", include_length=True, checksum="lrc")
    frame = bytearray(framing.encode(b"DATA"))
    frame[-2] ^= 0xFF  # corromper checksum
    with pytest.raises(SerialTransportError):
        framing.decode(bytes(frame))


def test_expected_total_length_no_end_delimiter():
    """I-05: terminación por longitud real del checksum y offset por start_byte."""
    expected_extra = {"none": 0, "lrc": 1, "sum": 1, "crc16": 2}
    payload = b"HELLO"
    for checksum, extra in expected_extra.items():
        framing = Framing(
            start_delimiter="STX", end_delimiter="", include_length=True, checksum=checksum
        )
        frame = framing.encode(payload)
        # STX + len(2) + payload + checksum real
        assert len(frame) == 1 + 2 + len(payload) + extra
        assert framing.expected_total_length(frame) == len(frame)
        # aún sin bytes suficientes para la longitud
        assert framing.expected_total_length(frame[:2]) is None
        assert framing.decode(frame) == payload


def test_expected_total_length_without_start_delimiter():
    """I-05: sin delimitador de inicio el campo de longitud está en buf[0:2]."""
    framing = Framing(start_delimiter="", end_delimiter="", include_length=True, checksum="crc16")
    frame = framing.encode(b"ABC")
    assert framing.expected_total_length(frame) == len(frame)
    assert framing.expected_total_length(frame[:1]) is None
    assert framing.decode(frame) == b"ABC"


@pytest.mark.hardware
def test_detect_im30_real():
    """Detección del IM30 real por USB (se omite si no hay hardware)."""
    ports = find_im30_ports()
    if not ports:
        pytest.skip("No hay PAX IM30 conectado por USB")
    assert all(p.device.startswith("/dev/") for p in ports)
    interfaces = {p.interface for p in ports}
    assert interfaces & {"if00", "if02", "if04"}
    best = detect_im30_port("if02")
    assert best is not None
    assert best.interface in {"if02", "if04", "if00"}
    info = describe_ports()
    assert info["detected"] is True
    assert info["count"] == len(ports)
