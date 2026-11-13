/**
 * app.js — Orquestador principal
 *
 * Patrón: IIFE (Inmediatly Invoked Function Expression).
 * Inicializa la aplicación, vincula los event listeners mediante
 * delegación de eventos, y coordina Cart (estado) con UI (renderizado).
 *
 * Dependencias (cargadas en orden):
 *   1. data.js — PRODUCTOS (catálogo)
 *   2. cart.js — Cart (gestión del carrito)
 *   3. ui.js — UI (renderizado DOM)
 *   4. app.js — Este archivo (orquestador)
 */

(function () {
  'use strict';

  /* ------------------------------------------------------------------ */
  /*  Inicialización                                                     */
  /* ------------------------------------------------------------------ */

  /**
   * Renderiza toda la interfaz desde cero.
   * Se llama al inicio y cada vez que cambia el estado del carrito.
   */
  function renderizarTodo() {
    UI.renderizarGrilla('grilla-productos');
    UI.renderizarCarrito('lista-carrito');
  }

  /* ------------------------------------------------------------------ */
  /*  Manejadores de eventos                                             */
  /* ------------------------------------------------------------------ */

  /**
   * Obtiene el ID del producto desde un elemento o su ancestro.
   *
   * @param {HTMLElement} el — Elemento desde el cual buscar.
   * @returns {number|null} — ID del producto o null si no se encuentra.
   */
  function obtenerProductoId(el) {
    var target = el.closest('[data-producto-id]');
    if (!target) return null;
    var id = parseInt(target.getAttribute('data-producto-id'), 10);
    return isNaN(id) ? null : id;
  }

  /**
   * Maneja los clics en la grilla de productos.
   * - "Agregar al carrito" → Cart.agregar() → re-render.
   * - "+" (btn-sumar) en control de cantidad → Cart.agregar() → re-render.
   * - "−" (btn-restar) en control de cantidad → Cart.quitar() → re-render.
   *
   * @param {MouseEvent} evento — Evento de clic.
   */
  function manejadorGrilla(evento) {
    var target = evento.target;
    var btnAgregar = target.closest('.btn-agregar');
    var btnSumar = target.closest('.btn-sumar');
    var btnRestar = target.closest('.btn-restar');

    // Botón "Agregar al carrito"
    if (btnAgregar) {
      evento.preventDefault();
      var productoId = obtenerProductoId(btnAgregar);
      if (productoId !== null) {
        Cart.agregar(productoId);
        renderizarTodo();
      }
      return;
    }

    // Botón "+" (sumar)
    if (btnSumar) {
      evento.preventDefault();
      if (btnSumar.disabled) return;
      var productoIdSumar = obtenerProductoId(btnSumar);
      if (productoIdSumar !== null) {
        Cart.agregar(productoIdSumar);
        renderizarTodo();
      }
      return;
    }

    // Botón "−" (restar)
    if (btnRestar) {
      evento.preventDefault();
      var productoIdRestar = obtenerProductoId(btnRestar);
      if (productoIdRestar !== null) {
        Cart.quitar(productoIdRestar);
        renderizarTodo();
      }
      return;
    }

    // Clic en cualquier parte de la tarjeta del producto (imagen, nombre, descripción, etc.)
    // Si el producto NO está en el carrito, lo agrega automáticamente.
    var tarjeta = target.closest('.tarjeta-producto');
    if (tarjeta) {
      evento.preventDefault();
      var productoTarjetaId = obtenerProductoId(tarjeta);
      if (productoTarjetaId !== null && Cart.obtenerCantidad(productoTarjetaId) === 0) {
        Cart.agregar(productoTarjetaId);
        renderizarTodo();
      }
      return;
    }
  }

  /**
   * Maneja los clics en el panel del carrito.
   * - "+" (btn-sumar) → Cart.agregar() → re-render.
   * - "−" (btn-restar) → Cart.quitar() → re-render.
   * - "×" (btn-eliminar) → Cart.eliminar() → re-render.
   *
   * @param {MouseEvent} evento — Evento de clic.
   */
  function manejadorCarrito(evento) {
    var target = evento.target;
    var btnSumar = target.closest('.btn-sumar');
    var btnRestar = target.closest('.btn-restar');
    var btnEliminar = target.closest('.btn-eliminar');

    // Botón "+" (sumar)
    if (btnSumar) {
      evento.preventDefault();
      if (btnSumar.disabled) return;
      var productoIdSumar = obtenerProductoId(btnSumar);
      if (productoIdSumar !== null) {
        Cart.agregar(productoIdSumar);
        renderizarTodo();
      }
      return;
    }

    // Botón "−" (restar)
    if (btnRestar) {
      evento.preventDefault();
      var productoIdRestar = obtenerProductoId(btnRestar);
      if (productoIdRestar !== null) {
        Cart.quitar(productoIdRestar);
        renderizarTodo();
      }
      return;
    }

    // Botón eliminar (×)
    if (btnEliminar) {
      evento.preventDefault();
      var productoIdEliminar = obtenerProductoId(btnEliminar);
      if (productoIdEliminar !== null) {
        Cart.eliminar(productoIdEliminar);
        renderizarTodo();
      }
      return;
    }
  }

  /**
   * Maneja el clic en el botón "Limpiar carrito".
   */
  function manejadorLimpiar() {
    if (Cart.estaVacio()) {
      // Opcional: mostrar toast "El carrito ya está vacío"
      UI.mostrarToast('El carrito ya está vacío', 'info');
      return;
    }

    Cart.limpiar();
    renderizarTodo();
    UI.mostrarToast('Carrito vaciado', 'exito');
  }

  /**
   * Maneja el clic en el botón "Confirmar compra".
   * Abre el modal de resumen si el carrito no está vacío.
   */
  function manejadorConfirmarCompra() {
    if (Cart.estaVacio()) {
      UI.aplicarShake('btn-confirmar');
      return;
    }

    UI.mostrarModalResumen();
  }

  /**
   * Maneja el clic en el botón "Confirmar" del modal.
   * Finaliza la compra: animación de éxito, limpia carrito, cierra modal.
   */
  function manejadorModalConfirmar() {
    UI.cerrarModal();

    UI.mostrarAnimacionExito(function () {
      Cart.limpiar();
      renderizarTodo();
      UI.mostrarToast('¡Compra confirmada! Gracias por tu pedido.', 'exito');
    });
  }

  /**
   * Maneja el clic en el botón "Cancelar" del modal.
   */
  function manejadorModalCancelar() {
    UI.cerrarModal();
  }

  /**
   * Maneja el clic en el backdrop del modal (fuera del contenido).
   *
   * @param {MouseEvent} evento — Evento de clic.
   */
  function manejadorModalBackdrop(evento) {
    if (evento.target === document.getElementById('modal-overlay')) {
      UI.cerrarModal();
    }
  }

  /* ------------------------------------------------------------------ */
  /*  Vinculación de event listeners                                     */
  /* ------------------------------------------------------------------ */

  /**
   * Inicializa la aplicación: renderiza la UI y vincula los eventos.
   */
  function init() {
    // Renderizado inicial
    renderizarTodo();

    // Delegación de eventos en la grilla de productos
    var grilla = document.getElementById('grilla-productos');
    if (grilla) {
      grilla.addEventListener('click', manejadorGrilla);
    }

    // Delegación de eventos en la lista del carrito
    var listaCarrito = document.getElementById('lista-carrito');
    if (listaCarrito) {
      listaCarrito.addEventListener('click', manejadorCarrito);
    }

    // Botón Limpiar carrito
    var btnLimpiar = document.getElementById('btn-limpiar');
    if (btnLimpiar) {
      btnLimpiar.addEventListener('click', manejadorLimpiar);
    }

    // Botón Confirmar compra
    var btnConfirmar = document.getElementById('btn-confirmar');
    if (btnConfirmar) {
      btnConfirmar.addEventListener('click', manejadorConfirmarCompra);
    }

    // Modal: botón Confirmar
    var modalBtnConfirmar = document.getElementById('modal-btn-confirmar');
    if (modalBtnConfirmar) {
      modalBtnConfirmar.addEventListener('click', manejadorModalConfirmar);
    }

    // Modal: botón Cancelar
    var modalBtnCancelar = document.getElementById('modal-btn-cancelar');
    if (modalBtnCancelar) {
      modalBtnCancelar.addEventListener('click', manejadorModalCancelar);
    }

    // Modal: clic en backdrop
    var modalOverlay = document.getElementById('modal-overlay');
    if (modalOverlay) {
      modalOverlay.addEventListener('click', manejadorModalBackdrop);
    }
  }

  // Iniciar la aplicación cuando el DOM esté listo
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
