"""Pruebas del comprobante digital (HTML + PDF)."""
from __future__ import annotations

from orders import Order, Transaction
from receipt import format_clp, generate_pdf, receipt_context, render_html

ITEMS = [
    {"product_id": "beb-cafe", "name": "Café Americano", "unit_price": 2000, "qty": 2, "subtotal": 4000},
    {"product_id": "snk-papas", "name": "Papas Fritas", "unit_price": 1700, "qty": 1, "subtotal": 1700},
]


def _order():
    return Order(
        id="ABC123",
        status="paid",
        total=5700,
        currency="CLP",
        items=ITEMS,
        created_at="2026-09-14T10:00:00-03:00",
        updated_at="2026-09-14T10:01:00-03:00",
        receipt_count=1,
    )


def _tx():
    return Transaction(
        order_id="ABC123",
        code=0,
        message="APPROVED",
        terminal_id="SIM-IM30-01",
        commerce_code="DEMO0001",
        authorization_code="AUTH123456",
        amount=5700,
        real_date="2026-09-14T10:01:00-03:00",
        operation_mode="Integrated",
        sale_type="Card",
    )


def test_format_clp():
    assert format_clp(5700) == "$5.700"
    assert format_clp(1000000) == "$1.000.000"


def test_render_html_contains_fields():
    html = render_html(_order(), _tx())
    assert "ABC123" in html
    assert "AUTH123456" in html
    assert "Café Americano" in html
    assert "$5.700" in html
    assert "TOTAL" in html


def test_generate_pdf_bytes():
    pdf = generate_pdf(_order(), _tx())
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 500


def test_generate_pdf_to_file(tmp_path):
    out = tmp_path / "comprobante.pdf"
    generate_pdf(_order(), _tx(), output_path=str(out))
    assert out.exists()
    assert out.read_bytes().startswith(b"%PDF")


def test_receipt_context():
    ctx = receipt_context(_order(), _tx())
    assert ctx["total_formatted"] == "$5.700"
    assert ctx["items"][0]["unit_price_formatted"] == "$2.000"
