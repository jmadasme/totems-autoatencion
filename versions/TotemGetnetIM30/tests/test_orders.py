"""Pruebas de la máquina de estados de órdenes e idempotencia."""
from __future__ import annotations

import pytest

from orders import (
    CANCELLED,
    CHARGING,
    EMITTED,
    ERROR,
    FAILED,
    PAID,
    PENDING,
    TIMEOUT,
    InvalidTransition,
    OrderNotFound,
    OrderStore,
    Transaction,
)

ITEMS = [
    {"product_id": "beb-cafe", "name": "Café", "unit_price": 2000, "qty": 1, "subtotal": 2000}
]


def test_create_order_pending(store: OrderStore):
    order = store.create_order(ITEMS, 2000)
    assert order.status == PENDING
    assert order.total == 2000
    assert store.get_order(order.id).items[0]["name"] == "Café"


def test_happy_path_state_machine(store: OrderStore):
    order = store.create_order(ITEMS, 2000)
    order = store.transition(order.id, CHARGING)
    assert order.status == CHARGING
    order = store.transition(order.id, PAID)
    assert order.status == PAID
    order = store.transition(order.id, EMITTED)
    assert order.status == EMITTED


def test_invalid_transition_pending_to_paid(store: OrderStore):
    order = store.create_order(ITEMS, 2000)
    with pytest.raises(InvalidTransition):
        store.transition(order.id, PAID)


def test_double_charge_prevented(store: OrderStore):
    """Una orden pagada no puede volver a charging (no doble cobro)."""
    order = store.create_order(ITEMS, 2000)
    store.transition(order.id, CHARGING)
    store.transition(order.id, PAID)
    with pytest.raises(InvalidTransition):
        store.transition(order.id, CHARGING)


def test_emitted_is_idempotent(store: OrderStore):
    order = store.create_order(ITEMS, 2000)
    store.transition(order.id, CHARGING)
    store.transition(order.id, PAID)
    first = store.transition(order.id, EMITTED)
    second = store.transition(order.id, EMITTED)
    assert second.status == EMITTED
    assert second.receipt_count >= first.receipt_count


def test_retry_from_failed(store: OrderStore):
    order = store.create_order(ITEMS, 2000)
    store.transition(order.id, CHARGING)
    store.transition(order.id, FAILED, error="rechazado")
    order = store.transition(order.id, CHARGING)
    assert order.status == CHARGING
    order = store.transition(order.id, PAID)
    assert order.status == PAID


def test_timeout_and_cancel_branches(store: OrderStore):
    o1 = store.create_order(ITEMS, 1000)
    store.transition(o1.id, CHARGING)
    assert store.transition(o1.id, TIMEOUT, error="sin tarjeta").status == TIMEOUT

    o2 = store.create_order(ITEMS, 1000)
    assert store.transition(o2.id, CANCELLED).status == CANCELLED

    o3 = store.create_order(ITEMS, 1000)
    store.transition(o3.id, CHARGING)
    assert store.transition(o3.id, ERROR, error="boom").status == ERROR


def test_order_not_found(store: OrderStore):
    with pytest.raises(OrderNotFound):
        store.transition("NOEXISTE", CHARGING)


def test_transactions_persistence(store: OrderStore):
    order = store.create_order(ITEMS, 2000)
    store.transition(order.id, CHARGING)
    store.add_transaction(
        Transaction(
            order_id=order.id,
            code=0,
            message="APPROVED",
            terminal_id="T1",
            authorization_code="AUTH1",
            amount=2000,
        )
    )
    store.transition(order.id, PAID)
    txs = store.get_transactions(order.id)
    assert len(txs) == 1
    assert txs[0].authorization_code == "AUTH1"
    assert store.get_last_transaction(order.id).code == 0


def test_list_orders(store: OrderStore):
    store.create_order(ITEMS, 1000)
    store.create_order(ITEMS, 2000)
    assert len(store.list_orders()) == 2


def test_flags_refund_ambiguous_reconciled(store: OrderStore):
    """I-02/I-04: flags de reembolso y reconciliación persistidos."""
    order = store.create_order(ITEMS, 2000)
    assert order.refunded is False
    assert order.ambiguous is False
    assert order.reconciled is False

    store.transition(order.id, CHARGING)
    store.transition(order.id, TIMEOUT, error="ambiguo")
    store.mark_ambiguous(order.id, True)
    assert store.get_order(order.id).ambiguous is True
    store.mark_reconciled(order.id, True)
    assert store.get_order(order.id).reconciled is True

    paid = store.create_order(ITEMS, 2000)
    store.transition(paid.id, CHARGING)
    store.transition(paid.id, PAID)
    store.mark_refunded(paid.id, True)
    refreshed = store.get_order(paid.id)
    assert refreshed.refunded is True
    assert refreshed.to_dict()["refunded"] is True


def test_mark_refunded_idempotent_atomic(store: OrderStore):
    """I-09: la marca de reembolso es atómica; un segundo intento falla."""
    order = store.create_order(ITEMS, 2000)
    store.transition(order.id, CHARGING)
    store.transition(order.id, PAID)
    store.mark_refunded(order.id, True)
    assert store.get_order(order.id).refunded is True
    with pytest.raises(InvalidTransition):
        store.mark_refunded(order.id, True)
    assert store.get_order(order.id).refunded is True
