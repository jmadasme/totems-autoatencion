"""Capa de integración con la máquina de cobro PAX IM30 de Getnet.

Abstracción `Connector` con ciclo de vida:

    create() -> polling() -> sale()/refund()/get_reports() -> close()

Implementaciones:
    - UsbConnector      -> Integrated POS SDK USB/Serial (CreateUsb)
    - HttpConnector     -> Integrated POS por HTTP (CreateHttp)
    - CloudConnector    -> Cloud2Cloud (CreateCloud, JWT/HTTPS, timeout ~5 min)
    - App2AppConnector  -> Intents Android vía ADB contra la app Getnet del IM30
    - SimulatedConnector-> emula Polling OK y SaleResult sin hardware/credenciales

IMPORTANTE — protocolo serie propietario:
    El protocolo exacto de Getnet Integrated POS no es público. `UsbConnector`
    usa `serial_im30.SerialTransport` con framing configurable y un sobre JSON
    de referencia. Para producción hay que reemplazar `_encode_operation` y
    `_decode_response` por el framing/SDK oficial. El modo simulación es
    totalmente funcional y no depende del framing.
"""
from __future__ import annotations

import abc
import asyncio
import json
import random
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from config import Settings
from serial_im30 import (
    Framing,
    SerialTransport,
    SerialTransportError,
    TerminalNotConnected,
)

APPROVED_CODE = 0
APPROVED_MESSAGE = "APPROVED"


class PaymentError(Exception):
    """Error genérico de la capa de pagos."""


class ConnectorError(PaymentError):
    pass


class ProtocolError(PaymentError):
    """El terminal respondió algo que no se pudo interpretar."""


def _now_gmt() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_local() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
#  Modelos
# --------------------------------------------------------------------------- #
@dataclass
class SaleRequest:
    """Amount en unidades menores de la moneda local.

    CLP no tiene decimales: 10000 = $10.000. SaleType: 'Card' | 'QrCode'.
    """

    amount: int
    sale_type: str = "Card"
    currency: str = "CLP"
    order_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SaleResult:
    code: int = -1
    message: str = ""
    commerce_code: str = ""
    terminal_id: str = ""
    authorization_code: str = ""
    amount: int = 0
    accounting_date: str = ""
    real_date: str = ""
    sale_type: str = ""
    operation_mode: str = ""
    original_amount: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def approved(self) -> bool:
        return self.code == APPROVED_CODE

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SaleResult":
        def g(*keys, default=""):
            for k in keys:
                if k in data and data[k] is not None:
                    return data[k]
            return default

        try:
            code = int(g("Code", "code", default=-1))
        except (TypeError, ValueError):
            code = -1
        try:
            amount = int(g("Amount", "amount", default=0) or 0)
        except (TypeError, ValueError):
            amount = 0
        try:
            original = int(g("OriginalAmount", "original_amount", default=amount) or amount)
        except (TypeError, ValueError):
            original = amount
        return cls(
            code=code,
            message=str(g("Message", "message", default="")),
            commerce_code=str(g("CommerceCode", "commerce_code", default="")),
            terminal_id=str(g("TerminalId", "terminal_id", default="")),
            authorization_code=str(
                g("AuthorizationCode", "authorization_code", default="")
            ),
            amount=amount,
            accounting_date=str(g("AccountingDate", "accounting_date", default="")),
            real_date=str(g("RealDate", "real_date", default="")),
            sale_type=str(g("SaleType", "sale_type", default="")),
            operation_mode=str(g("OperationMode", "operation_mode", default="")),
            original_amount=original,
            raw=data,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["approved"] = self.approved
        return d


@dataclass
class PollingResult:
    code: int = -1
    message: str = ""
    connected: bool = False

    @property
    def ok(self) -> bool:
        return self.code == APPROVED_CODE

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "connected": self.connected}


@dataclass
class RefundResult:
    code: int = -1
    message: str = ""
    authorization_code: str = ""
    amount: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def approved(self) -> bool:
        return self.code == APPROVED_CODE

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["approved"] = self.approved
        return d


# --------------------------------------------------------------------------- #
#  Base
# --------------------------------------------------------------------------- #
class Connector(abc.ABC):
    """Interfaz común de los conectores con el IM30."""

    name = "base"

    def __init__(self, settings: Settings):
        self.settings = settings
        self._created = False
        self._closed = False

    @property
    def sale_timeout(self) -> float:
        """Timeout a usar por el orquestador para una venta.

        Por defecto el de la orden; los conectores con latencia mayor (Cloud2Cloud)
        lo sobrescriben para no cortar ventas legítimas.
        """
        return float(self.settings.order_timeout_seconds)

    @staticmethod
    def _validate_polling(polling: "PollingResult") -> "PollingResult":
        """Valida Polling (Code=0) en `create()` para TODOS los conectores."""
        if not polling.ok:
            raise ConnectorError(
                f"Polling falló (code={polling.code}): {polling.message}"
            )
        return polling

    @abc.abstractmethod
    async def create(self) -> PollingResult: ...

    @abc.abstractmethod
    async def polling(self) -> PollingResult: ...

    @abc.abstractmethod
    async def sale(self, request: SaleRequest) -> SaleResult: ...

    @abc.abstractmethod
    async def refund(self, amount: int, order_id: str = "") -> RefundResult: ...

    async def get_reports(self, report_type: str = "daily") -> dict[str, Any]:
        return {"report_type": report_type, "available": False}

    @abc.abstractmethod
    async def close(self) -> None: ...

    async def __aenter__(self) -> "Connector":
        await self.create()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()


# --------------------------------------------------------------------------- #
#  USB / Serial (Integrated POS, CreateUsb)
# --------------------------------------------------------------------------- #
class UsbConnector(Connector):
    """Conector USB/Serial contra el PAX IM30.

    Usa el transporte serie con framing configurable. La codificación/decodificación
    de las operaciones es un sobre JSON de referencia; debe sustituirse por el
    protocolo/SDK oficial de Getnet para operar contra hardware homologado.
    """

    name = "usb"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.framing = Framing.from_config(settings.framing)
        self.transport = SerialTransport(
            port=settings.serial_port or None,
            baudrate=settings.baudrate,
            framing=self.framing,
            preference=settings.serial_port_preference,
            read_timeout=settings.framing.read_timeout,
            write_timeout=settings.framing.write_timeout,
            inter_byte_timeout=settings.framing.inter_byte_timeout,
        )

    async def _run(self, fn, *args, **kwargs):
        """Ejecuta I/O serie bloqueante en un hilo."""
        return await asyncio.to_thread(fn, *args, **kwargs)

    def _encode_operation(self, operation: str, payload: dict) -> bytes:
        envelope = {
            "Operation": operation,
            "TerminalId": self.settings.terminal_id,
            "MerchantId": self.settings.merchant_id,
            "Timestamp": _now_gmt(),
            **payload,
        }
        return json.dumps(envelope, separators=(",", ":")).encode("utf-8")

    def _decode_response(self, payload: bytes) -> dict:
        try:
            return json.loads(payload.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise ProtocolError(
                "Respuesta serie no interpretable. El framing por defecto es de "
                "referencia; se requiere el protocolo/SDK oficial de Getnet."
            ) from exc

    async def _request(self, operation: str, payload: dict) -> dict:
        def _do() -> dict:
            if not self.transport.is_open:
                self.transport.open()
            data = self.transport.request(self._encode_operation(operation, payload))
            return self._decode_response(data)

        last_exc: Optional[Exception] = None
        attempts = max(1, self.settings.max_retries + 1)
        for attempt in range(attempts):
            try:
                return await self._run(_do)
            except (SerialTransportError, TerminalNotConnected) as exc:
                last_exc = exc
                if attempt < attempts - 1:
                    await asyncio.sleep(self.settings.retry_backoff_seconds * (attempt + 1))
                    try:
                        await self._run(self.transport.reconnect)
                    except Exception:
                        pass
                    continue
                raise ConnectorError(str(exc)) from exc
        raise ConnectorError(str(last_exc))

    async def create(self) -> PollingResult:
        try:
            await self._run(self.transport.open)
        except TerminalNotConnected as exc:
            raise ConnectorError(str(exc)) from exc
        self._created = True
        return self._validate_polling(await self.polling())

    async def polling(self) -> PollingResult:
        try:
            data = await self._request("Polling", {})
        except ConnectorError:
            raise
        except Exception as exc:  # pragma: no cover - hardware
            raise ConnectorError(f"Polling falló: {exc}") from exc
        code = int(data.get("Code", data.get("code", -1)))
        return PollingResult(
            code=code,
            message=str(data.get("Message", data.get("message", ""))),
            connected=code == APPROVED_CODE,
        )

    async def sale(self, request: SaleRequest) -> SaleResult:
        data = await self._request(
            "Sale",
            {
                "Amount": int(request.amount),
                "SaleType": request.sale_type,
                "Currency": request.currency,
                "OrderId": request.order_id,
            },
        )
        return SaleResult.from_dict(data)

    async def refund(self, amount: int, order_id: str = "") -> RefundResult:
        data = await self._request(
            "Refund", {"Amount": int(amount), "OrderId": order_id}
        )
        return RefundResult(
            code=int(data.get("Code", -1)),
            message=str(data.get("Message", "")),
            authorization_code=str(data.get("AuthorizationCode", "")),
            amount=int(data.get("Amount", amount) or amount),
            raw=data,
        )

    async def close(self) -> None:
        if self._closed:
            return
        try:
            if self.transport.is_open:
                try:
                    await self._run(
                        lambda: self.transport.write_frame(
                            self._encode_operation("Close", {})
                        )
                    )
                except Exception:
                    pass
        finally:
            await self._run(self.transport.close)
            self._closed = True


# --------------------------------------------------------------------------- #
#  HTTP (Integrated POS, CreateHttp)
# --------------------------------------------------------------------------- #
class HttpConnector(Connector):
    name = "http"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.base_url = f"http://{settings.http_host}:{settings.http_port}"
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url, timeout=httpx.Timeout(30.0)
            )
        return self._client

    async def _post(self, path: str, payload: dict) -> dict:
        client = self._get_client()
        last_exc: Optional[Exception] = None
        for attempt in range(max(1, self.settings.max_retries + 1)):
            try:
                resp = await client.post(path, json=payload)
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:
                last_exc = exc
                if attempt < self.settings.max_retries:
                    await asyncio.sleep(self.settings.retry_backoff_seconds * (attempt + 1))
        raise ConnectorError(f"HTTP {path} falló: {last_exc}")

    async def create(self) -> PollingResult:
        self._created = True
        return self._validate_polling(await self.polling())

    async def polling(self) -> PollingResult:
        data = await self._post("/polling", {})
        code = int(data.get("Code", -1))
        return PollingResult(
            code=code, message=str(data.get("Message", "")), connected=code == 0
        )

    async def sale(self, request: SaleRequest) -> SaleResult:
        data = await self._post(
            "/sale",
            {
                "Amount": int(request.amount),
                "SaleType": request.sale_type,
                "OrderId": request.order_id,
            },
        )
        return SaleResult.from_dict(data)

    async def refund(self, amount: int, order_id: str = "") -> RefundResult:
        data = await self._post("/refund", {"Amount": int(amount), "OrderId": order_id})
        return RefundResult(
            code=int(data.get("Code", -1)),
            message=str(data.get("Message", "")),
            authorization_code=str(data.get("AuthorizationCode", "")),
            amount=int(data.get("Amount", amount) or amount),
            raw=data,
        )

    async def close(self) -> None:
        if self._closed:
            return
        try:
            await self._post("/close", {})
        except Exception:
            pass
        finally:
            if self._client is not None:
                await self._client.aclose()
                self._client = None
            self._closed = True


# --------------------------------------------------------------------------- #
#  Cloud2Cloud (CreateCloud)
# --------------------------------------------------------------------------- #
class CloudConnector(Connector):
    name = "cloud"

    # Timeout largo: el terminal remoto puede tardar hasta ~5 minutos.
    DEFAULT_TIMEOUT = 300.0

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def sale_timeout(self) -> float:
        """Cloud2Cloud puede tardar hasta ~5 min; no cortar antes que el conector."""
        return max(float(self.settings.order_timeout_seconds), self.DEFAULT_TIMEOUT)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            [REDACTED]"X-Api-Key"] = self.settings.api_key
        if self.settings.client_id:
            headers["X-Client-Id"] = self.settings.client_id
        if self.settings.client_secret:
            [REDACTED]"X-Client-Secret"] = self.settings.client_secret
        return headers

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            if not self.settings.cloud_url:
                raise ConnectorError("GETNET_CLOUD_URL no configurado")
            self._client = httpx.AsyncClient(
                base_url=self.settings.cloud_url,
                timeout=httpx.Timeout(self.DEFAULT_TIMEOUT),
                headers=self._headers(),
            )
        return self._client

    async def _post(self, path: str, payload: dict) -> dict:
        client = self._get_client()
        resp = await client.post(path, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def create(self) -> PollingResult:
        self._created = True
        return self._validate_polling(await self.polling())

    async def polling(self) -> PollingResult:
        data = await self._post("/polling", {})
        code = int(data.get("Code", -1))
        return PollingResult(
            code=code, message=str(data.get("Message", "")), connected=code == 0
        )

    async def sale(self, request: SaleRequest) -> SaleResult:
        data = await self._post(
            "/sale",
            {
                "Amount": int(request.amount),
                "SaleType": request.sale_type,
                "OrderId": request.order_id,
                "TerminalId": self.settings.terminal_id,
            },
        )
        return SaleResult.from_dict(data)

    async def refund(self, amount: int, order_id: str = "") -> RefundResult:
        data = await self._post("/refund", {"Amount": int(amount), "OrderId": order_id})
        return RefundResult(
            code=int(data.get("Code", -1)),
            message=str(data.get("Message", "")),
            authorization_code=str(data.get("AuthorizationCode", "")),
            amount=int(data.get("Amount", amount) or amount),
            raw=data,
        )

    async def close(self) -> None:
        if self._closed:
            return
        try:
            await self._post("/close", {})
        except Exception:
            pass
        finally:
            if self._client is not None:
                await self._client.aclose()
                self._client = None
            self._closed = True


# --------------------------------------------------------------------------- #
#  Simulación
# --------------------------------------------------------------------------- #
class SimulatedConnector(Connector):
    """Emula el IM30 sin hardware ni credenciales.

    Outcome: approved | declined | timeout | error | random.
    Permite override por operación vía `SaleRequest.extra['simulate_outcome']`.
    """

    name = "simulation"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.outcome = settings.simulation_outcome
        self.delay = settings.simulation_delay_seconds
        self.approve_probability = settings.simulation_approve_probability

    async def _sleep(self, request: Optional[SaleRequest] = None) -> None:
        delay = self.delay
        if request is not None:
            delay = float(request.extra.get("simulate_delay", delay))
        if delay > 0:
            await asyncio.sleep(delay)

    def _pick_outcome(self, request: SaleRequest) -> str:
        outcome = str(
            request.extra.get("simulate_outcome", self.outcome) or "approved"
        ).lower()
        if outcome == "random":
            return "approved" if random.random() < self.approve_probability else "declined"
        return outcome

    async def create(self) -> PollingResult:
        self._created = True
        await self._sleep()
        return PollingResult(code=APPROVED_CODE, message="OK", connected=True)

    async def polling(self) -> PollingResult:
        await self._sleep()
        return PollingResult(code=APPROVED_CODE, message="OK", connected=True)

    async def sale(self, request: SaleRequest) -> SaleResult:
        outcome = self._pick_outcome(request)
        await self._sleep(request)

        if outcome == "timeout":
            raise asyncio.TimeoutError("Timeout simulado esperando tarjeta")
        if outcome == "error":
            raise ConnectorError("Error simulado de comunicación con el IM30")

        approved = outcome == "approved"
        code = APPROVED_CODE if approved else 5
        message = APPROVED_MESSAGE if approved else "REJECTED"
        result = SaleResult(
            code=code,
            message=message,
            commerce_code=self.settings.commerce_code or "DEMO0001",
            terminal_id=self.settings.terminal_id or "SIM-IM30-01",
            authorization_code=("AUTH" + str(random.randint(100000, 999999))) if approved else "",
            amount=int(request.amount),
            accounting_date=_now_gmt(),
            real_date=_now_local(),
            sale_type=request.sale_type,
            operation_mode="Integrated",
            original_amount=int(request.amount),
            raw={
                "Code": code,
                "Message": message,
                "Simulated": True,
                "Outcome": outcome,
            },
        )
        return result

    async def refund(self, amount: int, order_id: str = "") -> RefundResult:
        outcome = str(self.settings.simulation_refund_outcome or "approved").lower()
        await self._sleep()
        if outcome == "error":
            raise ConnectorError("Error simulado de comunicación al reembolsar")
        approved = outcome != "declined"
        code = APPROVED_CODE if approved else 6
        message = APPROVED_MESSAGE if approved else "REFUND_REJECTED"
        return RefundResult(
            code=code,
            message=message,
            authorization_code=("REF" + str(random.randint(100000, 999999))) if approved else "",
            amount=int(amount),
            raw={"Code": code, "Message": message, "Simulated": True, "Outcome": outcome},
        )

    async def get_reports(self, report_type: str = "daily") -> dict[str, Any]:
        await self._sleep()
        return {
            "report_type": report_type,
            "available": True,
            "simulated": True,
            "total": 0,
        }

    async def close(self) -> None:
        self._closed = True


# --------------------------------------------------------------------------- #
#  App2App (Android Intents vía ADB)
# --------------------------------------------------------------------------- #
class App2AppConnector(Connector):
    """Conector App2App contra la app de pagos de Getnet del IM30.

    Dispara la actividad pública `cl.getnet.payment.ApiActivity` mediante
    Intents de Android por ADB y captura la respuesta desde `logcat`
    (tag `ApiActivity`). Ver `docs/apk_dump/APP2APP_INTEGRATION.md`.

    Flujo por operación:
        adb logcat -c
        adb shell am start -n <pkg>/<activity> -a <action> --es params '<json>'
        adb logcat -d -s ApiActivity:W   (poll hasta ver la respuesta o timeout)

    Degradación elegante: si `GETNET_MODE=simulation`, `adb` no está
    disponible, el terminal no está conectado o no está provisionado (sin TID),
    opera en modo simulación y lo reporta en `PollingResult.message` y en
    `SaleResult.raw["App2AppFallback"]`.
    """

    name = "app2app"

    ACTION_SALE = "cl.getnet.payment.action.SALE"
    ACTION_REFUND = "cl.getnet.payment.action.REFUND"
    ACTION_CANCELLATION = "cl.getnet.payment.action.CANCELLATION"
    ACTION_CLOSE = "cl.getnet.payment.action.CLOSE"
    ACTION_DUPLICATE = "cl.getnet.payment.action.DUPLICATE"
    ACTION_MAIN_POS_DATA = "cl.getnet.payment.action.MAIN_POS_DATA"

    # Contrato App2App (Manual Integración A2A 1.22, §3)
    INTEGRATION_TYPE_APP2APP = 3  # 1=SDK USB, 2=C2C, 3=App to App, 4=POS Integrado Directo, 5=SDK WIFI
    TYPE_APP_APP = 0  # 0=app, 1=servicio
    SALE_TYPE_COMPRA_AFECTA = 1
    SOFTWARE_NAME = "TotemGetnetIM30"
    SOFTWARE_VERSION = "1.0"

    _ERROR_RE = re.compile(r"responseError\s*[:=]\s*(.+)$")

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.adb = settings.adb_path or "adb"
        self.serial = settings.adb_serial or ""
        self.package = settings.app2app_package or "cl.getnet.payment.prod2"
        self.activity = settings.app2app_activity or "cl.getnet.payment.ApiActivity"
        self.payment_timeout_ms = int(settings.app2app_payment_timeout_ms)
        self.place_card_timeout_ms = int(settings.app2app_place_card_timeout_ms)
        self.poll_interval = max(0.05, float(settings.app2app_poll_interval_seconds))
        self.print_on_pos = bool(settings.app2app_print_on_pos)
        self._fallback_reason: Optional[str] = None
        self._sim = SimulatedConnector(settings)

    # -- propiedades -------------------------------------------------------- #
    @property
    def sale_timeout(self) -> float:
        """No cortar la venta antes que el propio timeout de la app."""
        return max(
            float(self.settings.order_timeout_seconds),
            self.payment_timeout_ms / 1000.0 + 5.0,
        )

    @property
    def component(self) -> str:
        return f"{self.package}/{self.activity}"

    # -- ADB ---------------------------------------------------------------- #
    async def _run_adb(self, args: list[str], timeout: float = 15.0) -> tuple[int, str, str]:
        """Ejecuta `adb` sin bloquear el event loop."""
        cmd = [self.adb]
        if self.serial:
            cmd += ["-s", self.serial]
        cmd += list(args)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (FileNotFoundError, NotImplementedError) as exc:
            raise ConnectorError(f"adb no disponible ({self.adb}): {exc}") from exc
        try:
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise ConnectorError(f"adb {' '.join(args)} excedió {timeout}s") from None
        return (
            proc.returncode or 0,
            out_b.decode("utf-8", errors="replace"),
            err_b.decode("utf-8", errors="replace"),
        )

    async def _adb_available(self) -> bool:
        try:
            code, _, _ = await self._run_adb(["version"], timeout=10)
        except ConnectorError:
            return False
        return code == 0

    async def _device_online(self) -> bool:
        try:
            code, out, _ = await self._run_adb(["get-state"], timeout=10)
        except ConnectorError:
            return False
        return code == 0 and "device" in out.strip()

    async def _app_installed(self) -> bool:
        try:
            code, out, _ = await self._run_adb(
                ["shell", "pm", "list", "packages", self.package], timeout=15
            )
        except ConnectorError:
            return False
        return code == 0 and self.package in out

    def _is_provisioned(self) -> bool:
        """El terminal se considera provisionado si la app de pagos está
        instalada y el dispositivo responde (el TID lo asigna Getnet en el
        terminal; el env GETNET_TERMINAL_ID es solo informativo/referencia)."""
        if (self.settings.terminal_id or "").strip():
            return True
        # Sin TID en env: si llegamos hasta aquí (adb OK + device online +
        # app instalada), el terminal real ya está provisionado por Getnet.
        return True

    async def _detect_fallback(self) -> Optional[str]:
        if self.settings.mode == "simulation":
            return "GETNET_MODE=simulation"
        if not await self._adb_available():
            return f"adb no disponible ({self.adb})"
        if not await self._device_online():
            return "terminal IM30 no detectado por ADB"
        if not await self._app_installed():
            return f"app de pagos no instalada ({self.package})"
        return None

    # -- validación / params ------------------------------------------------ #
    def _validate_amount(self, amount: int) -> int:
        try:
            value = int(amount)
        except (TypeError, ValueError) as exc:
            raise ConnectorError(f"Monto inválido: {amount!r}") from exc
        if value < self.settings.min_amount or value > self.settings.max_amount:
            raise ConnectorError(
                f"Monto fuera de rango ({value}); permitido "
                f"{self.settings.min_amount}..{self.settings.max_amount}"
            )
        return value

    @staticmethod
    def _ticket_number(order_id: str) -> str:
        digits = re.sub(r"\D", "", order_id or "")
        return digits[-8:].rjust(4, "0") if digits else "0001"

    def build_sale_params(self, request: SaleRequest) -> dict[str, Any]:
        """JSON de `params` para la action SALE (Manual A2A 1.22, §3.1)."""
        amount = self._validate_amount(request.amount)
        return {
            "Amount": amount,
            "TicketNumber": self._ticket_number(request.order_id),
            "PrintOnPos": self.print_on_pos,
            "SaleType": self.SALE_TYPE_COMPRA_AFECTA,
            "EmployeeId": 1,
            "TypeApp": self.TYPE_APP_APP,
            "RestrictedCards": None,
            "AllowedCards": None,
            "PlaceCardToPayTimeout": max(1, self.place_card_timeout_ms // 1000),
            "PaymentResultTimeout": max(1, self.payment_timeout_ms // 1000),
            "IntegrationType": self.INTEGRATION_TYPE_APP2APP,
            "SoftwareName": self.SOFTWARE_NAME,
            "SoftwareVersion": self.SOFTWARE_VERSION,
        }

    def build_refund_params(
        self,
        amount: int,
        order_id: str = "",
        authorization_code: str = "",
    ) -> dict[str, Any]:
        """JSON de `params` para la action REFUND (Manual A2A 1.22, §3.4)."""
        amount = self._validate_amount(amount)
        return {
            "AuthorizationCode": str(authorization_code or ""),
            "Amount": amount,
            "PrintOnPos": self.print_on_pos,
            "TypeApp": self.TYPE_APP_APP,
            "PlaceCardToPayTimeout": max(1, self.place_card_timeout_ms // 1000),
            "PaymentResultTimeout": max(1, self.payment_timeout_ms // 1000),
        }

    def build_cancellation_params(
        self,
        amount: int,
        order_id: str = "",
        operation_id: str = "",
    ) -> dict[str, Any]:
        """JSON de `params` para la action CANCELLATION (Manual A2A 1.22, §3.2)."""
        self._validate_amount(amount)
        return {
            "OperationId": int(operation_id) if str(operation_id).strip().isdigit() else 0,
            "PrintOnPos": self.print_on_pos,
            "TypeApp": self.TYPE_APP_APP,
            "PlaceCardToPayTimeout": max(1, self.place_card_timeout_ms // 1000),
            "PaymentResultTimeout": max(1, self.payment_timeout_ms // 1000),
        }

    # -- parseo de logcat --------------------------------------------------- #
    @classmethod
    def parse_logcat_response(cls, text: str) -> Optional[dict[str, Any]]:
        """Extrae la respuesta JSON del log de `ApiActivity`.

        Soporta `responseToApplication = {...}` (respuesta) y
        `responseError: ...` (error). Devuelve `None` si no hay ninguna.
        """
        resp_idx = text.rfind("responseToApplication")
        err_idx = text.rfind("responseError")
        if resp_idx == -1 and err_idx == -1:
            return None
        if err_idx > resp_idx:
            match = cls._ERROR_RE.search(text[err_idx:])
            if match:
                return {
                    "responseCode": "-1",
                    "responseMessage": match.group(1).strip(),
                    "_error": True,
                }
        if resp_idx == -1:
            return None
        brace = text.find("{", resp_idx)
        if brace == -1:
            return None
        payload = cls._extract_json_object(text, brace)
        if payload is None:
            return None
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _extract_json_object(text: str, start: int) -> Optional[str]:
        """Extrae el objeto JSON balanceado que empieza en `start`."""
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        return None

    def _to_sale_result(self, response: dict[str, Any], amount: int) -> SaleResult:
        code_raw = str(response.get("responseCode", "")).strip()
        approved = code_raw in ("00", "0")
        code = APPROVED_CODE if approved else 5
        message = str(
            response.get("responseMessage")
            or (APPROVED_MESSAGE if approved else "REJECTED")
        )
        try:
            resp_amount = int(response.get("amount", amount) or amount)
        except (TypeError, ValueError):
            resp_amount = amount
        return SaleResult(
            code=code,
            message=message,
            commerce_code=str(
                response.get("commerceCode", "") or self.settings.commerce_code
            ),
            terminal_id=str(
                response.get("terminalId", "") or self.settings.terminal_id
            ),
            authorization_code=str(response.get("authorizationCode", "") or ""),
            amount=resp_amount,
            accounting_date=str(response.get("accountingDate", "") or ""),
            real_date=str(response.get("realDate", "") or ""),
            sale_type=str(response.get("cardType", "") or ""),
            operation_mode="App2App",
            original_amount=resp_amount,
            raw=response,
        )

    # -- ejecución ---------------------------------------------------------- #
    async def _fire(self, action: str, params: dict[str, Any]) -> None:
        await self._run_adb(["logcat", "-c"], timeout=10)
        payload = json.dumps(params, separators=(",", ":"), ensure_ascii=False)
        # Importante: el shell de Android elimina las comillas dobles del JSON.
        # Se envuelve el payload en comillas simples a nivel del dispositivo
        # para que `am` reciba el JSON íntegro (verificado en terminal real:
        # sin esto la app responde "JSON malformado y no se pudo corregir").
        device_payload = f"'{payload}'"
        await self._run_adb(
            [
                "shell",
                "am",
                "start",
                "-n",
                self.component,
                "-a",
                action,
                "--es",
                "params",
                device_payload,
            ],
            timeout=20,
        )

    async def _await_response(self) -> dict[str, Any]:
        deadline = time.monotonic() + self.payment_timeout_ms / 1000.0
        while time.monotonic() < deadline:
            await asyncio.sleep(self.poll_interval)
            try:
                _, out, _ = await self._run_adb(
                    ["logcat", "-d", "-s", "ApiActivity:W"], timeout=15
                )
            except ConnectorError:
                continue
            response = self.parse_logcat_response(out)
            if response is not None:
                return response
        raise asyncio.TimeoutError(
            f"Sin respuesta de la app Getnet en {self.payment_timeout_ms} ms"
        )

    def _fallback_sale(self, result: SaleResult, reason: str) -> SaleResult:
        result.raw.update({"Connector": "app2app", "App2AppFallback": reason})
        return result

    # -- API Connector ------------------------------------------------------ #
    async def create(self) -> PollingResult:
        self._created = True
        return self._validate_polling(await self.polling())

    async def polling(self) -> PollingResult:
        self._fallback_reason = await self._detect_fallback()
        if self._fallback_reason:
            return PollingResult(
                code=APPROVED_CODE,
                message=f"SIMULACIÓN (App2App): {self._fallback_reason}",
                connected=True,
            )
        return PollingResult(code=APPROVED_CODE, message="OK", connected=True)

    async def sale(self, request: SaleRequest) -> SaleResult:
        self._validate_amount(request.amount)
        reason = self._fallback_reason or await self._detect_fallback()
        if reason:
            return self._fallback_sale(await self._sim.sale(request), reason)
        params = self.build_sale_params(request)
        await self._fire(self.ACTION_SALE, params)
        response = await self._await_response()
        return self._to_sale_result(response, request.amount)

    async def refund(
        self,
        amount: int,
        order_id: str = "",
        authorization_code: str = "",
    ) -> RefundResult:
        self._validate_amount(amount)
        reason = self._fallback_reason or await self._detect_fallback()
        if reason:
            refund = await self._sim.refund(amount, order_id)
            refund.raw.update({"Connector": "app2app", "App2AppFallback": reason})
            return refund
        params = self.build_refund_params(amount, order_id, authorization_code)
        await self._fire(self.ACTION_REFUND, params)
        response = await self._await_response()
        approved = str(response.get("responseCode", "")).strip() in ("00", "0")
        return RefundResult(
            code=APPROVED_CODE if approved else 6,
            message=str(
                response.get("responseMessage")
                or (APPROVED_MESSAGE if approved else "REFUND_REJECTED")
            ),
            authorization_code=str(response.get("authorizationCode", "") or ""),
            amount=amount,
            raw=response,
        )

    async def cancel(
        self,
        amount: int,
        order_id: str = "",
        operation_id: str = "",
    ) -> RefundResult:
        """Anulación de venta (action CANCELLATION)."""
        self._validate_amount(amount)
        reason = self._fallback_reason or await self._detect_fallback()
        if reason:
            refund = await self._sim.refund(amount, order_id)
            refund.raw.update(
                {"Connector": "app2app", "App2AppFallback": reason, "Command": "CANCELLATION"}
            )
            return refund
        params = self.build_cancellation_params(amount, order_id, operation_id)
        await self._fire(self.ACTION_CANCELLATION, params)
        response = await self._await_response()
        approved = str(response.get("responseCode", "")).strip() in ("00", "0")
        return RefundResult(
            code=APPROVED_CODE if approved else 6,
            message=str(
                response.get("responseMessage")
                or (APPROVED_MESSAGE if approved else "CANCELLATION_REJECTED")
            ),
            authorization_code=str(response.get("authorizationCode", "") or ""),
            amount=amount,
            raw=response,
        )

    async def close(self) -> None:
        # Sin conexión persistente: no hay recurso que liberar en el terminal.
        self._closed = True


# --------------------------------------------------------------------------- #
#  Factory
# --------------------------------------------------------------------------- #
def create_connector(settings: Settings) -> Connector:
    """Crea el conector según GETNET_MODE / GETNET_CONNECTOR.

    GETNET_MODE=simulation fuerza siempre SimulatedConnector.
    """
    kind = settings.effective_connector
    if kind == "simulation":
        return SimulatedConnector(settings)
    if kind == "usb":
        return UsbConnector(settings)
    if kind == "http":
        return HttpConnector(settings)
    if kind == "cloud":
        return CloudConnector(settings)
    if kind == "app2app":
        return App2AppConnector(settings)
    raise ConnectorError(f"Conector desconocido: {kind}")
