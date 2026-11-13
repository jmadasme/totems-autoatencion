"""Pruebas del conector de pagos (modo simulación)."""
from __future__ import annotations

import asyncio

import pytest

from payments_getnet import (
    APPROVED_CODE,
    APPROVED_MESSAGE,
    App2AppConnector,
    ConnectorError,
    SaleRequest,
    SaleResult,
    SimulatedConnector,
    create_connector,
)


def test_factory_simulation_forces_simulated(sim_settings):
    connector = create_connector(sim_settings)
    assert isinstance(connector, SimulatedConnector)
    assert connector.name == "simulation"


def test_sale_result_from_dict_mapping():
    data = {
        "Code": 0,
        "Message": "APPROVED",
        "CommerceCode": "123456",
        "TerminalId": "TERM01",
        "AuthorizationCode": "A1B2C3",
        "Amount": 10000,
        "AccountingDate": "2026-09-14T12:00:00Z",
        "RealDate": "2026-09-14T09:00:00-03:00",
        "SaleType": "Card",
        "OperationMode": "Integrated",
        "OriginalAmount": 10000,
    }
    result = SaleResult.from_dict(data)
    assert result.approved
    assert result.authorization_code == "A1B2C3"
    assert result.terminal_id == "TERM01"
    assert result.amount == 10000


async def test_simulated_polling_ok(sim_settings):
    connector = create_connector(sim_settings)
    polling = await connector.create()
    assert polling.ok
    assert polling.connected
    assert polling.code == APPROVED_CODE
    await connector.close()


async def test_simulated_sale_approved(sim_settings):
    connector = create_connector(sim_settings)
    await connector.create()
    result = await connector.sale(SaleRequest(amount=10000, order_id="ORD1"))
    assert result.approved
    assert result.message == APPROVED_MESSAGE
    assert result.amount == 10000
    assert result.authorization_code
    assert result.raw.get("Simulated") is True
    await connector.close()


async def test_simulated_sale_declined(sim_settings):
    connector = create_connector(sim_settings)
    await connector.create()
    result = await connector.sale(
        SaleRequest(amount=5000, order_id="ORD2", extra={"simulate_outcome": "declined"})
    )
    assert not result.approved
    assert result.code != APPROVED_CODE
    assert result.message == "REJECTED"
    await connector.close()


async def test_simulated_sale_timeout(sim_settings):
    connector = create_connector(sim_settings)
    await connector.create()
    with pytest.raises(asyncio.TimeoutError):
        await connector.sale(
            SaleRequest(amount=5000, order_id="ORD3", extra={"simulate_outcome": "timeout"})
        )
    await connector.close()


async def test_simulated_sale_error(sim_settings):
    connector = create_connector(sim_settings)
    await connector.create()
    with pytest.raises(ConnectorError):
        await connector.sale(
            SaleRequest(amount=5000, order_id="ORD4", extra={"simulate_outcome": "error"})
        )
    await connector.close()


async def test_simulated_refund(sim_settings):
    connector = create_connector(sim_settings)
    await connector.create()
    refund = await connector.refund(10000, "ORD5")
    assert refund.approved
    assert refund.amount == 10000
    await connector.close()


def test_cloud_sale_timeout_at_least_300():
    """I-03: en cloud el timeout de venta no puede ser menor que el del conector."""
    from config import load_settings, override_settings
    from payments_getnet import CloudConnector

    base = load_settings()
    settings = override_settings(
        base, mode="production", connector="cloud", order_timeout_seconds=120
    )
    connector = create_connector(settings)
    assert isinstance(connector, CloudConnector)
    assert connector.sale_timeout >= 300
    assert connector.sale_timeout == max(120, CloudConnector.DEFAULT_TIMEOUT)


def test_app2app_build_sale_params():
    """El JSON de SALE cumple el contrato App2App (Manual A2A 1.22 §3.1)."""
    from config import load_settings, override_settings

    settings = override_settings(
        load_settings(), mode="production", connector="app2app"
    )
    connector = App2AppConnector(settings)
    params = connector.build_sale_params(SaleRequest(amount=3500, order_id="ORD-42"))
    assert params["Amount"] == 3500
    assert params["SaleType"] == App2AppConnector.SALE_TYPE_COMPRA_AFECTA
    assert params["TypeApp"] == App2AppConnector.TYPE_APP_APP
    assert params["IntegrationType"] == App2AppConnector.INTEGRATION_TYPE_APP2APP
    assert params["SoftwareName"] == App2AppConnector.SOFTWARE_NAME
    assert params["TicketNumber"] == "0042"
    assert params["PrintOnPos"] is False
    assert params["RestrictedCards"] is None
    assert params["AllowedCards"] is None
    assert params["PlaceCardToPayTimeout"] == settings.app2app_place_card_timeout_ms // 1000
    assert params["PaymentResultTimeout"] == settings.app2app_payment_timeout_ms // 1000

    refund = connector.build_refund_params(1200, "ORD-42", "AUTH123")
    assert refund["AuthorizationCode"] == "AUTH123"
    assert refund["Amount"] == 1200
    assert refund["TypeApp"] == App2AppConnector.TYPE_APP_APP
    assert "SaleType" not in refund

    cancel = connector.build_cancellation_params(1200, "ORD-42", "77")
    assert cancel["OperationId"] == 77
    assert cancel["TypeApp"] == App2AppConnector.TYPE_APP_APP
    assert "Amount" not in cancel


def test_app2app_build_sale_params_rejects_bad_amount():
    from config import load_settings, override_settings

    settings = override_settings(
        load_settings(), mode="production", connector="app2app", max_amount=999
    )
    connector = App2AppConnector(settings)
    with pytest.raises(ConnectorError):
        connector.build_sale_params(SaleRequest(amount=1000))


def test_app2app_parse_logcat_response():
    approved = (
        "09-14 16:11:23.000  1234  1234 W ApiActivity: "
        'responseToApplication = {"responseCode":"00","responseMessage":"Aprobado",'
        '"authorizationCode":"551437","amount":3500}'
    )
    parsed = App2AppConnector.parse_logcat_response(approved)
    assert parsed is not None
    assert parsed["responseCode"] == "00"
    assert parsed["authorizationCode"] == "551437"

    rejected = (
        "09-14 16:11:23.000  1234  1234 W ApiActivity: "
        'responseToApplication = {"responseCode":"05","responseMessage":"Rechazado"}'
    )
    parsed_rejected = App2AppConnector.parse_logcat_response(rejected)
    assert parsed_rejected is not None
    assert parsed_rejected["responseCode"] == "05"

    error = "09-14 16:11:23.000 W ApiActivity: responseError: Terminal no provisionado"
    parsed_error = App2AppConnector.parse_logcat_response(error)
    assert parsed_error is not None
    assert parsed_error["_error"] is True

    assert App2AppConnector.parse_logcat_response("sin marcadores") is None


async def test_app2app_sale_simulation_fallback():
    """Sin ADB/provisioning el conector degrada a simulación, sin bloquear."""
    from config import load_settings, override_settings

    settings = override_settings(
        load_settings(),
        mode="production",
        connector="app2app",
        adb_path="/nonexistent/adb-does-not-exist",
        terminal_id="",
        simulation_outcome="approved",
        simulation_delay_seconds=0.0,
    )
    connector = create_connector(settings)
    assert isinstance(connector, App2AppConnector)

    polling = await connector.create()
    assert polling.ok
    assert "SIMULACI" in polling.message.upper()

    result = await connector.sale(SaleRequest(amount=1000, order_id="X1"))
    assert result.approved
    assert result.raw.get("Simulated") is True
    assert result.raw.get("App2AppFallback")
    await connector.close()


def test_validate_polling_raises_on_nonzero_code():
    """I-04: `create()` valida Polling (Code=0) para todos los conectores."""
    from payments_getnet import PollingResult

    with pytest.raises(ConnectorError):
        SimulatedConnector._validate_polling(
            PollingResult(code=5, message="NO CONECTADO", connected=False)
        )
    ok = SimulatedConnector._validate_polling(
        PollingResult(code=APPROVED_CODE, message="OK", connected=True)
    )
    assert ok.ok
