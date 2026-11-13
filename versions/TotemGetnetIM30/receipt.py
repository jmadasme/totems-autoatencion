"""Comprobante digital: vista HTML (Jinja2) y exportación PDF (reportlab).

No se usa impresora térmica. El comprobante es digital (pantalla + PDF) y puede
re-emitirse de forma idempotente desde el historial.
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Optional

from jinja2 import Environment, BaseLoader, select_autoescape
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from orders import Order, Transaction


def format_clp(amount: int) -> str:
    return "$" + f"{int(amount):,}".replace(",", ".")


_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Comprobante {{ order.id }}</title>
</head>
<body style="font-family: system-ui, sans-serif; max-width: 420px; margin: 0 auto;">
  <div class="receipt">
    <h1 style="text-align:center;margin-bottom:0;">Tótem Getnet</h1>
    <p style="text-align:center;color:#666;margin-top:4px;">Comprobante de pago</p>
    <hr>
    <table style="width:100%;font-size:14px;">
      <tr><td>Folio</td><td style="text-align:right;"><b>{{ order.id }}</b></td></tr>
      <tr><td>Estado</td><td style="text-align:right;">{{ order.status | upper }}</td></tr>
      <tr><td>Fecha</td><td style="text-align:right;">{{ tx.real_date or order.updated_at }}</td></tr>
      <tr><td>Terminal</td><td style="text-align:right;">{{ tx.terminal_id or '-' }}</td></tr>
      <tr><td>Comercio</td><td style="text-align:right;">{{ tx.commerce_code or '-' }}</td></tr>
      <tr><td>Autorización</td><td style="text-align:right;"><b>{{ tx.authorization_code or '-' }}</b></td></tr>
      <tr><td>Código respuesta</td><td style="text-align:right;">{{ tx.code }} {{ tx.message }}</td></tr>
    </table>
    <hr>
    <table style="width:100%;font-size:14px;">
      <thead>
        <tr style="border-bottom:1px solid #ccc;">
          <th style="text-align:left;">Producto</th>
          <th style="text-align:center;">Cant.</th>
          <th style="text-align:right;">P. Unit</th>
          <th style="text-align:right;">Subtotal</th>
        </tr>
      </thead>
      <tbody>
        {% for it in order.items %}
        <tr>
          <td>{{ it.name }}</td>
          <td style="text-align:center;">{{ it.qty }}</td>
          <td style="text-align:right;">{{ it.unit_price | clp }}</td>
          <td style="text-align:right;">{{ it.subtotal | clp }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    <hr>
    <h2 style="text-align:right;">TOTAL: {{ order.total | clp }} {{ order.currency }}</h2>
    <p style="text-align:center;color:#666;font-size:12px;">
      {{ tx.operation_mode or 'Integrated POS' }} · {{ tx.sale_type or 'Card' }}<br>
      Reemisión #{{ order.receipt_count }}
    </p>
  </div>
</body>
</html>
"""


def _env() -> Environment:
    env = Environment(
        loader=BaseLoader(),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.filters["clp"] = format_clp
    return env


def render_html(
    order: Order, transaction: Optional[Transaction] = None
) -> str:
    tx = transaction or Transaction(order_id=order.id)
    template = _env().from_string(_TEMPLATE)
    return template.render(order=order, tx=tx)


def _styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ReceiptTitle",
            parent=styles["Title"],
            fontSize=16,
            spaceAfter=2,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Small",
            parent=styles["Normal"],
            fontSize=8,
            textColor=colors.grey,
        )
    )
    return styles


def generate_pdf(
    order: Order,
    transaction: Optional[Transaction] = None,
    output_path: Optional[str] = None,
) -> bytes:
    """Genera el PDF del comprobante. Devuelve los bytes y opcionalmente lo guarda."""
    tx = transaction or Transaction(order_id=order.id)
    styles = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"Comprobante {order.id}",
    )

    story: list[Any] = []
    story.append(Paragraph("Tótem Getnet — Comprobante de pago", styles["ReceiptTitle"]))
    story.append(
        Paragraph(
            f"Folio: <b>{order.id}</b> &nbsp;|&nbsp; Estado: {order.status.upper()}",
            styles["Normal"],
        )
    )
    story.append(
        Paragraph(
            f"Fecha: {tx.real_date or order.updated_at} &nbsp;|&nbsp; "
            f"Terminal: {tx.terminal_id or '-'} &nbsp;|&nbsp; "
            f"Comercio: {tx.commerce_code or '-'}",
            styles["Normal"],
        )
    )
    story.append(
        Paragraph(
            f"Autorización: <b>{tx.authorization_code or '-'}</b> &nbsp;|&nbsp; "
            f"Respuesta: {tx.code} {tx.message}",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 6 * mm))

    rows = [["Producto", "Cant.", "P. Unit", "Subtotal"]]
    for it in order.items:
        rows.append(
            [
                str(it.get("name", "")),
                str(it.get("qty", "")),
                format_clp(int(it.get("unit_price", 0))),
                format_clp(int(it.get("subtotal", 0))),
            ]
        )
    rows.append(["", "", "TOTAL", format_clp(order.total)])

    table = Table(rows, colWidths=[80 * mm, 20 * mm, 30 * mm, 30 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#222222")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("ALIGN", (1, 1), (1, -2), "CENTER"),
                ("GRID", (0, 0), (-1, -2), 0.25, colors.HexColor("#cccccc")),
                ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 6 * mm))
    story.append(
        Paragraph(
            f"{tx.operation_mode or 'Integrated POS'} · {tx.sale_type or 'Card'} · "
            f"Reemisión #{order.receipt_count}",
            styles["Small"],
        )
    )

    doc.build(story)
    data = buf.getvalue()
    buf.close()

    if output_path:
        with open(output_path, "wb") as fh:
            fh.write(data)
    return data


def receipt_context(
    order: Order, transaction: Optional[Transaction] = None
) -> dict:
    tx = transaction or Transaction(order_id=order.id)
    return {
        "order": order.to_dict(),
        "transaction": tx.to_dict(),
        "total_formatted": format_clp(order.total),
        "items": [
            {**it, "unit_price_formatted": format_clp(int(it.get("unit_price", 0)))}
            for it in order.items
        ],
    }
