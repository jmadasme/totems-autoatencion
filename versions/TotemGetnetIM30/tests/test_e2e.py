"""Flujo end-to-end del tótem en modo simulación (FastAPI TestClient)."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from orders import OrderStore
from tests.conftest import make_sim_settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    import app as app_module

    settings = make_sim_settings(tmp_path)
    monkeypatch.setattr(app_module, "settings", settings)
    monkeypatch.setattr(app_module, "store", OrderStore(tmp_path / "orders.db"))
    app_module._payment_tasks.clear()
    with TestClient(app_module.app) as c:
        yield c
    app_module._payment_tasks.clear()


def _wait_terminal(client, order_id, timeout=10.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        resp = client.get(f"/api/orders/{order_id}/status")
        assert resp.status_code == 200
        last = resp.json()
        if last["order"]["status"] != "charging":
            return last
        time.sleep(0.05)
    raise AssertionError(f"La orden no llegó a estado terminal: {last}")


def test_health_and_config(client):
    assert client.get("/api/health").json()["status"] == "ok"
    cfg = client.get("/api/config").json()
    assert cfg["mode"] == "simulation"
    assert cfg["connector"] == "simulation"


def test_config_does_not_expose_sensitive_identifiers(client):
    """I-01: /api/config no debe exponer terminal_id ni commerce_code."""
    cfg = client.get("/api/config").json()
    assert "terminal_id" not in cfg
    assert "commerce_code" not in cfg
    assert "merchant_id" not in cfg
    assert "api_key" not in cfg
    assert "client_secret" not in cfg
    assert "credentials_configured" in cfg


def test_catalog_loads(client):
    data = client.get("/api/catalog").json()
    assert data["currency"] == "CLP"
    assert len(data["categories"]) >= 2
    assert any(p["category"] == "bebidas" for p in data["products"])
    assert any(p["category"] == "snacks" for p in data["products"])


def test_full_flow_approved_and_receipt(client):
    catalog = client.get("/api/catalog").json()
    p1 = catalog["products"][0]
    p2 = catalog["products"][1]

    order = client.post(
        "/api/orders",
        json={"items": [{"product_id": p1["id"], "qty": 2}, {"product_id": p2["id"], "qty": 1}]},
    ).json()
    assert order["status"] == "pending"
    expected_total = p1["price"] * 2 + p2["price"]
    assert order["total"] == expected_total

    resp = client.post(f"/api/orders/{order['id']}/pay", json={})
    assert resp.status_code == 202

    status = _wait_terminal(client, order["id"])
    assert status["order"]["status"] in ("paid", "emitted")
    assert status["transaction"]["code"] == 0
    assert status["transaction"]["authorization_code"]

    html = client.get(f"/api/orders/{order['id']}/receipt")
    assert html.status_code == 200
    assert order["id"] in html.text

    pdf = client.get(f"/api/orders/{order['id']}/receipt.pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")


def test_flow_declined_and_retry(client):
    catalog = client.get("/api/catalog").json()
    pid = catalog["products"][0]["id"]
    order = client.post("/api/orders", json={"items": [{"product_id": pid, "qty": 1}]}).json()

    client.post(f"/api/orders/{order['id']}/pay", json={"simulate_outcome": "declined"})
    status = _wait_terminal(client, order["id"])
    assert status["order"]["status"] == "failed"
    assert status["transaction"]["code"] != 0

    # Reintento de la misma orden (aprobado).
    resp = client.post(f"/api/orders/{order['id']}/pay", json={})
    assert resp.status_code == 202
    status = _wait_terminal(client, order["id"])
    assert status["order"]["status"] in ("paid", "emitted")


def test_flow_timeout(client):
    catalog = client.get("/api/catalog").json()
    pid = catalog["products"][0]["id"]
    order = client.post("/api/orders", json={"items": [{"product_id": pid, "qty": 1}]}).json()

    client.post(f"/api/orders/{order['id']}/pay", json={"simulate_outcome": "timeout"})
    status = _wait_terminal(client, order["id"])
    assert status["order"]["status"] == "timeout"

    # I-02: la operación ambigua debe reconciliarse (reversión) automáticamente.
    deadline = time.time() + 5.0
    reconciled = False
    while time.time() < deadline:
        st = client.get(f"/api/orders/{order['id']}/status").json()
        if st["order"]["reconciled"]:
            reconciled = True
            break
        time.sleep(0.05)
    assert reconciled, "la orden ambigua no se reconcilió"
    assert st["order"]["ambiguous"] is True
    # El reintento debe permitirse tras reconciliar.
    resp = client.post(f"/api/orders/{order['id']}/pay", json={})
    assert resp.status_code == 202


def test_flow_transport_error_reconciles(client):
    """I-07: un error de transporte durante la venta marca la orden ambigua y
    se reconcilia (reversión) antes de permitir el reintento."""
    catalog = client.get("/api/catalog").json()
    pid = catalog["products"][0]["id"]
    order = client.post("/api/orders", json={"items": [{"product_id": pid, "qty": 1}]}).json()

    client.post(f"/api/orders/{order['id']}/pay", json={"simulate_outcome": "error"})
    status = _wait_terminal(client, order["id"])
    assert status["order"]["status"] == "error"

    # La operación ambigua debe reconciliarse automáticamente (reversión aprobada).
    deadline = time.time() + 5.0
    st = None
    while time.time() < deadline:
        st = client.get(f"/api/orders/{order['id']}/status").json()
        if st["order"]["reconciled"]:
            break
        time.sleep(0.05)
    assert st["order"]["ambiguous"] is True
    assert st["order"]["reconciled"] is True
    # Tras reconciliar, el reintento debe permitirse.
    assert client.post(f"/api/orders/{order['id']}/pay", json={}).status_code == 202


def test_flow_transport_error_blocks_retry_when_reversal_fails(client, monkeypatch):
    """I-07: si la reversión falla, la orden ambigua bloquea el reintento (409)."""
    import app as app_module
    from config import override_settings

    monkeypatch.setattr(
        app_module,
        "settings",
        override_settings(app_module.settings, simulation_refund_outcome="declined"),
    )
    catalog = client.get("/api/catalog").json()
    pid = catalog["products"][0]["id"]
    order = client.post("/api/orders", json={"items": [{"product_id": pid, "qty": 1}]}).json()

    client.post(f"/api/orders/{order['id']}/pay", json={"simulate_outcome": "error"})
    status = _wait_terminal(client, order["id"])
    assert status["order"]["status"] == "error"
    assert status["order"]["ambiguous"] is True
    assert status["order"]["reconciled"] is False
    # La reversión falló → el reintento queda bloqueado por seguridad.
    resp = client.post(f"/api/orders/{order['id']}/pay", json={})
    assert resp.status_code == 409


def test_refund_declined_returns_502(client, monkeypatch):
    """I-04: un reembolso rechazado responde 502 y no marca la orden como reembolsada."""
    import app as app_module
    from config import override_settings

    catalog = client.get("/api/catalog").json()
    pid = catalog["products"][0]["id"]
    order = client.post("/api/orders", json={"items": [{"product_id": pid, "qty": 1}]}).json()
    client.post(f"/api/orders/{order['id']}/pay", json={})
    _wait_terminal(client, order["id"])

    monkeypatch.setattr(
        app_module,
        "settings",
        override_settings(app_module.settings, simulation_refund_outcome="declined"),
    )
    resp = client.post(f"/api/orders/{order['id']}/refund", json={})
    assert resp.status_code == 502
    st = client.get(f"/api/orders/{order['id']}/status").json()
    assert st["order"]["refunded"] is False


def test_refund_approved_persists_and_flags(client):
    """I-04: reembolso aprobado persiste transacción y marca la orden."""
    catalog = client.get("/api/catalog").json()
    pid = catalog["products"][0]["id"]
    order = client.post("/api/orders", json={"items": [{"product_id": pid, "qty": 1}]}).json()
    client.post(f"/api/orders/{order['id']}/pay", json={})
    _wait_terminal(client, order["id"])

    resp = client.post(f"/api/orders/{order['id']}/refund", json={})
    assert resp.status_code == 200
    assert resp.json()["refund"]["approved"] is True
    st = client.get(f"/api/orders/{order['id']}/status").json()
    assert st["order"]["refunded"] is True
    # Segundo reembolso rechazado (ya reembolsada).
    assert client.post(f"/api/orders/{order['id']}/refund", json={}).status_code == 409


def test_double_pay_rejected(client):
    catalog = client.get("/api/catalog").json()
    pid = catalog["products"][0]["id"]
    order = client.post("/api/orders", json={"items": [{"product_id": pid, "qty": 1}]}).json()
    client.post(f"/api/orders/{order['id']}/pay", json={})
    status = _wait_terminal(client, order["id"])
    assert status["order"]["status"] in ("paid", "emitted")

    again = client.post(f"/api/orders/{order['id']}/pay", json={})
    assert again.status_code == 409


def test_cancel_pending_order(client):
    catalog = client.get("/api/catalog").json()
    pid = catalog["products"][0]["id"]
    order = client.post("/api/orders", json={"items": [{"product_id": pid, "qty": 1}]}).json()
    resp = client.post(f"/api/orders/{order['id']}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_invalid_cart(client):
    assert client.post("/api/orders", json={"items": []}).status_code == 400
    bad = client.post("/api/orders", json={"items": [{"product_id": "noexiste", "qty": 1}]})
    assert bad.status_code == 400
    invalid_qty = client.post(
        "/api/orders", json={"items": [{"product_id": "beb-cafe", "qty": 0}]}
    )
    assert invalid_qty.status_code == 422


def test_terminal_status_simulation(client):
    status = client.get("/api/terminal/status").json()
    assert status["mode"] == "simulation"
    assert status["polling"]["connected"] is True
    ports = client.get("/api/terminal/ports").json()
    assert "ports" in ports


def test_index_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Tótem" in resp.text or "Totem" in resp.text


def test_history(client):
    catalog = client.get("/api/catalog").json()
    pid = catalog["products"][0]["id"]
    client.post("/api/orders", json={"items": [{"product_id": pid, "qty": 1}]})
    orders = client.get("/api/orders").json()["orders"]
    assert len(orders) >= 1
