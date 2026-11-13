/**
 * cart.js — Módulo de gestión del carrito de compras
 *
 * Patrón: Módulo revelador (IIFE) para encapsulamiento.
 * Mantiene el estado del carrito como un Map<number, number> (productId → quantity).
 * Expone una API pública para manipular y consultar el carrito.
 * Depende de la variable global PRODUCTOS (definida en data.js) para calcular subtotales.
 *
 * @module Cart
 * @global {Object} Cart — API pública del módulo.
 */

const Cart = (function () {
  'use strict';

  /** @const {number} Cantidad máxima de unidades por producto */
  const MAX_CANTIDAD = 99;

  /** @const {number} Cantidad mínima (menos de 1 elimina el ítem) */
  const MIN_CANTIDAD = 1;

  /**
   * Estado privado del carrito.
   * Map<number, number> — clave: productId, valor: cantidad.
   * @private
   */
  let items = new Map();

  /**
   * Busca un producto por su ID en el catálogo global.
   * @param {number} productId — ID del producto.
   * @returns {Object|undefined} — El producto encontrado o undefined.
   */
  function _buscarProducto(productId) {
    return PRODUCTOS.find(function (p) { return p.id === productId; });
  }

  /**
   * Agrega una unidad al carrito.
   * - Si el producto no existe, lo añade con cantidad = 1.
   * - Si ya existe, incrementa la cantidad (sin superar MAX_CANTIDAD).
   * - Si se alcanza MAX_CANTIDAD, no hace nada (el botón + se deshabilita en UI).
   *
   * @param {number} productId — ID del producto a agregar.
   * @returns {boolean} — true si se agregó/incrementó, false si no (límite alcanzado).
   */
  function agregar(productId) {
    if (!_buscarProducto(productId)) return false;

    var cantidadActual = items.get(productId) || 0;
    if (cantidadActual >= MAX_CANTIDAD) return false;

    items.set(productId, cantidadActual + 1);
    return true;
  }

  /**
   * Quita una unidad del carrito.
   * - Decrementa la cantidad en 1.
   * - Si la cantidad llega a 0, elimina el producto del carrito.
   * - Si el producto no existe en el carrito, no hace nada.
   *
   * @param {number} productId — ID del producto a quitar.
   * @returns {boolean} — true si se quitó/decrementó, false si no existía.
   */
  function quitar(productId) {
    if (!items.has(productId)) return false;

    var cantidadActual = items.get(productId);
    if (cantidadActual <= 1) {
      items.delete(productId);
    } else {
      items.set(productId, cantidadActual - 1);
    }
    return true;
  }

  /**
   * Elimina completamente un producto del carrito.
   *
   * @param {number} productId — ID del producto a eliminar.
   * @returns {boolean} — true si se eliminó, false si no existía.
   */
  function eliminar(productId) {
    return items.delete(productId);
  }

  /**
   * Vacía completamente el carrito.
   */
  function limpiar() {
    items.clear();
  }

  /**
   * Obtiene una copia de los ítems del carrito como array de objetos.
   *
   * @returns {Array<{productId: number, quantity: number}>}
   */
  function obtenerItems() {
    var resultado = [];
    items.forEach(function (cantidad, productId) {
      resultado.push({ productId: productId, quantity: cantidad });
    });
    return resultado;
  }

  /**
   * Obtiene la cantidad de un producto específico en el carrito.
   *
   * @param {number} productId — ID del producto.
   * @returns {number} — Cantidad actual (0 si no está en el carrito).
   */
  function obtenerCantidad(productId) {
    return items.get(productId) || 0;
  }

  /**
   * Calcula el número total de ítems (suma de todas las cantidades).
   *
   * @returns {number} — Total de unidades en el carrito.
   */
  function obtenerTotalItems() {
    var total = 0;
    items.forEach(function (cantidad) {
      total += cantidad;
    });
    return total;
  }

  /**
   * Calcula el subtotal de un producto específico (precio × cantidad).
   *
   * @param {number} productId — ID del producto.
   * @returns {number} — Subtotal en CLP. 0 si el producto no está en el carrito.
   */
  function obtenerSubtotal(productId) {
    var producto = _buscarProducto(productId);
    var cantidad = items.get(productId) || 0;
    if (!producto || cantidad === 0) return 0;
    return producto.precio * cantidad;
  }

  /**
   * Calcula el total general del carrito (suma de todos los subtotales).
   *
   * @returns {number} — Total general en CLP.
   */
  function obtenerTotalGeneral() {
    var total = 0;
    items.forEach(function (cantidad, productId) {
      var producto = _buscarProducto(productId);
      if (producto) {
        total += producto.precio * cantidad;
      }
    });
    return total;
  }

  /**
   * Verifica si el carrito está vacío.
   *
   * @returns {boolean} — true si no hay productos en el carrito.
   */
  function estaVacio() {
    return items.size === 0;
  }

  /**
   * Obtiene el límite máximo de cantidad por producto.
   *
   * @returns {number} — Cantidad máxima permitida.
   */
  function obtenerMaxCantidad() {
    return MAX_CANTIDAD;
  }

  // API pública
  return {
    agregar: agregar,
    quitar: quitar,
    eliminar: eliminar,
    limpiar: limpiar,
    obtenerItems: obtenerItems,
    obtenerCantidad: obtenerCantidad,
    obtenerTotalItems: obtenerTotalItems,
    obtenerSubtotal: obtenerSubtotal,
    obtenerTotalGeneral: obtenerTotalGeneral,
    estaVacio: estaVacio,
    obtenerMaxCantidad: obtenerMaxCantidad
  };
})();
