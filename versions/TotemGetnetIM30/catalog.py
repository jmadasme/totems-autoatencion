"""Catálogo demo del tótem (bebidas y snacks, precios en CLP).

Los precios son enteros en pesos chilenos (CLP no tiene decimales).
`Amount` que se envía a Getnet = precio en pesos (1 unidad menor = 1 CLP).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable, Optional

CURRENCY = "CLP"

CATEGORIES = [
    {"id": "bebidas", "name": "Bebidas", "icon": "🥤"},
    {"id": "snacks", "name": "Snacks", "icon": "🍫"},
]


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    category: str
    price: int  # CLP entero
    icon: str = "🛒"
    image: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


PRODUCTS: list[Product] = [
    # --- Bebidas ---
    Product("beb-agua", "Agua Mineral 500ml", "bebidas", 1200, "💧"),
    Product("beb-coca", "Coca-Cola 350ml", "bebidas", 1500, "🥤"),
    Product("beb-juice", "Jugo Natural 300ml", "bebidas", 1800, "🧃"),
    Product("beb-cafe", "Café Americano", "bebidas", 2000, "☕"),
    Product("beb-te", "Té Helado 400ml", "bebidas", 1600, "🧋"),
    Product("beb-energy", "Bebida Energética", "bebidas", 2500, "⚡"),
    # --- Snacks ---
    Product("snk-papas", "Papas Fritas", "snacks", 1700, "🍟"),
    Product("snk-choco", "Chocolate", "snacks", 1300, "🍫"),
    Product("snk-galleta", "Galletas", "snacks", 1100, "🍪"),
    Product("snk-mani", "Maní Salado", "snacks", 900, "🥜"),
    Product("snk-bar", "Barra de Cereal", "snacks", 1000, "🍬"),
    Product("snk-sandwich", "Sándwich", "snacks", 3200, "🥪"),
]

_PRODUCTS_BY_ID = {p.id: p for p in PRODUCTS}


def get_categories() -> list[dict]:
    return list(CATEGORIES)


def get_products(category: Optional[str] = None) -> list[Product]:
    if category:
        return [p for p in PRODUCTS if p.category == category]
    return list(PRODUCTS)


def get_product(product_id: str) -> Optional[Product]:
    return _PRODUCTS_BY_ID.get(product_id)


def get_catalog() -> dict:
    return {
        "currency": CURRENCY,
        "categories": get_categories(),
        "products": [p.to_dict() for p in PRODUCTS],
    }


def build_line_items(items: Iterable[dict]) -> list[dict]:
    """Convierte [{product_id, qty}] en líneas con precio server-side.

    Lanza ValueError si el producto no existe o la cantidad es inválida.
    """
    lines: list[dict] = []
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError("Item inválido")
        pid = str(raw.get("product_id") or raw.get("id") or "").strip()
        try:
            qty = int(raw.get("qty", raw.get("quantity", 1)))
        except (TypeError, ValueError):
            raise ValueError(f"Cantidad inválida para '{pid}'")
        if qty < 1 or qty > 99:
            raise ValueError(f"Cantidad fuera de rango para '{pid}' (1-99)")
        product = get_product(pid)
        if product is None:
            raise ValueError(f"Producto desconocido: '{pid}'")
        lines.append(
            {
                "product_id": product.id,
                "name": product.name,
                "category": product.category,
                "unit_price": product.price,
                "qty": qty,
                "subtotal": product.price * qty,
                "icon": product.icon,
            }
        )
    if not lines:
        raise ValueError("El carrito está vacío")
    return lines


def compute_total(lines: Iterable[dict]) -> int:
    return int(sum(int(li["subtotal"]) for li in lines))
