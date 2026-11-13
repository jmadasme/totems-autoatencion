/* Tótem Getnet IM30 — lógica de UI (sin build, vanilla JS). */
"use strict";

const API = "";

const state = {
  catalog: { categories: [], products: [], currency: "CLP" },
  cart: new Map(), // product_id -> qty
  activeCategory: null,
  order: null,
  polling: null,
  idleTimer: null,
  idleTimeout: 60,
  config: {},
};

const $ = (sel) => document.querySelector(sel);

/* ------------------------------------------------------------------ utils */
function formatCLP(amount) {
  return "$" + Number(amount || 0).toLocaleString("es-CL");
}

function showScreen(id) {
  document.querySelectorAll(".screen").forEach((el) => el.classList.remove("active"));
  const el = document.getElementById(id);
  if (el) el.classList.add("active");
}

function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add("hidden"), 3500);
}

async function api(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch (_) {}
    throw new Error(detail);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

/* ------------------------------------------------------------------ clock */
function tickClock() {
  const d = new Date();
  $("#clock").textContent = d.toLocaleTimeString("es-CL", {
    hour: "2-digit",
    minute: "2-digit",
  });
}
setInterval(tickClock, 1000);
tickClock();

/* ------------------------------------------------------------------ idle */
function resetIdle() {
  clearTimeout(state.idleTimer);
  state.idleTimer = setTimeout(onIdle, state.idleTimeout * 1000);
}

function onIdle() {
  if (state.order && state.order.status === "charging") return;
  clearCart();
  goAttractor();
}

["pointerdown", "keydown", "touchstart"].forEach((ev) =>
  document.addEventListener(ev, resetIdle, { passive: true })
);

function goAttractor() {
  showScreen("screen-attractor");
  resetIdle();
}

/* ------------------------------------------------------------------ cart */
function clearCart() {
  state.cart.clear();
  renderCart();
}

function addToCart(productId) {
  const qty = state.cart.get(productId) || 0;
  if (qty >= 99) return toast("Cantidad máxima alcanzada");
  state.cart.set(productId, qty + 1);
  renderCart();
}

function changeQty(productId, delta) {
  const qty = (state.cart.get(productId) || 0) + delta;
  if (qty <= 0) state.cart.delete(productId);
  else state.cart.set(productId, Math.min(qty, 99));
  renderCart();
}

function cartLines() {
  const lines = [];
  for (const [pid, qty] of state.cart.entries()) {
    const p = state.catalog.products.find((x) => x.id === pid);
    if (!p) continue;
    lines.push({ product: p, qty, subtotal: p.price * qty });
  }
  return lines;
}

function cartTotal() {
  return cartLines().reduce((acc, l) => acc + l.subtotal, 0);
}

function renderCart() {
  const box = $("#cart-items");
  const lines = cartLines();
  if (!lines.length) {
    box.innerHTML = '<p class="muted">Carrito vacío</p>';
  } else {
    box.innerHTML = lines
      .map(
        (l) => `
      <div class="cart-row">
        <div>
          <div class="name">${l.product.icon} ${l.product.name}</div>
          <div class="price">${formatCLP(l.product.price)} c/u</div>
        </div>
        <div class="qty-controls">
          <button data-minus="${l.product.id}">−</button>
          <span>${l.qty}</span>
          <button data-plus="${l.product.id}">+</button>
        </div>
        <div class="price">${formatCLP(l.subtotal)}</div>
      </div>`
      )
      .join("");
    box.querySelectorAll("[data-plus]").forEach((b) =>
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        addToCart(b.dataset.plus);
      })
    );
    box.querySelectorAll("[data-minus]").forEach((b) =>
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        changeQty(b.dataset.minus, -1);
      })
    );
  }
  $("#cart-total").textContent = formatCLP(cartTotal());
  $("#btn-pay").disabled = lines.length === 0;
}

/* ------------------------------------------------------------------ catálogo */
function renderCategories() {
  const tabs = $("#category-tabs");
  tabs.innerHTML = state.catalog.categories
    .map(
      (c) =>
        `<button data-cat="${c.id}" class="${
          c.id === state.activeCategory ? "active" : ""
        }">${c.icon} ${c.name}</button>`
    )
    .join("");
  tabs.querySelectorAll("[data-cat]").forEach((b) =>
    b.addEventListener("click", () => {
      state.activeCategory = b.dataset.cat;
      renderCategories();
      renderProducts();
    })
  );
}

function renderProducts() {
  const grid = $("#product-grid");
  const products = state.catalog.products.filter(
    (p) => !state.activeCategory || p.category === state.activeCategory
  );
  grid.innerHTML = products
    .map(
      (p) => `
    <div class="product-card" data-id="${p.id}">
      <div class="product-icon">${p.icon}</div>
      <div class="product-name">${p.name}</div>
      <div class="product-price">${formatCLP(p.price)}</div>
    </div>`
    )
    .join("");
  grid.querySelectorAll(".product-card").forEach((card) =>
    card.addEventListener("click", () => addToCart(card.dataset.id))
  );
}

/* ------------------------------------------------------------------ pago */
async function checkout() {
  const lines = cartLines();
  if (!lines.length) return;
  $("#btn-pay").disabled = true;
  try {
    const order = await api("/api/orders", {
      method: "POST",
      body: JSON.stringify({
        items: lines.map((l) => ({ product_id: l.product.id, qty: l.qty })),
      }),
    });
    state.order = order;
    $("#payment-amount").textContent = formatCLP(order.total);
    showScreen("screen-payment");
    resetIdle();

    await api(`/api/orders/${order.id}/pay`, { method: "POST", body: "{}" });
    startPolling(order.id);
  } catch (err) {
    $("#btn-pay").disabled = false;
    toast("No se pudo iniciar el pago: " + err.message);
    showScreen("screen-catalog");
  }
}

function startPolling(orderId) {
  clearInterval(state.polling);
  state.polling = setInterval(() => pollStatus(orderId), 1000);
  pollStatus(orderId);
}

async function pollStatus(orderId) {
  try {
    const data = await api(`/api/orders/${orderId}/status`);
    const order = data.order;
    state.order = order;
    if (order.status !== "charging") {
      clearInterval(state.polling);
      state.polling = null;
      handleResult(order, data.transaction);
    }
  } catch (err) {
    console.error("poll error", err);
  }
}

async function cancelPayment() {
  if (!state.order) return;
  clearInterval(state.polling);
  state.polling = null;
  try {
    const order = await api(`/api/orders/${state.order.id}/cancel`, { method: "POST" });
    state.order = order;
    handleResult(order, null);
  } catch (err) {
    toast("Error al cancelar: " + err.message);
  }
}

function handleResult(order, tx) {
  resetIdle();
  const icon = $("#result-icon");
  const title = $("#result-title");
  const msg = $("#result-message");
  const btnReceipt = $("#btn-receipt");
  const btnRetry = $("#btn-retry");

  btnReceipt.classList.add("hidden");
  btnRetry.classList.add("hidden");

  switch (order.status) {
    case "paid":
    case "emitted":
      icon.textContent = "✅";
      title.textContent = "Pago aprobado";
      msg.textContent =
        "Autorización: " + (tx && tx.authorization_code ? tx.authorization_code : "—");
      btnReceipt.classList.remove("hidden");
      break;
    case "failed":
      icon.textContent = "❌";
      title.textContent = "Pago rechazado";
      msg.textContent = order.error || "La transacción fue rechazada.";
      btnRetry.classList.remove("hidden");
      break;
    case "timeout":
      icon.textContent = "⏱️";
      title.textContent = "Tiempo agotado";
      msg.textContent = order.error || "No se detectó la tarjeta a tiempo.";
      btnRetry.classList.remove("hidden");
      break;
    case "cancelled":
      icon.textContent = "🚫";
      title.textContent = "Pago cancelado";
      msg.textContent = "La operación fue cancelada.";
      btnRetry.classList.remove("hidden");
      break;
    default:
      icon.textContent = "⚠️";
      title.textContent = "Error de pago";
      msg.textContent = order.error || "Ocurrió un error inesperado.";
      btnRetry.classList.remove("hidden");
  }
  showScreen("screen-result");
}

async function retryPayment() {
  if (!state.order) return goAttractor();
  try {
    $("#payment-amount").textContent = formatCLP(state.order.total);
    showScreen("screen-payment");
    resetIdle();
    await api(`/api/orders/${state.order.id}/pay`, { method: "POST", body: "{}" });
    startPolling(state.order.id);
  } catch (err) {
    toast("No se pudo reintentar: " + err.message);
    showScreen("screen-result");
  }
}

/* ------------------------------------------------------------------ comprobante */
function showReceipt(orderId) {
  $("#receipt-frame").src = `/api/orders/${orderId}/receipt`;
  showScreen("screen-receipt");
  resetIdle();
}

/* ------------------------------------------------------------------ historial */
async function showHistory() {
  try {
    const data = await api("/api/orders?limit=50");
    const box = $("#history-list");
    if (!data.orders.length) {
      box.innerHTML = '<p class="muted">Sin ventas registradas</p>';
    } else {
      box.innerHTML = data.orders
        .map(
          (o) => `
        <div class="history-row" data-id="${o.id}">
          <span class="folio">#${o.id}</span>
          <span>${formatCLP(o.total)}</span>
          <span class="status ${o.status}">${o.status}</span>
          <span class="muted">${new Date(o.created_at).toLocaleString("es-CL")}</span>
        </div>`
        )
        .join("");
      box.querySelectorAll(".history-row").forEach((row) =>
        row.addEventListener("click", () => showReceipt(row.dataset.id))
      );
    }
    showScreen("screen-history");
    resetIdle();
  } catch (err) {
    toast("No se pudo cargar el historial: " + err.message);
  }
}

/* ------------------------------------------------------------------ init */
async function loadTerminalStatus() {
  try {
    const status = await api("/api/terminal/status");
    const badge = $("#mode-badge");
    const connected = status.polling && status.polling.connected;
    badge.textContent = `${status.mode} · ${status.connector} · ${
      connected ? "conectado" : "sin terminal"
    }`;
  } catch (_) {
    $("#mode-badge").textContent = "offline";
  }
}

async function init() {
  try {
    const cfg = await api("/api/config");
    state.config = cfg;
    state.idleTimeout = cfg.idle_timeout_seconds || 60;
  } catch (_) {}

  try {
    state.catalog = await api("/api/catalog");
    state.activeCategory = state.catalog.categories[0]?.id || null;
    renderCategories();
    renderProducts();
  } catch (err) {
    toast("No se pudo cargar el catálogo: " + err.message);
  }

  renderCart();
  loadTerminalStatus();
  setInterval(loadTerminalStatus, 15000);
  goAttractor();

  // Eventos
  $("#screen-attractor").addEventListener("click", () => {
    showScreen("screen-catalog");
    resetIdle();
  });
  $("#btn-clear").addEventListener("click", clearCart);
  $("#btn-pay").addEventListener("click", checkout);
  $("#btn-cancel").addEventListener("click", cancelPayment);
  $("#btn-receipt").addEventListener("click", () => showReceipt(state.order.id));
  $("#btn-retry").addEventListener("click", retryPayment);
  $("#btn-home").addEventListener("click", () => {
    clearCart();
    goAttractor();
  });
  $("#btn-new-sale").addEventListener("click", () => {
    clearCart();
    goAttractor();
  });
  $("#btn-download-pdf").addEventListener("click", () => {
    if (state.order) window.open(`/api/orders/${state.order.id}/receipt.pdf`, "_blank");
  });
  $("#btn-back-result").addEventListener("click", () => showScreen("screen-result"));
  $("#btn-history").addEventListener("click", showHistory);
  $("#btn-history-back").addEventListener("click", () => {
    showScreen("screen-catalog");
    resetIdle();
  });
}

document.addEventListener("DOMContentLoaded", init);
