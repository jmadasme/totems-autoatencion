"""Carga de configuración del tótem.

Precedencia: variables de entorno (.env) > config.yaml > defaults.

Las credenciales Getnet NUNCA se hardcodean aquí; se leen de variables de
entorno cargadas desde `.env` (excluido de git).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.yaml"

# Carga .env sin sobreescribir variables ya presentes en el entorno real.
load_dotenv(BASE_DIR / ".env", override=False)


@dataclass
class SerialFraming:
    """Framing configurable del protocolo serie (propietario Getnet)."""

    start_delimiter: str = "STX"
    end_delimiter: str = "ETX"
    include_length: bool = True
    checksum: str = "lrc"  # none | lrc | sum | crc16
    read_timeout: float = 2.0
    write_timeout: float = 2.0
    inter_byte_timeout: float = 0.5


@dataclass
class Settings:
    mode: str = "simulation"  # simulation | sandbox | production
    connector: str = "usb"  # usb | http | cloud | app2app
    serial_port: str = ""  # vacío -> autodetección por by-id
    serial_port_preference: str = "if02"
    baudrate: int = 57600

    # --- App2App (Intents ADB contra la app de pagos de Getnet) ---
    adb_path: str = "adb"  # binario adb (o ruta absoluta)
    adb_serial: str = ""  # vacío -> adb autodetecta el único dispositivo
    app2app_package: str = "cl.getnet.payment.prod2"
    app2app_activity: str = "cl.getnet.payment.ApiActivity"
    app2app_payment_timeout_ms: int = 120000
    app2app_place_card_timeout_ms: int = 60000
    app2app_poll_interval_seconds: float = 1.5
    app2app_print_on_pos: bool = False

    terminal_id: str = ""
    merchant_id: str = ""
    commerce_code: str = ""

    http_host: str = "127.0.0.1"
    http_port: int = 8080

    cloud_url: str = ""
    api_key: str = ""
    client_id: str = ""
    client_secret: str = ""

    order_timeout_seconds: int = 120
    idle_timeout_seconds: int = 60
    max_retries: int = 2
    retry_backoff_seconds: float = 1.0

    db_path: str = "data/orders.db"
    host: str = "0.0.0.0"
    port: int = 8000
    currency: str = "CLP"
    min_amount: int = 1
    max_amount: int = 999999

    simulation_outcome: str = "approved"
    simulation_refund_outcome: str = "approved"  # approved | declined | error
    simulation_delay_seconds: float = 1.5
    simulation_approve_probability: float = 1.0

    framing: SerialFraming = field(default_factory=SerialFraming)

    @property
    def effective_connector(self) -> str:
        """En modo simulación SIEMPRE se usa el conector simulado."""
        if self.mode == "simulation":
            return "simulation"
        return self.connector

    @property
    def db_full_path(self) -> Path:
        p = Path(self.db_path)
        return p if p.is_absolute() else (BASE_DIR / p)

    def to_public_dict(self) -> dict[str, Any]:
        """Config sin secretos, para exponer a la UI/diagnóstico.

        No expone identificadores sensibles (`terminal_id`, `commerce_code`,
        `merchant_id`, `api_key`, `client_id`, `client_secret`). Solo publica
        el booleano `credentials_configured`.
        """
        return {
            "mode": self.mode,
            "connector": self.effective_connector,
            "configured_connector": self.connector,
            "serial_port": self.serial_port or None,
            "baudrate": self.baudrate,
            "adb_serial": self.adb_serial or None,
            "app2app_package": self.app2app_package,
            "currency": self.currency,
            "order_timeout_seconds": self.order_timeout_seconds,
            "idle_timeout_seconds": self.idle_timeout_seconds,
            "credentials_configured": bool(
                self.terminal_id and (self.merchant_id or self.commerce_code)
            ),
        }


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    return val


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "si", "sí"}


def _load_yaml(path: Path) -> dict[str, Any]:
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return yaml.safe_load(fh) or {}
        except Exception:
            return {}
    return {}


def load_settings(config_path: Optional[Path] = None) -> Settings:
    """Construye la configuración efectiva (env > yaml > defaults)."""
    cfg = _load_yaml(config_path or DEFAULT_CONFIG_PATH)
    app_cfg = cfg.get("app", {}) or {}
    gn = cfg.get("getnet", {}) or {}
    gn_http = gn.get("http", {}) or {}
    gn_cloud = gn.get("cloud", {}) or {}
    gn_app2app = gn.get("app2app", {}) or {}
    gn_serial = gn.get("serial", {}) or {}
    framing_cfg = gn_serial.get("framing", {}) or {}
    sim_cfg = cfg.get("simulation", {}) or {}

    framing = SerialFraming(
        start_delimiter=str(framing_cfg.get("start_delimiter", "STX")),
        end_delimiter=str(framing_cfg.get("end_delimiter", "ETX")),
        include_length=bool(framing_cfg.get("include_length", True)),
        checksum=str(framing_cfg.get("checksum", "lrc")),
        read_timeout=float(framing_cfg.get("read_timeout", 2.0)),
        write_timeout=float(framing_cfg.get("write_timeout", 2.0)),
        inter_byte_timeout=float(framing_cfg.get("inter_byte_timeout", 0.5)),
    )

    settings = Settings(
        mode=str(_env("GETNET_MODE", "simulation")),
        connector=str(_env("GETNET_CONNECTOR", gn.get("connector", "usb"))),
        serial_port=str(_env("GETNET_SERIAL_PORT", gn.get("serial_port", "") or "")),
        serial_port_preference=str(
            _env("GETNET_SERIAL_PREFERENCE", gn.get("serial_port_preference", "if02"))
        ),
        baudrate=_env_int("GETNET_BAUDRATE", int(gn.get("baudrate", 57600))),
        terminal_id=str(_env("GETNET_TERMINAL_ID", "") or ""),
        merchant_id=str(_env("GETNET_MERCHANT_ID", "") or ""),
        commerce_code=str(_env("GETNET_COMMERCE_CODE", "") or ""),
        http_host=str(_env("GETNET_HTTP_HOST", gn_http.get("host", "127.0.0.1"))),
        http_port=_env_int("GETNET_HTTP_PORT", int(gn_http.get("port", 8080))),
        cloud_url=str(_env("GETNET_CLOUD_URL", gn_cloud.get("url", "") or "")),
        api_key=[REDACTED]"GETNET_API_KEY", "") or ""),
        client_id=str(_env("GETNET_CLIENT_ID", "") or ""),
        client_secret=[REDACTED]"GETNET_CLIENT_SECRET", "") or ""),
        adb_path=str(_env("GETNET_ADB_PATH", gn_app2app.get("adb_path", "adb"))),
        adb_serial=str(_env("GETNET_ADB_SERIAL", "") or ""),
        app2app_package=str(
            _env(
                "GETNET_APP2APP_PACKAGE",
                gn_app2app.get("package", "cl.getnet.payment.prod2"),
            )
        ),
        app2app_activity=str(
            _env(
                "GETNET_APP2APP_ACTIVITY",
                gn_app2app.get("activity", "cl.getnet.payment.ApiActivity"),
            )
        ),
        app2app_payment_timeout_ms=_env_int(
            "GETNET_APP2APP_PAYMENT_TIMEOUT_MS",
            int(gn_app2app.get("payment_timeout_ms", 120000)),
        ),
        app2app_place_card_timeout_ms=_env_int(
            "GETNET_APP2APP_PLACE_CARD_TIMEOUT_MS",
            int(gn_app2app.get("place_card_timeout_ms", 60000)),
        ),
        app2app_poll_interval_seconds=_env_float(
            "GETNET_APP2APP_POLL_INTERVAL",
            float(gn_app2app.get("poll_interval_seconds", 1.5)),
        ),
        app2app_print_on_pos=_env_bool(
            "GETNET_APP2APP_PRINT_ON_POS",
            bool(gn_app2app.get("print_on_pos", False)),
        ),
        order_timeout_seconds=_env_int(
            "ORDER_TIMEOUT_SECONDS", int(app_cfg.get("order_timeout_seconds", 120))
        ),
        idle_timeout_seconds=_env_int(
            "IDLE_TIMEOUT_SECONDS", int(app_cfg.get("idle_timeout_seconds", 60))
        ),
        max_retries=_env_int("GETNET_MAX_RETRIES", int(gn.get("max_retries", 2))),
        retry_backoff_seconds=_env_float(
            "GETNET_RETRY_BACKOFF", float(gn.get("retry_backoff_seconds", 1.0))
        ),
        db_path=str(_env("DB_PATH", "data/orders.db")),
        host=str(_env("APP_HOST", app_cfg.get("host", "0.0.0.0"))),
        port=_env_int("APP_PORT", int(app_cfg.get("port", 8000))),
        currency=str(_env("CURRENCY", app_cfg.get("currency", "CLP"))),
        min_amount=_env_int("MIN_AMOUNT", int(app_cfg.get("min_amount", 1))),
        max_amount=_env_int("MAX_AMOUNT", int(app_cfg.get("max_amount", 999999))),
        simulation_outcome=str(
            _env("GETNET_SIM_OUTCOME", sim_cfg.get("outcome", "approved"))
        ),
        simulation_refund_outcome=str(
            _env("GETNET_SIM_REFUND_OUTCOME", sim_cfg.get("refund_outcome", "approved"))
        ),
        simulation_delay_seconds=_env_float(
            "GETNET_SIM_DELAY", float(sim_cfg.get("delay_seconds", 1.5))
        ),
        simulation_approve_probability=_env_float(
            "GETNET_SIM_APPROVE_PROB",
            float(sim_cfg.get("approve_probability", 1.0)),
        ),
        framing=framing,
    )
    return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def override_settings(base: Settings, **kwargs: Any) -> Settings:
    """Devuelve una copia modificada (útil para tests)."""
    return replace(base, **kwargs)
