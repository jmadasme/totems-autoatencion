/**
 * ui.js — Módulo de renderizado del DOM
 *
 * Patrón: Módulo revelador (IIFE) para encapsulamiento.
 * Contiene todas las funciones que manipulan el DOM.
 * NO modifica el estado del carrito, solo lee datos y renderiza.
 * Depende de la variable global Cart (cart.js) para obtener el estado.
 *
 * @module UI
 * @global {Object} UI — API pública del módulo.
 */

const UI = (function () {
  'use strict';

  /* ------------------------------------------------------------------ */
  /*  Constantes internas                                                */
  /* ------------------------------------------------------------------ */

  /* ------------------------------------------------------------------ */
  /*  Funciones de utilidad                                              */
  /* ------------------------------------------------------------------ */

  /**
   * Formatea un número entero (CLP) con separador de miles.
   * Ejemplo: 1500 → "$1.500"
   *
   * @param {number} precio — Precio en CLP (entero).
   * @returns {string} — Precio formateado con símbolo $ y separador de miles.
   */
  function formatearPrecio(precio) {
    if (typeof precio !== 'number') return '$0';
    return '$' + precio.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  }

  /**
   * Genera un placeholder con las iniciales del producto
   * para usar como fallback de imagen.
   *
   * @param {string} nombre — Nombre del producto.
   * @returns {string} — Iniciales (máximo 2 caracteres).
   */
  function _obtenerIniciales(nombre) {
    var palabras = nombre.split(' ');
    if (palabras.length === 1) {
      return palabras[0].substring(0, 2).toUpperCase();
    }
    return (palabras[0][0] + palabras[1][0]).toUpperCase();
  }

  /* ------------------------------------------------------------------ */
  /*  Renderizado de la grilla de productos                              */
  /* ------------------------------------------------------------------ */

  /**
   * Renderiza la grilla de productos completa en el contenedor.
   *
   * @param {string} containerId — ID del contenedor de la grilla.
   */
  function renderizarGrilla(containerId) {
    var container = document.getElementById(containerId);
    if (!container) return;

    var html = '';
    for (var i = 0; i < PRODUCTOS.length; i++) {
      var producto = PRODUCTOS[i];
      var cantidadEnCarrito = Cart.obtenerCantidad(producto.id);
      html += _renderizarTarjetaProducto(producto, cantidadEnCarrito);
    }
    container.innerHTML = html;

    // Asignar manejador de error de imagen a cada img de la grilla
    var imagenes = container.querySelectorAll('.tarjeta-imagen');
    for (var j = 0; j < imagenes.length; j++) {
      imagenes[j].addEventListener('error', function () {
        _manejarErrorImagen(this);
      });
    }
  }

  /**
   * Renderiza el HTML de una tarjeta de producto.
   *
   * @param {Object} producto — Datos del producto.
   * @param {number} cantidadEnCarrito — Cantidad actual en el carrito (0 si no está).
   * @returns {string} — HTML de la tarjeta.
   */
  function _renderizarTarjetaProducto(producto, cantidadEnCarrito) {
    var controlHtml = '';
    if (cantidadEnCarrito > 0) {
      var maxAlcanzado = cantidadEnCarrito >= Cart.obtenerMaxCantidad();
      controlHtml =
        '<div class="control-cantidad" data-producto-id="' + producto.id + '">' +
          '<button class="btn-cantidad btn-restar" type="button" aria-label="Reducir cantidad">−</button>' +
          '<span class="cantidad-valor">' + cantidadEnCarrito + '</span>' +
          '<button class="btn-cantidad btn-sumar" type="button" aria-label="Aumentar cantidad"' +
            (maxAlcanzado ? ' disabled' : '') + '>+</button>' +
        '</div>';
    } else {
      controlHtml =
        '<button class="btn-agregar" type="button" data-producto-id="' + producto.id + '" aria-label="Agregar ' + _escapeAttr(producto.nombre) + ' al carrito">' +
          '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
            '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>' +
          '</svg>' +
          'Agregar al carrito' +
        '</button>';
    }

    return (
      '<article class="tarjeta-producto" data-producto-id="' + producto.id + '">' +
        '<img class="tarjeta-imagen" src="' + producto.imagen + '" alt="' + _escapeAttr(producto.nombre) + '" loading="lazy">' +
        '<div class="tarjeta-body">' +
          '<h3 class="tarjeta-nombre">' + _escapeHtml(producto.nombre) + '</h3>' +
          '<span class="tarjeta-categoria">' + _escapeHtml(producto.categoria) + '</span>' +
          '<p class="tarjeta-descripcion">' + _escapeHtml(producto.descripcion) + '</p>' +
        '</div>' +
        '<div class="tarjeta-footer">' +
          '<span class="tarjeta-precio">' + formatearPrecio(producto.precio) + '</span>' +
          controlHtml +
        '</div>' +
      '</article>'
    );
  }

  /**
   * Escapa caracteres HTML en un string para prevenir XSS.
   *
   * @param {string} texto — Texto a escapar.
   * @returns {string} — Texto escapado.
   */
  function _escapeHtml(texto) {
    if (typeof texto !== 'string') return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(texto));
    return div.innerHTML;
  }

  /**
   * Escapa caracteres para su uso seguro dentro de atributos HTML
   * delimitados por comillas dobles (").
   * Además de &, < y >, también escapa " a &quot;.
   *
   * @param {string} texto — Texto a escapar para atributo HTML.
   * @returns {string} — Texto escapado seguro para atributos.
   */
  function _escapeAttr(texto) {
    if (typeof texto !== 'string') return '';
    return texto
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  /**
   * Manejador para cuando una imagen no carga.
   * Reemplaza el src por un placeholder con iniciales.
   *
   * @param {HTMLElement} img — El elemento img que falló.
   */
  function _manejarErrorImagen(img) {
    if (!img || img.dataset.fallback) return;
    img.dataset.fallback = 'true';

    // Intentar obtener el nombre del producto desde la tarjeta contenedora
    var tarjeta = img.closest('.tarjeta-producto, .item-carrito');
    var iniciales = '';
    if (tarjeta) {
      var nombreEl = tarjeta.querySelector('.tarjeta-nombre, .item-carrito-nombre');
      if (nombreEl) {
        iniciales = _obtenerIniciales(nombreEl.textContent);
      }
    }

    img.style.display = 'none';
    var fallback = document.createElement('div');
    fallback.className = 'tarjeta-imagen-fallback';
    fallback.textContent = iniciales || '?';
    img.parentNode.insertBefore(fallback, img.nextSibling);
  }

  /* ------------------------------------------------------------------ */
  /*  Renderizado del panel del carrito                                  */
  /* ------------------------------------------------------------------ */

  /**
   * Renderiza el contenido del carrito (lista, total, botones).
   *
   * @param {string} listaId — ID del contenedor de la lista.
   */
  function renderizarCarrito(listaId) {
    var lista = document.getElementById(listaId);
    if (!lista) return;

    var items = Cart.obtenerItems();

    if (items.length === 0) {
      lista.innerHTML =
        '<div class="carrito-vacio">' +
          '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' +
            '<circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/>' +
            '<path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>' +
          '</svg>' +
          '<p class="carrito-vacio-texto">Tu carrito está vacío</p>' +
        '</div>';
    } else {
      var html = '';
      for (var i = 0; i < items.length; i++) {
        var item = items[i];
        var producto = _buscarProductoEnCatalogo(item.productId);
        if (producto) {
          html += _renderizarItemCarrito(item, producto);
        }
      }
      lista.innerHTML = html;

      // Asignar manejador de error de imagen a cada img del carrito
      var imagenes = lista.querySelectorAll('.item-carrito-imagen');
      for (var j = 0; j < imagenes.length; j++) {
        imagenes[j].addEventListener('error', function () {
          _manejarErrorImagen(this);
        });
      }
    }

    // Actualizar total general (solo el span, sin destruir el label)
    _actualizarSubtotal();

    // Actualizar contador
    actualizarContadorCarrito(Cart.obtenerTotalItems());

    // Actualizar botón confirmar
    actualizarBotonConfirmar(!Cart.estaVacio());
  }

  /**
   * Busca un producto en el catálogo global por su ID.
   *
   * @param {number} productId — ID del producto.
   * @returns {Object|undefined} — Producto encontrado o undefined.
   */
  function _buscarProductoEnCatalogo(productId) {
    for (var i = 0; i < PRODUCTOS.length; i++) {
      if (PRODUCTOS[i].id === productId) return PRODUCTOS[i];
    }
    return undefined;
  }

  /**
   * Renderiza el HTML de un ítem del carrito.
   *
   * @param {{productId: number, quantity: number}} item — Ítem del carrito.
   * @param {Object} producto — Datos del producto.
   * @returns {string} — HTML del ítem.
   */
  function _renderizarItemCarrito(item, producto) {
    var subtotal = producto.precio * item.quantity;
    var maxAlcanzado = item.quantity >= Cart.obtenerMaxCantidad();

    return (
      '<div class="item-carrito" data-producto-id="' + producto.id + '">' +
        '<img class="item-carrito-imagen" src="' + producto.imagen + '" alt="' + _escapeAttr(producto.nombre) + '" loading="lazy">' +
        '<div class="item-carrito-info">' +
          '<span class="item-carrito-nombre">' + _escapeHtml(producto.nombre) + '</span>' +
          '<span class="item-carrito-precio-unitario">' + formatearPrecio(producto.precio) + ' c/u</span>' +
          '<div class="item-carrito-control">' +
            '<div class="control-cantidad" data-producto-id="' + producto.id + '">' +
              '<button class="btn-cantidad btn-restar" type="button" aria-label="Reducir cantidad">−</button>' +
              '<span class="cantidad-valor">' + item.quantity + '</span>' +
              '<button class="btn-cantidad btn-sumar" type="button" aria-label="Aumentar cantidad"' +
                (maxAlcanzado ? ' disabled' : '') + '>+</button>' +
            '</div>' +
            '<div class="item-carrito-acciones">' +
              '<span class="item-subtotal">' + formatearPrecio(subtotal) + '</span>' +
              '<button class="btn-eliminar" type="button" aria-label="Eliminar ' + _escapeAttr(producto.nombre) + '">' +
                '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
                  '<polyline points="3 6 5 6 21 6"/>' +
                  '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>' +
                '</svg>' +
              '</button>' +
            '</div>' +
          '</div>' +
        '</div>' +
      '</div>'
    );
  }

  /**
   * Actualiza el total general en el panel del carrito.
   * Solo modifica el span #total-general-carrito sin alterar el div contenedor
   * ni el label "Subtotal" que lo acompaña.
   */
  function _actualizarSubtotal() {
    var totalEl = document.getElementById('total-general-carrito');
    if (totalEl) {
      totalEl.textContent = formatearPrecio(Cart.obtenerTotalGeneral());
    }
  }

  /**
   * Actualiza el contador de ítems en el header.
   *
   * @param {number} count — Número total de ítems.
   */
  function actualizarContadorCarrito(count) {
    var contador = document.getElementById('contador-carrito');
    if (!contador) return;

    var valorActual = parseInt(contador.textContent, 10);
    contador.textContent = count;

    if (count !== valorActual) {
      contador.classList.remove('animar');
      // Forzar reflow para reiniciar la animación
      void contador.offsetWidth;
      contador.classList.add('animar');
    }
  }

  /**
   * Habilita o deshabilita el botón de confirmar compra.
   *
   * @param {boolean} habilitado — true para habilitar, false para deshabilitar.
   */
  function actualizarBotonConfirmar(habilitado) {
    var btn = document.getElementById('btn-confirmar');
    if (btn) {
      btn.disabled = !habilitado;
    }
  }

  /* ------------------------------------------------------------------ */
  /*  Toast (notificaciones efímeras)                                   */
  /* ------------------------------------------------------------------ */

  /**
   * Muestra una notificación toast efímera.
   *
   * @param {string} mensaje — Texto del toast.
   * @param {string} [tipo='info'] — Tipo de toast: 'info', 'exito', 'error'.
   */
  function mostrarToast(mensaje, tipo) {
    var container = document.getElementById('toast-container');
    if (!container) return;

    tipo = tipo || 'info';

    var toast = document.createElement('div');
    toast.className = 'toast ' + tipo;

    // Icono según tipo
    var iconoHtml = '';
    if (tipo === 'exito') {
      iconoHtml =
        '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
          '<polyline points="20 6 9 17 4 12"/>' +
        '</svg>';
    } else if (tipo === 'error') {
      iconoHtml =
        '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
          '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>' +
        '</svg>';
    } else {
      iconoHtml =
        '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
          '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>' +
        '</svg>';
    }

    toast.innerHTML = iconoHtml + '<span>' + _escapeHtml(mensaje) + '</span>';

    container.appendChild(toast);

    // Remover después de la animación (3s)
    setTimeout(function () {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
    }, 3000);
  }

  /* ------------------------------------------------------------------ */
  /*  Modal de resumen de compra                                        */
  /* ------------------------------------------------------------------ */

  /**
   * Muestra el modal con el resumen de la compra.
   * Genera la tabla con los productos, cantidades, precios y totales.
   */
  function mostrarModalResumen() {
    if (Cart.estaVacio()) return;

    var overlay = document.getElementById('modal-overlay');
    var cuerpo = document.getElementById('modal-cuerpo');
    if (!overlay || !cuerpo) return;

    var items = Cart.obtenerItems();

    // Construir tabla
    var html =
      '<table class="modal-tabla">' +
        '<thead>' +
          '<tr>' +
            '<th class="col-producto">Producto</th>' +
            '<th class="col-cantidad">Cant.</th>' +
            '<th class="col-precio">P. Unit.</th>' +
            '<th class="col-subtotal">Subtotal</th>' +
          '</tr>' +
        '</thead>' +
        '<tbody>';

    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      var producto = _buscarProductoEnCatalogo(item.productId);
      if (producto) {
        var subtotal = producto.precio * item.quantity;
        html +=
          '<tr>' +
            '<td class="col-producto">' + _escapeHtml(producto.nombre) + '</td>' +
            '<td class="col-cantidad">' + item.quantity + '</td>' +
            '<td class="col-precio">' + formatearPrecio(producto.precio) + '</td>' +
            '<td class="col-subtotal">' + formatearPrecio(subtotal) + '</td>' +
          '</tr>';
      }
    }

    html +=
        '</tbody>' +
      '</table>' +
      '<div class="modal-separador"></div>' +
      '<div class="modal-total-row">' +
        '<span class="modal-total-label">Total general</span>' +
        '<span class="modal-total-valor">' + formatearPrecio(Cart.obtenerTotalGeneral()) + '</span>' +
      '</div>';

    cuerpo.innerHTML = html;

    // Mostrar modal
    overlay.classList.add('activo');
    document.body.style.overflow = 'hidden';
  }

  /**
   * Cierra el modal de resumen.
   */
  function cerrarModal() {
    var overlay = document.getElementById('modal-overlay');
    if (overlay) {
      overlay.classList.remove('activo');
    }
    document.body.style.overflow = '';
  }

  /**
   * Muestra la animación de checkmark de éxito (compra confirmada).
   * Luego de la animación, ejecuta un callback.
   *
   * @param {function} callback — Función a ejecutar tras la animación.
   */
  function mostrarAnimacionExito(callback) {
    var overlay = document.createElement('div');
    overlay.className = 'checkmark-overlay';
    overlay.innerHTML =
      '<div class="checkmark-contenedor">' +
        '<div class="checkmark-circulo">' +
          '<svg class="checkmark-svg" viewBox="0 0 24 24">' +
            '<path d="M20 6L9 17l-5-5" fill="none"/>' +
          '</svg>' +
        '</div>' +
        '<p class="checkmark-texto">¡Compra confirmada!</p>' +
      '</div>';

    document.body.appendChild(overlay);

    setTimeout(function () {
      if (overlay.parentNode) {
        overlay.parentNode.removeChild(overlay);
      }
      if (typeof callback === 'function') {
        callback();
      }
    }, 1800);
  }

  /**
   * Aplica la animación de shake a un elemento.
   *
   * @param {HTMLElement|string} elemento — Elemento o ID del elemento.
   */
  function aplicarShake(elemento) {
    var el = (typeof elemento === 'string') ? document.getElementById(elemento) : elemento;
    if (!el) return;

    el.classList.remove('shake-aplicar');
    // Forzar reflow
    void el.offsetWidth;
    el.classList.add('shake-aplicar');

    setTimeout(function () {
      el.classList.remove('shake-aplicar');
    }, 500);
  }

  /* ------------------------------------------------------------------ */
  /*  API pública                                                        */
  /* ------------------------------------------------------------------ */

  return {
    renderizarGrilla: renderizarGrilla,
    renderizarCarrito: renderizarCarrito,
    actualizarContadorCarrito: actualizarContadorCarrito,
    actualizarBotonConfirmar: actualizarBotonConfirmar,
    mostrarModalResumen: mostrarModalResumen,
    cerrarModal: cerrarModal,
    mostrarAnimacionExito: mostrarAnimacionExito,
    mostrarToast: mostrarToast,
    formatearPrecio: formatearPrecio,
    aplicarShake: aplicarShake
  };
})();
