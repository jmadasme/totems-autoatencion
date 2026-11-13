"""Tótem de autoatención con cobro en el PAX IM30 de Getnet.

App principal FastAPI: sirve la UI táctil (`ui/`), expone la API de órdenes,
orquesta el ciclo de vida del conector de pagos y emite el comprobante digital.

Ejecutar:
    .venv/bin/python app.py
    # o
    .venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import catalog
import receipt as receipt_mod
from config import BASE_DIR, Settings, get_settings
from orders import (
    CANCELLED,
    CHARGING,
    EMITTED,
    ERROR,
    FAILED,
    PAID,
    PENDING,
    TERMINAL_STATES,
    TIMEOUT,
    InvalidTransition,
    Order,
    OrderStore,
    Transaction,
)
from payments_getnet import (
    APPROVED_MESSAGE,
    ConnectorError,
    SaleRequest,
    create_connector,
)
from serial_im30 import describe_ports, find_im30_ports

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("totem")

UI_DIR = BASE_DIR / "ui"
RECEIPTS_DIR = BASE_DIR / "data" / "receipts"

settings: Settings = get_settings()
store: OrderStore = OrderStore(settings.db_full_path)
_payment_tasks: dict[str, asyncio.Task] = {}
_order_locks: dict[str, asyncio.Lock] = {}


def _lock_for(order_id: str) -> asyncio.Lock:
    if order_id not in _order_locks:
        _order_locks[order_id] = asyncio.Lock()
    return _order_locks[order_id]


@asynccontextmanager
async def lifespan(app: FastAPI):
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    UI_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Tótem iniciado | mode=%s connector=%s db=%s",
        settings.mode,
        settings.effective_connector,
        settings.db_full_path,
    )
    yield
    # Cierre limpio: cancelar tareas de pago en curso.
    for task in list(_payment_tasks.values()):
        task.cancel()
    if _payment_tasks:
        await asyncio.gather(*_payment_tasks.values(), return_exceptions=True)
    logger.info("Tótem detenido")


app = FastAPI(title="Tótem Getnet IM30", version="1.0.0", lifespan=lifespan)


# --------------------------------------------------------------------------- #
#  Modelos de entrada
# --------------------------------------------------------------------------- #
class CartItemIn(BaseModel):
    product_id: str
    qty: int = Field(default=1, ge=1, le=99)


class CreateOrderIn(BaseModel):
    items: list[CartItemIn]


class PayIn(BaseModel):
    # Override de resultado solo para demo/pruebas en modo simulación.
    simulate_outcome: Optional[str] = None


class RefundIn(BaseModel):
    amount: Optional[int] = None


# --------------------------------------------------------------------------- #
#  Orquestación de pagos
# --------------------------------------------------------------------------- #
async def _reconcile_order(
    order_id: str,
    amount: int,
    reason: str = "ambiguous",
    connector=None,
) -> bool:
    """Revierte (refund/void) el importe de una operación ambigua.

    Se usa ante un timeout, cancelación o error de transporte durante
    `charging`, donde el terminal pudo haber autorizado el cargo aunque la
    respuesta se perdiera. Antes de permitir un reintento se intenta la
    reversión y se registra el resultado.

    Devuelve True si la reversión fue aprobada; False en caso contrario (la
    orden queda marcada como ambigua NO reconciliada y el reintento se bloquea).

    LIMITACIÓN (I-08): la venta cancelada por `asyncio.wait_for` se ejecuta en
    un hilo (`asyncio.to_thread`) que la cancelación NO detiene. Por eso la
    reversión usa SIEMPRE un conector NUEVO (cuando `connector is None`, que es
    el caso por defecto en las rutas de timeout y error de transporte) en lugar
    de reutilizar el conector cancelado: evitar concurrencia sobre el mismo
    puerto `pyserial`. En hardware homologado debe validarse además que la
    venta previa terminó de desenrollarse antes de emitir el refund.
    """
    order = store.get_order(order_id)
    if order is None:
        return False

    own_connector = connector is None
    conn = connector or create_connector(settings)
    try:
        if own_connector:
            polling = await conn.create()
            if not polling.ok:
                logger.warning(
                    "Orden %s: no se pudo reconciliar, polling falló (%s)",
                    order_id,
                    polling.message,
                )
                store.mark_reconciled(order_id, False)
                return False

        result = await conn.refund(int(amount), order_id)
        store.add_transaction(
            Transaction(
                order_id=order_id,
                code=result.code,
                message=result.message,
                authorization_code=result.authorization_code,
                amount=result.amount or int(amount),
                operation_mode="Reconciliation",
                sale_type="VOID",
                raw=json.dumps(result.raw, ensure_ascii=False),
            )
        )
        if result.approved:
            store.mark_reconciled(order_id, True)
            logger.info(
                "Orden %s reconciliada (%s): reversión aprobada auth=%s",
                order_id,
                reason,
                result.authorization_code,
            )
            return True
        store.mark_reconciled(order_id, False)
        logger.warning(
            "Orden %s: reversión RECHAZADA (%s) code=%s msg=%s",
            order_id,
            reason,
            result.code,
            result.message,
        )
        return False
    except Exception as exc:  # noqa: BLE001
        logger.error("Orden %s: error al reconciliar (%s): %s", order_id, reason, exc)
        try:
            store.mark_reconciled(order_id, False)
        except Exception:  # noqa: BLE001
            pass
        return False
    finally:
        if own_connector:
            try:
                await conn.close()
            except Exception:  # noqa: BLE001
                pass


async def _run_payment(order_id: str, simulate_outcome: Optional[str] = None) -> None:
    """Ejecuta el ciclo create -> polling -> sale -> close para una orden."""
    order = store.get_order(order_id)
    if order is None:
        return
    connector = create_connector(settings)
    sale_attempted = False
    try:
        polling = await connector.create()
        logger.info("Polling %s: code=%s msg=%s", connector.name, polling.code, polling.message)
        if not polling.ok:
            store.transition(order_id, ERROR, error=f"Polling falló: {polling.message}")
            return

        extra: dict[str, Any] = {}
        if simulate_outcome:
            extra["simulate_outcome"] = simulate_outcome
        request = SaleRequest(
            amount=order.total,
            sale_type="Card",
            currency=order.currency,
            order_id=order_id,
            extra=extra,
        )
        try:
            # I-03: el timeout del conector manda (Cloud2Cloud >= 300s).
            sale_attempted = True
            result = await asyncio.wait_for(
                connector.sale(request), timeout=connector.sale_timeout
            )
        except asyncio.TimeoutError:
            logger.warning("Orden %s: timeout esperando tarjeta (ambiguo)", order_id)
            store.transition(order_id, TIMEOUT, error="Timeout esperando la tarjeta")
            # I-02/I-08: intentar reversión ANTES de permitir reintento, usando
            # un conector NUEVO (el de la venta cancelada puede seguir en I/O).
            store.mark_ambiguous(order_id, True)
            await asyncio.sleep(0.05)
            await _reconcile_order(order_id, order.total, reason="timeout")
            return

        tx = Transaction(
            order_id=order_id,
            code=result.code,
            message=result.message,
            terminal_id=result.terminal_id,
            commerce_code=result.commerce_code,
            authorization_code=result.authorization_code,
            amount=result.amount or order.total,
            real_date=result.real_date,
            accounting_date=result.accounting_date,
            operation_mode=result.operation_mode,
            sale_type=result.sale_type,
            raw=json.dumps(result.raw, ensure_ascii=False),
        )
        store.add_transaction(tx)

        if result.approved:
            store.transition(order_id, PAID)
            logger.info("Orden %s APROBADA auth=%s", order_id, result.authorization_code)
        else:
            store.transition(
                order_id, FAILED, error=f"{result.message or 'Rechazado'} (code={result.code})"
            )
            logger.info("Orden %s RECHAZADA code=%s", order_id, result.code)
    except asyncio.CancelledError:
        current = store.get_order(order_id)
        if current and current.status == CHARGING:
            try:
                store.transition(order_id, CANCELLED, error="Cancelado por el usuario")
                # I-02: cancelación durante charging = operación ambigua.
                store.mark_ambiguous(order_id, True)
            except InvalidTransition:
                pass
        raise
    except (ConnectorError, Exception) as exc:  # noqa: BLE001
        if isinstance(exc, asyncio.CancelledError):
            raise
        logger.error("Orden %s error: %s", order_id, exc)
        current = store.get_order(order_id)
        if current and current.status == CHARGING:
            try:
                # I-07: si el error ocurrió durante la venta, la operación es
                # AMBIGUA (el terminal pudo autorizar aunque se perdiera la
                # respuesta). Reconciliar ANTES de dejar la orden en `error`.
                if sale_attempted:
                    store.mark_ambiguous(order_id, True)
                    await _reconcile_order(
                        order_id, order.total, reason="transport-error"
                    )
                store.transition(order_id, ERROR, error=f"{type(exc).__name__}: {exc}")
            except InvalidTransition:
                pass
    finally:
        try:
            await connector.close()
        except Exception:  # noqa: BLE001
            pass
        _payment_tasks.pop(order_id, None)


# --------------------------------------------------------------------------- #
#  API: catálogo y configuración
# --------------------------------------------------------------------------- #
@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "mode": settings.mode}


@app.get("/api/config")
async def api_config() -> dict:
    return settings.to_public_dict()


@app.get("/api/catalog")
async def api_catalog() -> dict:
    return catalog.get_catalog()


# --------------------------------------------------------------------------- #
#  API: órdenes
# --------------------------------------------------------------------------- #
@app.post("/api/orders", status_code=201)
async def create_order(payload: CreateOrderIn) -> dict:
    if not payload.items:
        raise HTTPException(status_code=400, detail="El carrito está vacío")
    try:
        lines = catalog.build_line_items([i.model_dump() for i in payload.items])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    total = catalog.compute_total(lines)
    if total < settings.min_amount:
        raise HTTPException(
            status_code=400,
            detail=f"Monto inválido: {total} {settings.currency} (mínimo {settings.min_amount})",
        )
    if total > settings.max_amount:
        raise HTTPException(
            status_code=400,
            detail=f"Monto excedido: {total} {settings.currency} (máximo {settings.max_amount})",
        )

    order = store.create_order(lines, total, currency=settings.currency)
    return order.to_dict()


@app.get("/api/orders")
async def list_orders(limit: int = 50) -> dict:
    limit = max(1, min(limit, 200))
    return {"orders": [o.to_dict() for o in store.list_orders(limit)]}


@app.get("/api/orders/{order_id}")
async def get_order(order_id: str) -> dict:
    order = store.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    return order.to_dict()


@app.get("/api/orders/{order_id}/status")
async def order_status(order_id: str) -> dict:
    order = store.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    tx = store.get_last_transaction(order_id)
    return {
        "order": order.to_dict(),
        "transaction": tx.to_dict() if tx else None,
        "charging": order.status == CHARGING,
    }


@app.post("/api/orders/{order_id}/pay", status_code=202)
async def pay_order(order_id: str, payload: Optional[PayIn] = None) -> dict:
    # I-06: exclusión mutua real por orden durante toda la secuencia de pago.
    async with _lock_for(order_id):
        order = store.get_order(order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="Orden no encontrada")
        if order.status in (PAID, EMITTED):
            raise HTTPException(status_code=409, detail="La orden ya fue pagada")
        if order.status == CHARGING:
            raise HTTPException(status_code=409, detail="La orden ya está en proceso de cobro")
        if order.total < settings.min_amount or order.total > settings.max_amount:
            raise HTTPException(status_code=400, detail="Monto de orden inválido")

        # I-02: si la operación anterior fue ambigua (timeout/cancel en charging),
        # exigir reconciliación (reversión) antes de permitir el reintento.
        if order.ambiguous and not order.reconciled:
            ok = await _reconcile_order(order_id, order.total, reason="pre-retry")
            order = store.get_order(order_id) or order
            if not ok:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Operación previa ambigua sin reconciliar; se requiere "
                        "revisión manual del terminal antes de reintentar."
                    ),
                )

        try:
            order = store.transition(order_id, CHARGING)
        except InvalidTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        simulate = payload.simulate_outcome if payload else None
        task = asyncio.create_task(_run_payment(order_id, simulate))
        _payment_tasks[order_id] = task
        return {"order": order.to_dict(), "status": order.status}


@app.post("/api/orders/{order_id}/cancel")
async def cancel_order(order_id: str) -> dict:
    # I-09: mismo candado por orden para coherencia con pay/refund.
    async with _lock_for(order_id):
        order = store.get_order(order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="Orden no encontrada")

        task = _payment_tasks.get(order_id)
        if task and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=5)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):  # noqa: BLE001
                pass
        else:
            if order.status in (PENDING, FAILED, TIMEOUT):
                try:
                    order = store.transition(order_id, CANCELLED, error="Cancelado por el usuario")
                except InvalidTransition as exc:
                    raise HTTPException(status_code=409, detail=str(exc)) from exc
        refreshed = store.get_order(order_id)
        # I-02: si el cobro se canceló durante `charging`, reversar antes de dar
        # por cancelada la operación (pudo haberse autorizado en el terminal).
        if refreshed and refreshed.ambiguous and not refreshed.reconciled:
            await _reconcile_order(order_id, refreshed.total, reason="cancel")
            refreshed = store.get_order(order_id) or refreshed
        return refreshed.to_dict() if refreshed else order.to_dict()


@app.post("/api/orders/{order_id}/refund")
async def refund_order(order_id: str, payload: Optional[RefundIn] = None) -> dict:
    # I-09: exclusión mutua por orden + guarda atómica en mark_refunded evitan
    # el doble reembolso por carrera (check-then-act).
    async with _lock_for(order_id):
        order = store.get_order(order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="Orden no encontrada")
        if order.status not in (PAID, EMITTED):
            raise HTTPException(status_code=409, detail="Solo se puede reembolsar una orden pagada")
        if order.refunded:
            raise HTTPException(status_code=409, detail="La orden ya fue reembolsada")
        amount = (payload.amount if payload and payload.amount else order.total)
        if amount <= 0 or amount > order.total:
            raise HTTPException(status_code=400, detail="Monto de reembolso inválido")

        connector = create_connector(settings)
        try:
            # I-04: validar Polling (Code=0) antes de operar (todos los conectores).
            polling = await connector.create()
            if not polling.ok:
                raise HTTPException(
                    status_code=502,
                    detail=f"Polling falló (code={polling.code}): {polling.message}",
                )
            result = await connector.refund(amount, order_id)
            # Registrar SIEMPRE el intento de reembolso en `transactions`.
            store.add_transaction(
                Transaction(
                    order_id=order_id,
                    code=result.code,
                    message=result.message,
                    authorization_code=result.authorization_code,
                    amount=result.amount or amount,
                    operation_mode="Refund",
                    sale_type="REFUND",
                    raw=json.dumps(result.raw, ensure_ascii=False),
                )
            )
            if not result.approved:
                raise HTTPException(
                    status_code=502,
                    detail=f"Reembolso rechazado: {result.message or 'sin detalle'} "
                    f"(code={result.code})",
                )
            # I-04/I-09: marcar reembolsada de forma atómica e idempotente.
            try:
                store.mark_refunded(order_id, True)
            except InvalidTransition as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            refreshed = store.get_order(order_id) or order
            return {
                "refund": result.to_dict(),
                "order_id": order_id,
                "order": refreshed.to_dict(),
            }
        except ConnectorError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        finally:
            try:
                await connector.close()
            except Exception:  # noqa: BLE001
                pass


# --------------------------------------------------------------------------- #
#  API: comprobante
# --------------------------------------------------------------------------- #
def _require_receipt_order(order_id: str) -> tuple[Order, Transaction]:
    order = store.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    tx = store.get_last_transaction(order_id)
    return order, (tx or Transaction(order_id=order_id))


@app.get("/api/orders/{order_id}/receipt", response_class=HTMLResponse)
async def receipt_html(order_id: str) -> HTMLResponse:
    order, tx = _require_receipt_order(order_id)
    # Marcar como emitido (idempotente) y registrar la reemisión.
    if order.status == PAID:
        try:
            order = store.transition(order_id, EMITTED)
        except InvalidTransition:
            pass
    else:
        store._bump_receipt(order_id)
        order = store.get_order(order_id) or order
    return HTMLResponse(receipt_mod.render_html(order, tx))


@app.get("/api/orders/{order_id}/receipt.pdf")
async def receipt_pdf(order_id: str) -> Response:
    order, tx = _require_receipt_order(order_id)
    if order.status == PAID:
        try:
            order = store.transition(order_id, EMITTED)
        except InvalidTransition:
            pass
    pdf_bytes = receipt_mod.generate_pdf(order, tx)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="comprobante-{order_id}.pdf"'
        },
    )


@app.get("/api/orders/{order_id}/events")
async def order_events(order_id: str, request: Request) -> StreamingResponse:
    if store.get_order(order_id) is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    async def event_stream():
        last: Optional[str] = None
        while True:
            if await request.is_disconnected():
                break
            order = store.get_order(order_id)
            if order is None:
                break
            payload = json.dumps(order.to_dict(), ensure_ascii=False)
            if payload != last:
                yield f"event: order\ndata: {payload}\n\n"
                last = payload
            if order.status in TERMINAL_STATES:
                break
            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------------------------------- #
#  API: terminal / diagnóstico
# --------------------------------------------------------------------------- #
@app.get("/api/terminal/status")
async def terminal_status() -> dict:
    ports = describe_ports()
    status: dict[str, Any] = {
        "mode": settings.mode,
        "connector": settings.effective_connector,
        "baudrate": settings.baudrate,
        "configured_port": settings.serial_port or None,
        "serial": ports,
    }
    if settings.effective_connector == "simulation":
        status["polling"] = {"code": 0, "message": "OK (simulación)", "connected": True}
        return status

    connector = create_connector(settings)
    try:
        polling = await connector.create()
        status["polling"] = polling.to_dict()
    except Exception as exc:  # noqa: BLE001
        status["polling"] = {"code": -1, "message": str(exc), "connected": False}
    finally:
        try:
            await connector.close()
        except Exception:  # noqa: BLE001
            pass
    return status


@app.get("/api/terminal/ports")
async def terminal_ports() -> dict:
    return {"ports": [p.to_dict() for p in find_im30_ports()]}


# --------------------------------------------------------------------------- #
#  UI estática
# --------------------------------------------------------------------------- #
if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")
    if (UI_DIR / "assets").exists():
        app.mount(
            "/assets", StaticFiles(directory=str(UI_DIR / "assets")), name="assets"
        )


@app.get("/", response_class=HTMLResponse)
async def index() -> Response:
    index_file = UI_DIR / "index.html"
    if not index_file.exists():
        return JSONResponse(
            status_code=500, content={"detail": "ui/index.html no encontrado"}
        )
    return FileResponse(str(index_file))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
