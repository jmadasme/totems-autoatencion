"""Modelo de órdenes, máquina de estados e idempotencia (SQLite).

Estados:
    pending -> charging -> paid -> emitted
Ramificaciones:
    failed | timeout | cancelled | error

Reglas de idempotencia:
- Una orden solo puede pasar a `paid` una vez (desde `charging`).
- `paid -> emitted` es idempotente (re-emitir comprobante no cambia el estado).
- `charging` no puede volver a `pending`.
- Reintentos reutilizan la misma orden: failed/timeout/cancelled/error -> charging.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PENDING = "pending"
CHARGING = "charging"
PAID = "paid"
EMITTED = "emitted"
FAILED = "failed"
TIMEOUT = "timeout"
CANCELLED = "cancelled"
ERROR = "error"

TERMINAL_STATES = {PAID, EMITTED, FAILED, TIMEOUT, CANCELLED, ERROR}

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    PENDING: {CHARGING, CANCELLED, ERROR, TIMEOUT, FAILED},
    CHARGING: {PAID, FAILED, TIMEOUT, CANCELLED, ERROR},
    PAID: {EMITTED},
    EMITTED: set(),
    FAILED: {CHARGING, CANCELLED, ERROR},
    TIMEOUT: {CHARGING, CANCELLED, ERROR},
    CANCELLED: {CHARGING, ERROR},
    ERROR: {CHARGING, CANCELLED},
}


class InvalidTransition(Exception):
    """Transición de estado no permitida."""


class OrderNotFound(Exception):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass
class Order:
    id: str
    status: str
    total: int
    currency: str = "CLP"
    items: list[dict] = field(default_factory=list)
    error: Optional[str] = None
    receipt_count: int = 0
    refunded: bool = False
    ambiguous: bool = False
    reconciled: bool = False
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "total": self.total,
            "currency": self.currency,
            "items": self.items,
            "error": self.error,
            "receipt_count": self.receipt_count,
            "refunded": self.refunded,
            "ambiguous": self.ambiguous,
            "reconciled": self.reconciled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Transaction:
    id: Optional[int] = None
    order_id: str = ""
    code: int = -1
    message: str = ""
    terminal_id: str = ""
    commerce_code: str = ""
    authorization_code: str = ""
    amount: int = 0
    real_date: str = ""
    accounting_date: str = ""
    operation_mode: str = ""
    sale_type: str = ""
    raw: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "order_id": self.order_id,
            "code": self.code,
            "message": self.message,
            "terminal_id": self.terminal_id,
            "commerce_code": self.commerce_code,
            "authorization_code": self.authorization_code,
            "amount": self.amount,
            "real_date": self.real_date,
            "accounting_date": self.accounting_date,
            "operation_mode": self.operation_mode,
            "sale_type": self.sale_type,
            "created_at": self.created_at,
        }


_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    total INTEGER NOT NULL,
    currency TEXT NOT NULL DEFAULT 'CLP',
    items TEXT NOT NULL DEFAULT '[]',
    error TEXT,
    receipt_count INTEGER NOT NULL DEFAULT 0,
    refunded INTEGER NOT NULL DEFAULT 0,
    ambiguous INTEGER NOT NULL DEFAULT 0,
    reconciled INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    code INTEGER NOT NULL,
    message TEXT,
    terminal_id TEXT,
    commerce_code TEXT,
    authorization_code TEXT,
    amount INTEGER,
    real_date TEXT,
    accounting_date TEXT,
    operation_mode TEXT,
    sale_type TEXT,
    raw TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id)
);

CREATE INDEX IF NOT EXISTS idx_tx_order ON transactions(order_id);
"""


class OrderStore:
    """Persistencia SQLite de órdenes y transacciones."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Añade columnas nuevas a bases de datos ya creadas (idempotente)."""
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(orders)").fetchall()}
        new_cols = {
            "refunded": "INTEGER NOT NULL DEFAULT 0",
            "ambiguous": "INTEGER NOT NULL DEFAULT 0",
            "reconciled": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, ddl in new_cols.items():
            if name not in cols:
                conn.execute(f"ALTER TABLE orders ADD COLUMN {name} {ddl}")

    # ---------------------------------------------------------------- orders
    def create_order(
        self,
        items: list[dict],
        total: int,
        currency: str = "CLP",
        order_id: Optional[str] = None,
    ) -> Order:
        import uuid

        oid = order_id or uuid.uuid4().hex[:12].upper()
        now = _now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO orders (id, status, total, currency, items, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (oid, PENDING, int(total), currency, json.dumps(items), now, now),
            )
        return self.get_order(oid)  # type: ignore[return-value]

    def _row_to_order(self, row: sqlite3.Row) -> Order:
        keys = row.keys()
        return Order(
            id=row["id"],
            status=row["status"],
            total=row["total"],
            currency=row["currency"],
            items=json.loads(row["items"] or "[]"),
            error=row["error"],
            receipt_count=row["receipt_count"],
            refunded=bool(row["refunded"]) if "refunded" in keys else False,
            ambiguous=bool(row["ambiguous"]) if "ambiguous" in keys else False,
            reconciled=bool(row["reconciled"]) if "reconciled" in keys else False,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_order(self, order_id: str) -> Optional[Order]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
        return self._row_to_order(row) if row else None

    def list_orders(self, limit: int = 50) -> list[Order]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_order(r) for r in rows]

    def transition(
        self, order_id: str, new_status: str, error: Optional[str] = None
    ) -> Order:
        """Transiciona el estado validando la máquina de estados.

        Idempotencia: `paid -> emitted` repetido no falla (re-emisión).
        """
        with self._lock:
            order = self.get_order(order_id)
            if order is None:
                raise OrderNotFound(order_id)
            current = order.status
            if current == new_status:
                # Re-emisión de comprobante: idempotente.
                if new_status == EMITTED:
                    self._bump_receipt(order_id)
                    return self.get_order(order_id)  # type: ignore[return-value]
                raise InvalidTransition(f"{current} -> {new_status}")
            allowed = ALLOWED_TRANSITIONS.get(current, set())
            if new_status not in allowed:
                raise InvalidTransition(f"{current} -> {new_status}")
            now = _now_iso()
            with self._connect() as conn:
                conn.execute(
                    "UPDATE orders SET status = ?, error = ?, updated_at = ? WHERE id = ?",
                    (new_status, error, now, order_id),
                )
            return self.get_order(order_id)  # type: ignore[return-value]

    def _bump_receipt(self, order_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE orders SET receipt_count = receipt_count + 1, updated_at = ? WHERE id = ?",
                (_now_iso(), order_id),
            )

    def _set_flags(
        self,
        order_id: str,
        *,
        refunded: Optional[bool] = None,
        ambiguous: Optional[bool] = None,
        reconciled: Optional[bool] = None,
    ) -> Order:
        """Actualiza flags de la orden (reembolso / reconciliación)."""
        sets: list[str] = []
        params: list[Any] = []
        if refunded is not None:
            sets.append("refunded = ?")
            params.append(int(refunded))
        if ambiguous is not None:
            sets.append("ambiguous = ?")
            params.append(int(ambiguous))
        if reconciled is not None:
            sets.append("reconciled = ?")
            params.append(int(reconciled))
        if not sets:
            order = self.get_order(order_id)
            if order is None:
                raise OrderNotFound(order_id)
            return order
        sets.append("updated_at = ?")
        params.append(_now_iso())
        params.append(order_id)
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                f"UPDATE orders SET {', '.join(sets)} WHERE id = ?", params
            )
            if cur.rowcount == 0:
                raise OrderNotFound(order_id)
        return self.get_order(order_id)  # type: ignore[return-value]

    def mark_refunded(self, order_id: str, refunded: bool = True) -> Order:
        if not refunded:
            return self._set_flags(order_id, refunded=False)
        # I-09: guarda atómica — solo marca como reembolsada si aún no lo estaba.
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE orders SET refunded = 1, updated_at = ? WHERE id = ? AND refunded = 0",
                (_now_iso(), order_id),
            )
            if cur.rowcount == 0:
                raise InvalidTransition("La orden ya fue reembolsada")
        return self.get_order(order_id)  # type: ignore[return-value]

    def mark_ambiguous(self, order_id: str, ambiguous: bool = True) -> Order:
        return self._set_flags(order_id, ambiguous=ambiguous)

    def mark_reconciled(self, order_id: str, reconciled: bool = True) -> Order:
        return self._set_flags(order_id, reconciled=reconciled)

    # ---------------------------------------------------------- transactions
    def add_transaction(self, tx: Transaction) -> Transaction:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO transactions (order_id, code, message, terminal_id, commerce_code,"
                " authorization_code, amount, real_date, accounting_date, operation_mode,"
                " sale_type, raw, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    tx.order_id,
                    tx.code,
                    tx.message,
                    tx.terminal_id,
                    tx.commerce_code,
                    tx.authorization_code,
                    tx.amount,
                    tx.real_date,
                    tx.accounting_date,
                    tx.operation_mode,
                    tx.sale_type,
                    tx.raw,
                    tx.created_at or _now_iso(),
                ),
            )
            tx.id = cur.lastrowid
        return tx

    def get_transactions(self, order_id: str) -> list[Transaction]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM transactions WHERE order_id = ? ORDER BY id ASC",
                (order_id,),
            ).fetchall()
        return [
            Transaction(
                id=r["id"],
                order_id=r["order_id"],
                code=r["code"],
                message=r["message"] or "",
                terminal_id=r["terminal_id"] or "",
                commerce_code=r["commerce_code"] or "",
                authorization_code=r["authorization_code"] or "",
                amount=r["amount"] or 0,
                real_date=r["real_date"] or "",
                accounting_date=r["accounting_date"] or "",
                operation_mode=r["operation_mode"] or "",
                sale_type=r["sale_type"] or "",
                raw=r["raw"] or "",
                created_at=r["created_at"] or "",
            )
            for r in rows
        ]

    def get_last_transaction(self, order_id: str) -> Optional[Transaction]:
        txs = self.get_transactions(order_id)
        return txs[-1] if txs else None
