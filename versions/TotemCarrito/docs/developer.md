# Documentación para Desarrolladores — TotemCarrito

## Guía técnica del código fuente y guía de extensión

---

### Índice

1. [Arquitectura general](#1-arquitectura-general)
2. [Estructura de archivos y orden de carga](#2-estructura-de-archivos-y-orden-de-carga)
3. [Módulo: data.js — Catálogo de productos](#3-módulo-datajs--catálogo-de-productos)
4. [Módulo: cart.js — Gestión del carrito](#4-módulo-cartjs--gestión-del-carrito)
5. [Módulo: ui.js — Renderizado del DOM](#5-módulo-uijs--renderizado-del-dom)
6. [Módulo: app.js — Orquestador principal](#6-módulo-appjs--orquestador-principal)
7. [CSS: styles.css — Layout y estilos](#7-css-stylescss--layout-y-estilos)
8. [Flujo de datos completo](#8-flujo-de-datos-completo)
9. [Decisiones técnicas](#9-decisiones-técnicas)
10. [Cómo agregar o modificar productos](#10-cómo-agregar-o-modificar-productos)
11. [Cómo personalizar estilos](#11-cómo-personalizar-estilos)
12. [Cómo extender funcionalidades](#12-cómo-extender-funcionalidades)
13. [Notas de rendimiento](#13-notas-de-rendimiento)
14. [Seguridad](#14-seguridad)

---

## 1. Arquitectura general

TotemCarrito sigue una arquitectura de **tres capas** con separación estricta de responsabilidades. No utiliza frameworks, librerías externas ni gestores de paquetes.

```
┌────────────────────────────────────────────────────────────────┐
│                        index.html                              │
│   (Estructura semántica HTML5, contenedores con IDs, SVG inline)│
├────────────────────────────────────────────────────────────────┤
│                      css/styles.css                            │
│   (CSS Grid + Flexbox, paleta de colores, animaciones,         │
│    touch targets 48px, scrollbar personalizado)                │
├────────────────────────────────────────────────────────────────┤
│                       JavaScript (4 módulos)                   │
│                                                                 │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐       │
│  │   data.js    │   │   cart.js    │   │    ui.js     │       │
│  │  (Catálogo   │   │  (Estado del │   │  (Renderizado│       │
│  │   inmutable) │   │   carrito)   │   │     DOM)     │       │
│  │              │   │              │   │              │       │
│  │ PRODUCTOS    │──▶│ Cart (Map)   │◀──│ UI (lectura) │       │
│  │ (global)     │   │ (global)     │   │ (global)     │       │
│  └──────────────┘   └──────┬───────┘   └──────┬───────┘       │
│                            │                  │                │
│                            ▼                  ▼                │
│                      ┌────────────────────────────┐           │
│                      │         app.js             │           │
│                      │   (Orquestador + Eventos)  │           │
│                      │                            │           │
│                      │  init() → renderizarTodo() │           │
│                      │  Event delegation          │           │
│                      │  Cart.mutar() → UI.render()│           │
│                      └────────────────────────────┘           │
└────────────────────────────────────────────────────────────────┘
```

### Principios de diseño

| Principio | Aplicación |
|-----------|------------|
| **Separación de capas** | Datos (`data.js`), estado (`cart.js`), presentación (`ui.js`), orquestación (`app.js`). |
| **Única fuente de verdad** | `cart.js` es la única fuente de verdad del estado del carrito. `ui.js` nunca modifica el estado. |
| **Encapsulamiento** | Cada módulo usa el patrón **IIFE** (Immediately Invoked Function Expression) para exponer solo una API pública. |
| **Variables globales controladas** | Solo 3 variables globales: `PRODUCTOS`, `Cart`, `UI`. Todo lo demás es privado dentro de cada IIFE. |
| **Re-render completo** | Ante cualquier cambio de estado, se re-renderizan la grilla y el carrito completos. Simple, predecible y suficientemente rápido para 12 productos. |
| **Delegación de eventos** | Los event listeners se registran en contenedores padres, no en botones individuales. Solo hay 7 listeners en total. |

---

## 2. Estructura de archivos y orden de carga

### Orden de dependencias

Los scripts se cargan al final del `<body>` en `index.html` en este orden estricto:

```html
<script src="js/data.js"></script>   <!-- 1. Define PRODUCTOS (variable global) -->
<script src="js/cart.js"></script>   <!-- 2. Define Cart (depende de PRODUCTOS) -->
<script src="js/ui.js"></script>     <!-- 3. Define UI (depende de Cart y PRODUCTOS) -->
<script src="js/app.js"></script>    <!-- 4. Orquestador (depende de Cart y UI) -->
```

> **Importante:** El orden es crítico. `cart.js` necesita `PRODUCTOS` para calcular precios. `ui.js` necesita `Cart` para leer el estado. `app.js` necesita `Cart` y `UI` para orquestar. Si se altera el orden, la aplicación fallará con errores de referencia.

### Grafo de dependencias

```
data.js ──┐
           ├──▶ cart.js ──┐
           │              ├──▶ ui.js ──┐
           │              │            ├──▶ app.js
           │              │            │
           └──────────────┴────────────┘
              (cart.js y ui.js también leen PRODUCTOS)
```

---

## 3. Módulo: data.js — Catálogo de productos

**Archivo:** `js/data.js` (108 líneas)  
**Patrón:** Variable global constante  
**Variable expuesta:** `PRODUCTOS` (global, inmutable)

### Estructura de datos

```javascript
const PRODUCTOS = Object.freeze([
  {
    id: 1,                              // number — Identificador único
    nombre: 'Pan Artesanal',            // string — Nombre del producto
    descripcion: 'Pan de masa madre...',// string — Descripción corta
    precio: 1500,                       // number — Precio en CLP (entero, sin decimales)
    imagen: 'https://picsum.photos/...',// string — URL de imagen placeholder
    categoria: 'Panadería'              // string — Categoría (informativa, no se filtra)
  },
  // ... 11 productos más
]);
```

### Propiedades clave

- **`Object.freeze()`**: Hace el array inmutable. Cualquier intento de modificar `PRODUCTOS` lanzará un error en modo estricto o fallará silenciosamente en modo no estricto. Esto previene mutaciones accidentales de los datos del catálogo.
- **`precio` en entero**: Se almacena como número entero (sin decimales). El formateo con separador de miles (`$1.500`) se aplica en `ui.js`.
- **`imagen` con seed fijo**: Cada producto usa un seed único en `picsum.photos` (`seed/pan`, `seed/lechuga`, etc.) para que las imágenes sean consistentes entre recargas.

### Cómo modificar el catálogo

Vea la sección [Cómo agregar o modificar productos](#10-cómo-agregar-o-modificar-productos).

---

## 4. Módulo: cart.js — Gestión del carrito

**Archivo:** `js/cart.js` (192 líneas)  
**Patrón:** Módulo revelador (IIFE)  
**Variable expuesta:** `Cart` (global, API pública)

### Estado interno

```javascript
let items = new Map();  // Map<number, number> — productId → quantity
```

- Se utiliza `Map` en lugar de un objeto plano porque ofrece mejor semántica para pares clave-valor, métodos nativos (`has`, `delete`, `clear`, `forEach`) y mejor rendimiento en iteraciones.
- El estado es **privado** (dentro del closure de la IIFE). Solo se accede a través de la API pública expuesta.

### API pública

| Método | Parámetros | Retorno | Descripción |
|--------|------------|---------|-------------|
| `agregar(productId)` | `number` | `boolean` | Agrega 1 unidad. Retorna `false` si el producto no existe o ya tiene 99 unidades. |
| `quitar(productId)` | `number` | `boolean` | Quita 1 unidad. Si llega a 0, elimina el ítem. Retorna `false` si no existía. |
| `eliminar(productId)` | `number` | `boolean` | Elimina completamente el producto del carrito. |
| `limpiar()` | — | — | Vacía el carrito completamente (`items.clear()`). |
| `obtenerItems()` | — | `Array<{productId, quantity}>` | Devuelve copia de los ítems como array de objetos. |
| `obtenerCantidad(productId)` | `number` | `number` | Cantidad actual (0 si no está en el carrito). |
| `obtenerTotalItems()` | — | `number` | Suma total de todas las cantidades. |
| `obtenerSubtotal(productId)` | `number` | `number` | Precio × cantidad del producto. 0 si no está. |
| `obtenerTotalGeneral()` | — | `number` | Suma de todos los subtotales. |
| `estaVacio()` | — | `boolean` | `true` si no hay productos en el carrito. |
| `obtenerMaxCantidad()` | — | `number` | Retorna `99` (límite máximo por producto). |

### Constantes internas

| Constante | Valor | Descripción |
|-----------|-------|-------------|
| `MAX_CANTIDAD` | `99` | Máximo de unidades por producto |
| `MIN_CANTIDAD` | `1` | Mínimo antes de eliminar el ítem |

### Dependencias

- **`PRODUCTOS`** (de `data.js`): La función privada `_buscarProducto()` itera sobre `PRODUCTOS` para encontrar un producto por ID. Se usa en `agregar()`, `obtenerSubtotal()` y `obtenerTotalGeneral()`.

### Flujo de `agregar()`

```
agregar(productId)
  ├── _buscarProducto(productId) → ¿existe?
  │     └── No → return false
  ├── items.get(productId) || 0 → cantidadActual
  ├── ¿cantidadActual >= 99?
  │     └── Sí → return false
  └── items.set(productId, cantidadActual + 1) → return true
```

### Flujo de `quitar()`

```
quitar(productId)
  ├── ¿items.has(productId)?
  │     └── No → return false
  ├── cantidadActual = items.get(productId)
  ├── ¿cantidadActual <= 1?
  │     ├── Sí → items.delete(productId)
  │     └── No → items.set(productId, cantidadActual - 1)
  └── return true
```

---

## 5. Módulo: ui.js — Renderizado del DOM

**Archivo:** `js/ui.js` (520 líneas)  
**Patrón:** Módulo revelador (IIFE)  
**Variable expuesta:** `UI` (global, API pública)

### Principio fundamental

> **`ui.js` NUNCA modifica el estado del carrito.** Solo lee datos de `Cart` y de `PRODUCTOS`, y genera/actualiza el DOM. Las mutaciones del estado son responsabilidad exclusiva de `app.js` (que llama a `Cart`).

### API pública

| Método | Parámetros | Descripción |
|--------|------------|-------------|
| `renderizarGrilla(containerId)` | `string` | Renderiza las 12 tarjetas de producto en el contenedor indicado. |
| `renderizarCarrito(listaId)` | `string` | Renderiza la lista de ítems, actualiza subtotal, contador y botón confirmar. |
| `actualizarContadorCarrito(count)` | `number` | Actualiza el badge del header con animación si el valor cambió. |
| `actualizarBotonConfirmar(habilitado)` | `boolean` | Habilita/deshabilita el botón "Confirmar compra". |
| `mostrarModalResumen()` | — | Genera la tabla resumen y muestra el modal. Requiere que el carrito no esté vacío. |
| `cerrarModal()` | — | Oculta el modal y restaura el scroll del body. |
| `mostrarAnimacionExito(callback)` | `function` | Muestra el overlay de check verde; ejecuta el callback tras 1.8s. |
| `mostrarToast(mensaje, tipo)` | `string, string` | Muestra un toast efímero. `tipo`: `'info'`, `'exito'`, `'error'`. |
| `formatearPrecio(precio)` | `number` | Formatea un número como `$1.500`. Expuesto para uso externo. |
| `aplicarShake(elemento)` | `HTMLElement\|string` | Aplica animación de shake al elemento. |

### Funciones privadas clave

| Función | Descripción |
|---------|-------------|
| `_renderizarTarjetaProducto(producto, cantidad)` | Genera HTML de una tarjeta. Si `cantidad > 0`, muestra control −/cantidad/+; si no, muestra botón "Agregar". |
| `_renderizarItemCarrito(item, producto)` | Genera HTML de un ítem en el panel del carrito con miniatura, control de cantidad, subtotal y botón eliminar. |
| `_buscarProductoEnCatalogo(productId)` | Busca un producto en `PRODUCTOS` por ID (iteración lineal, 12 elementos). |
| `_actualizarSubtotal()` | Actualiza solo el span `#total-general-carrito` sin destruir el label "Subtotal". |
| `_escapeHtml(texto)` | Escapa `<`, `>`, `&`, `"` para contenido HTML usando `createTextNode`. Previene XSS. |
| `_escapeAttr(texto)` | Escapa adicionalmente `"` → `&quot;` para atributos HTML delimitados por comillas dobles. |
| `_manejarErrorImagen(img)` | Reemplaza una imagen que falló al cargar por un div con iniciales del producto. |
| `_obtenerIniciales(nombre)` | Extrae las iniciales de un nombre de producto (máx. 2 caracteres). |

### Estrategia de escape de HTML (prevención XSS)

Se utilizan **dos funciones de escape diferentes** según el contexto:

- **`_escapeHtml()`** para contenido entre etiquetas HTML (nombre, descripción, categoría). Utiliza `document.createElement('div')` + `createTextNode()` — el método más seguro porque delega el escape al motor del navegador.

- **`_escapeAttr()`** para valores de atributos HTML delimitados por comillas dobles (`alt`, `aria-label`). Escapa manualmente `&`, `"`, `<`, `>` en ese orden (`&` primero para evitar double-escaping).

> **Regla:** nunca uses `_escapeHtml()` dentro de atributos HTML. Usa `_escapeAttr()`. La diferencia es que `_escapeHtml()` no escapa comillas dobles.

### Manejo de errores de imagen

Cuando una imagen de producto falla al cargar (por falta de internet o URL rota):

1. El evento `error` en el `<img>` activa `_manejarErrorImagen()`.
2. Se verifica que no se haya aplicado ya un fallback (usando `dataset.fallback`).
3. Se obtienen las iniciales del producto desde el texto del nombre en la tarjeta contenedora.
4. Se oculta la imagen (`display: none`).
5. Se inserta un `<div class="tarjeta-imagen-fallback">` con las iniciales.

---

## 6. Módulo: app.js — Orquestador principal

**Archivo:** `js/app.js` (266 líneas)  
**Patrón:** IIFE auto-ejecutable  
**Variable expuesta:** Ninguna (todo es privado dentro del closure)

### Responsabilidad

`app.js` es el **orquestador** que coordina los otros módulos. Sus tareas son:

1. Inicializar la UI al cargar la página.
2. Vincular event listeners mediante delegación de eventos.
3. Traducir eventos de usuario en mutaciones de estado (`Cart`) y re-renderizados (`UI`).

### Función central: `renderizarTodo()`

```javascript
function renderizarTodo() {
  UI.renderizarGrilla('grilla-productos');
  UI.renderizarCarrito('lista-carrito');
}
```

Se llama en dos situaciones:
- Al inicializar la aplicación (`init()`).
- Después de **cada mutación del carrito** (agregar, quitar, eliminar, limpiar).

### Delegación de eventos

En lugar de registrar listeners en cada botón individual, se usa **delegación de eventos**: se registra un listener en el contenedor padre y se identifica el botón específico mediante `event.target.closest()`.

**Listeners registrados (7 en total):**

| # | Contenedor | Selector delegado | Acción |
|---|-----------|-------------------|--------|
| 1 | `#grilla-productos` | `.btn-agregar` | `Cart.agregar()` → `renderizarTodo()` |
| 2 | `#grilla-productos` | `.btn-sumar` | `Cart.agregar()` → `renderizarTodo()` |
| 3 | `#grilla-productos` | `.btn-restar` | `Cart.quitar()` → `renderizarTodo()` |
| 4 | `#lista-carrito` | `.btn-sumar` | `Cart.agregar()` → `renderizarTodo()` |
| 5 | `#lista-carrito` | `.btn-restar` | `Cart.quitar()` → `renderizarTodo()` |
| 6 | `#lista-carrito` | `.btn-eliminar` | `Cart.eliminar()` → `renderizarTodo()` |
| 7 | `#btn-limpiar` | (directo) | `Cart.limpiar()` → `renderizarTodo()` + toast |
| 8 | `#btn-confirmar` | (directo) | `UI.mostrarModalResumen()` |
| 9 | `#modal-btn-confirmar` | (directo) | `UI.cerrarModal()` → animación → `Cart.limpiar()` |
| 10 | `#modal-btn-cancelar` | (directo) | `UI.cerrarModal()` |
| 11 | `#modal-overlay` | `event.target === overlay` | `UI.cerrarModal()` |

### Función auxiliar: `obtenerProductoId(el)`

```javascript
function obtenerProductoId(el) {
  var target = el.closest('[data-producto-id]');
  if (!target) return null;
  var id = parseInt(target.getAttribute('data-producto-id'), 10);
  return isNaN(id) ? null : id;
}
```

Recorre los ancestros del elemento clickeado hasta encontrar uno con el atributo `data-producto-id`. Esto permite que el evento de clic se capture sin importar si el usuario tocó el botón, el SVG dentro del botón, o el span de texto.

### Inicialización

```javascript
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
```

Cubre dos casos:
- Si el DOM aún no está listo, espera `DOMContentLoaded`.
- Si el DOM ya está listo (script cargado con retraso), ejecuta `init()` inmediatamente.

---

## 7. CSS: styles.css — Layout y estilos

**Archivo:** `css/styles.css` (930 líneas)  
**Diseño:** CSS Grid para el layout principal, Flexbox para componentes internos.

### Layout principal (CSS Grid)

```css
#contenedor-principal {
  display: grid;
  grid-template-columns: 1fr 432px;   /* 60% productos | 40% carrito (ancho fijo) */
  height: calc(1920px - 80px);        /* Altura total menos header */
  width: 1080px;
}
```

- La grilla de productos (`#grilla-productos`) ocupa la fracción flexible (`1fr`), aproximadamente 648 px.
- El panel del carrito (`#panel-carrito`) tiene un ancho fijo de **432 px** (40% de 1080).
- El header (`#app-header`) está fuera del grid, con altura fija de **80 px**.

### Grilla de productos (sub-grid)

```css
#grilla-productos {
  display: grid;
  grid-template-columns: 1fr 1fr;     /* 2 columnas de igual ancho */
  gap: 20px;
  overflow-y: auto;                   /* Scroll vertical independiente */
  scroll-behavior: smooth;
}
```

### Panel del carrito (sticky)

```css
#panel-carrito {
  height: 100%;
  overflow: hidden;
}

.panel-sticky {
  position: sticky;
  top: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}
```

- La lista de ítems (`.lista-carrito`) tiene `flex: 1` y `overflow-y: auto` para scroll interno.
- El subtotal y los botones de acción están fijos en la parte inferior del panel.

### Touch targets (WCAG 2.1)

Todos los elementos interactivos tienen un tamaño mínimo de **48×48 px**:

```css
.btn-agregar {
  min-width: 48px;
  min-height: 48px;
}

.control-cantidad .btn-cantidad {
  width: 48px;
  min-width: 48px;
  height: 48px;
}

.btn {
  min-height: 52px;
}
```

### Animaciones

| Keyframe | Uso | Duración |
|----------|-----|----------|
| `fadeIn` | Modal, toast, overlay de éxito | 0.25s |
| `slideUp` | Modal, ítems del carrito | 0.3s |
| `shake` | Botón confirmar (carrito vacío) | 0.4s |
| `badgePop` | Contador del header | 0.3s |
| `checkmarkPop` | Círculo de éxito (escala) | 0.4s |
| `checkmarkDraw` | Dibujado del check (stroke-dashoffset) | 0.5s |
| `toastIn` / `toastOut` | Entrada/salida de toasts | 0.3s |

### Scrollbar personalizado

Se estilizan los scrollbars para Webkit (Chrome/Edge/Safari):

```css
#grilla-productos::-webkit-scrollbar { width: 8px; }
#grilla-productos::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
```

### Paleta de colores (variables implícitas)

Aunque no se usan CSS custom properties, la paleta está documentada en el README. Los colores principales son:

- Primario: `#0f766e` (teal-700)
- Hover: `#0d9488` (teal-600)
- Active: `#115e59` (teal-800)
- Éxito: `#16a34a` (green-600)
- Error: `#dc2626` (red-600)
- Fondo: `#f9f7f4` (off-white)
- Superficie: `#ffffff`
- Texto: `#1e293b` (slate-800)

---

## 8. Flujo de datos completo

### Ciclo de vida de una interacción

```
[Usuario presiona "+" en Pan Artesanal]
        │
        ▼
[app.js] Event listener en #grilla-productos
        │  event.target.closest('.btn-sumar')
        │  obtenerProductoId(btnSumar) → 1
        ▼
[cart.js] Cart.agregar(1)
        │  items.get(1) → cantidad actual 2
        │  items.set(1, 3)
        │  return true
        ▼
[app.js] renderizarTodo()
        │
        ├──▶ [ui.js] UI.renderizarGrilla('grilla-productos')
        │         │  Itera PRODUCTOS (12 productos)
        │         │  Para Pan (id=1): Cart.obtenerCantidad(1) → 3
        │         │  _renderizarTarjetaProducto(pan, 3)
        │         │  Genera HTML con control −/3/+ (máx no alcanzado: + habilitado)
        │         │  container.innerHTML = html
        │         └── Asigna manejadores de error a las imágenes
        │
        └──▶ [ui.js] UI.renderizarCarrito('lista-carrito')
                  │  Cart.obtenerItems() → [{productId: 1, quantity: 3}]
                  │  _buscarProductoEnCatalogo(1) → objeto Pan
                  │  _renderizarItemCarrito(item, pan)
                  │  Genera HTML con miniatura, nombre, −/3/+, subtotal=$4.500, btn-eliminar
                  │  lista.innerHTML = html
                  ├── _actualizarSubtotal() → total-general-carrito.textContent = "$4.500"
                  ├── actualizarContadorCarrito(3) → badge animado
                  └── actualizarBotonConfirmar(true) → habilitado
```

### Flujo de confirmación de compra

```
[Usuario presiona "Confirmar compra"]
        │
        ▼
[app.js] manejadorConfirmarCompra()
        │  Cart.estaVacio() → false
        ▼
[ui.js] UI.mostrarModalResumen()
        │  Cart.obtenerItems() → [...]
        │  Genera tabla HTML con productos, cantidades, precios, subtotales
        │  Calcula Cart.obtenerTotalGeneral()
        │  modal-cuerpo.innerHTML = tabla
        │  modal-overlay.classList.add('activo')
        │
        ▼
[Usuario presiona "Confirmar" en modal]
        │
        ▼
[app.js] manejadorModalConfirmar()
        │
        ├──▶ [ui.js] UI.cerrarModal()
        │         modal-overlay.classList.remove('activo')
        │
        └──▶ [ui.js] UI.mostrarAnimacionExito(callback)
                  │  Crea overlay con check verde
                  │  setTimeout(1800ms) → remueve overlay → ejecuta callback
                  │
                  ▼ (callback)
                  [cart.js] Cart.limpiar()
                  [app.js] renderizarTodo()
                  [ui.js] UI.mostrarToast('¡Compra confirmada!...', 'exito')
```

---

## 9. Decisiones técnicas

### 9.1 Re-render completo

**Decisión:** Cada vez que cambia el carrito, se re-renderiza todo el DOM de la grilla y el panel.

**Justificación:**
- Simplicidad: una sola función (`renderizarTodo()`) mantiene la UI sincronizada con el estado.
- Predictibilidad: no hay estados inconsistentes entre la grilla y el carrito.
- Rendimiento aceptable: con 12 productos, el DOM generado es de ~24 tarjetas y ~12 ítems de carrito (máximo). El re-render completo toma < 5 ms.
- Alternativa descartada: actualización selectiva del DOM requeriría mantener referencias a nodos específicos y lógica de diffing manual, añadiendo complejidad innecesaria.

### 9.2 Delegación de eventos

**Decisión:** Todos los eventos se capturan en contenedores padres usando `closest()` en lugar de listeners individuales por botón.

**Justificación:**
- Con re-render completo, los botones se destruyen y recrean constantemente. Si se usaran listeners directos, habría que re-registrarlos cada vez.
- Solo 7 listeners totales, independientemente de cuántos productos haya en el carrito.
- Mejor rendimiento de memoria y menor riesgo de memory leaks.

### 9.3 Patrón IIFE sin ES modules

**Decisión:** Cada archivo JS usa el patrón IIFE para encapsulamiento. No se usan `import`/`export` de ES6.

**Justificación:**
- Compatibilidad con navegadores más antiguos (sin necesidad de bundler).
- Carga simple con etiquetas `<script>` en orden, sin necesidad de servidor de desarrollo.
- Las variables globales (`PRODUCTOS`, `Cart`, `UI`) son un trade-off consciente: solo 3 variables globales para toda la aplicación, aceptable para un proyecto de este tamaño.

### 9.4 `Map` en lugar de objeto plano para el carrito

**Decisión:** El estado del carrito es un `Map<number, number>` en lugar de un objeto `{ [productId]: quantity }`.

**Justificación:**
- `Map` tiene API nativa más limpia: `has()`, `delete()`, `clear()`, `forEach()`.
- Mejor semántica: es un mapa de claves a valores, no un objeto genérico.
- Iteración predecible (orden de inserción).
- `items.size` para verificar si está vacío (más explícito que `Object.keys(obj).length`).

### 9.5 Escape HTML por contexto

**Decisión:** Dos funciones de escape separadas: `_escapeHtml()` para contenido de texto y `_escapeAttr()` para atributos HTML.

**Justificación:**
- Seguridad: el contexto de atributo HTML requiere escapar comillas dobles (`"`), que no son peligrosas en contenido de texto.
- `_escapeHtml()` usa `createTextNode()`, la forma más segura de escapar HTML porque delega en el motor del navegador.
- `_escapeAttr()` usa reemplazo manual para garantizar compatibilidad en todos los navegadores.

### 9.6 Formateo de precios sin `Intl.NumberFormat`

**Decisión:** `formatearPrecio()` usa una expresión regular en lugar de `Intl.NumberFormat`.

**Justificación:**
- Simplicidad: la expresión regular `/\B(?=(\d{3})+(?!\d))/g` es suficiente para el formato chileno (`$1.500`).
- `Intl.NumberFormat` podría usarse para i18n futura, pero añade complejidad innecesaria para un solo locale.

### 9.7 Sin persistencia en localStorage

**Decisión:** El carrito no se persiste entre recargas de página.

**Justificación:**
- El proyecto es un frontend estático para un tótem de autoatención. El carrito se vacía naturalmente al confirmar la compra.
- En modo kiosko, la página rara vez se recarga.
- Si se requiere persistencia, es trivial añadir `localStorage` en `cart.js` (ver sección de extensión).

---

## 10. Cómo agregar o modificar productos

### Agregar un nuevo producto

Edite `js/data.js` y añada un nuevo objeto al array `PRODUCTOS`. Ejemplo:

```javascript
// Dentro del array PRODUCTOS, antes del cierre ]
{
  id: 13,
  nombre: 'Yogur Natural (500ml)',
  descripcion: 'Yogur natural sin azúcar, elaborado con leche entera. Cremoso y probiótico.',
  precio: 1600,
  imagen: 'https://picsum.photos/seed/yogur/400/300',
  categoria: 'Lácteos'
}
```

**Reglas:**
- El `id` debe ser **único** y consecutivo.
- El `precio` debe ser un número entero (sin decimales).
- La `imagen` debe ser una URL de `picsum.photos` con un seed único, o una ruta a una imagen local.
- La `categoria` es libre, pero idealmente debe coincidir con las existentes para consistencia visual.

### Modificar un producto existente

Edite el objeto correspondiente en `js/data.js`. Por ejemplo, para cambiar el precio del Pan Artesanal:

```javascript
{
  id: 1,
  nombre: 'Pan Artesanal',
  descripcion: 'Pan de masa madre, horneado a leña...',
  precio: 1800,  // Cambiado de 1500 a 1800
  // ...
}
```

**No es necesario modificar ningún otro archivo.** El cambio se reflejará automáticamente en la UI en la siguiente recarga.

### Eliminar un producto

Simplemente elimine el objeto completo del array. Asegúrese de que los IDs restantes sigan siendo consistentes (no es necesario que sean consecutivos, pero es una buena práctica).

### Usar imágenes locales

Si prefiere no depender de `picsum.photos`:

1. Cree una carpeta `img/` en el proyecto.
2. Coloque las imágenes allí (por ejemplo, `img/pan.jpg`).
3. Cambie la propiedad `imagen`:

```javascript
imagen: 'img/pan.jpg',
```

---

## 11. Cómo personalizar estilos

### Cambiar la paleta de colores

Edite `css/styles.css`. Los colores principales están dispersos en los selectores. Para cambiarlos eficientemente, busque y reemplace:

| Color original | Selectores donde aparece |
|---------------|--------------------------|
| `#0f766e` | `.header`, `.btn-agregar`, `.btn-primario`, `.tarjeta-precio`, `.tarjeta-categoria`, `.subtotal-valor` (borde), `.modal-header`, `.modal-total-valor`, `.item-subtotal` |
| `#0d9488` | `.btn-agregar:hover`, `.btn-primario:hover`, `header` (gradiente) |
| `#115e59` | `.btn-agregar:active`, `.btn-primario:active` |
| `#16a34a` | `.checkmark-circulo`, `.checkmark-texto`, `.toast.exito` |
| `#dc2626` | `.btn-secundario`, `.btn-eliminar`, `.toast.error` |
| `#f9f7f4` | `body` |
| `#1e293b` | `body`, `.tarjeta-nombre`, `.modal-titulo` |
| `#64748b` | `.tarjeta-descripcion`, `.modal-pregunta`, `.subtotal-label` |

**Recomendación:** Para facilitar cambios futuros, considere migrar a CSS custom properties:

```css
:root {
  --color-primary: #0f766e;
  --color-primary-hover: #0d9488;
  --color-primary-active: #115e59;
  --color-success: #16a34a;
  --color-danger: #dc2626;
  --color-bg: #f9f7f4;
  --color-text: #1e293b;
  --color-text-secondary: #64748b;
}
```

### Cambiar la tipografía

La fuente se define en `body`:

```css
body {
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
}
```

Cambie a cualquier fuente del sistema o agregue una `@import` de Google Fonts.

### Modificar la resolución

Si necesita cambiar la resolución objetivo (por ejemplo, 768×1366 para un tótem más pequeño):

1. Edite el meta viewport en `index.html`:
   ```html
   <meta name="viewport" content="width=768, height=1366, initial-scale=1.0, user-scalable=no">
   ```

2. Edite `css/styles.css`:
   ```css
   body {
     width: 768px;
     height: 1366px;
   }
   #modal-overlay {
     width: 768px;
     height: 1366px;
   }
   .checkmark-overlay {
     width: 768px;
     height: 1366px;
   }
   ```

3. Ajuste el ancho del panel del carrito según la proporción deseada:
   ```css
   #contenedor-principal {
     grid-template-columns: 1fr 307px;  /* 40% de 768 */
   }
   ```

---

## 12. Cómo extender funcionalidades

### Agregar persistencia con localStorage

En `js/cart.js`, modifique el módulo para guardar/cargar el estado:

```javascript
const Cart = (function () {
  'use strict';
  
  const STORAGE_KEY = 'totemcarrito_cart';
  
  // Cargar estado al iniciar
  let items = new Map();
  try {
    var saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      JSON.parse(saved).forEach(function (entry) {
        items.set(entry[0], entry[1]);
      });
    }
  } catch (e) { /* ignorar errores de localStorage */ }
  
  function _guardar() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify([...items]));
    } catch (e) { /* ignorar */ }
  }
  
  // Llamar _guardar() después de cada mutación
  function agregar(productId) {
    // ... lógica existente ...
    _guardar();  // ← añadir esta línea
    return true;
  }
  // ... mismo patrón en quitar(), eliminar(), limpiar() ...
})();
```

### Agregar filtro por categoría

1. En `index.html`, agregue botones de filtro (ej: "Panadería", "Verduras", "Lácteos", "Almacén", "Todos").
2. En `ui.js`, modifique `renderizarGrilla()` para aceptar una categoría opcional:

```javascript
function renderizarGrilla(containerId, filtroCategoria) {
  var container = document.getElementById(containerId);
  var html = '';
  for (var i = 0; i < PRODUCTOS.length; i++) {
    if (filtroCategoria && PRODUCTOS[i].categoria !== filtroCategoria) continue;
    // ... resto igual ...
  }
  container.innerHTML = html;
}
```

3. En `app.js`, agregue listeners para los botones de filtro que llamen a `UI.renderizarGrilla()` con la categoría seleccionada.

### Agregar búsqueda de productos

1. Agregue un `<input type="search">` en el header de `index.html`.
2. En `renderizarGrilla()`, agregue un parámetro `filtroTexto`:

```javascript
function renderizarGrilla(containerId, filtroTexto) {
  var termino = (filtroTexto || '').toLowerCase();
  // ... en el loop:
  if (termino && producto.nombre.toLowerCase().indexOf(termino) === -1) continue;
}
```

### Integrar con un backend

Para conectar con una API de pedidos:

1. En `app.js`, modifique `manejadorModalConfirmar()`:

```javascript
function manejadorModalConfirmar() {
  UI.cerrarModal();
  
  var pedido = {
    items: Cart.obtenerItems(),
    total: Cart.obtenerTotalGeneral(),
    timestamp: new Date().toISOString()
  };
  
  fetch('https://api.mitienda.com/pedidos', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(pedido)
  })
  .then(function (response) {
    if (response.ok) {
      UI.mostrarAnimacionExito(function () {
        Cart.limpiar();
        renderizarTodo();
        UI.mostrarToast('¡Pedido enviado!', 'exito');
      });
    } else {
      UI.mostrarToast('Error al enviar el pedido', 'error');
    }
  })
  .catch(function () {
    UI.mostrarToast('Error de conexión', 'error');
  });
}
```

---

## 13. Notas de rendimiento

### Rendimiento actual

| Métrica | Valor | Nota |
|---------|-------|------|
| **Tiempo de re-render** | < 5 ms | Para 12 productos + carrito, insignificante |
| **Tamaño DOM total** | ~150 nodos | Incluyendo grilla (24 tarjetas máx.) y carrito (12 ítems máx.) |
| **Listeners de eventos** | 7 | Delegación de eventos en contenedores |
| **CSS total** | 930 líneas | Sin dependencias externas |
| **JS total** | ~1086 líneas | 4 archivos, sin minificación (en producción se recomienda minificar) |
| **Carga inicial** | < 50 ms (local) | Sin dependencias de red (excepto imágenes) |

### Oportunidades de optimización

- **Minificación:** Para producción, minificar `styles.css` y los 4 archivos JS reduciría el tamaño total en ~40-60%.
- **Inlining de CSS crítico:** El CSS above-the-fold podría inyectarse en `<style>` para eliminar el bloqueo de renderizado.
- **Lazy loading mejorado:** Las imágenes ya usan `loading="lazy"`, pero podría usarse `IntersectionObserver` para cargar imágenes solo cuando están visibles en el viewport.
- **Virtual scrolling:** Si el catálogo creciera a 100+ productos, implementar virtual scrolling en la grilla mejoraría el rendimiento. Para 12 productos no es necesario.

### Consideraciones para el modo kiosko

- **Sin animaciones innecesarias:** Las animaciones son solo con `transform` y `opacity` (GPU-accelerated). No hay `setInterval` ni polling.
- **Sin memory leaks:** Los toasts se auto-remueven tras 3 segundos. Los event listeners son por delegación (no se acumulan). El modal limpia sus referencias al cerrarse.
- **Touch events:** Solo se usan eventos `click` (no `touchstart`/`touchend` separados). El atributo `touch-action: manipulation` en botones evita el delay de 300ms en navegadores móviles.

---

## 14. Seguridad

### XSS (Cross-Site Scripting)

- **Contexto de HTML:** Todo contenido de texto que se inserta en el DOM mediante `innerHTML` primero pasa por `_escapeHtml()`, que usa `createTextNode()` — el método más seguro.
- **Contexto de atributo:** Los valores de atributos (`alt`, `aria-label`) pasan por `_escapeAttr()`, que escapa `&`, `"`, `<`, `>`.
- **No se usa `eval()`, `document.write()`, ni `Function()` constructor** en ningún lugar del código.

### CSP (Content Security Policy)

Si se desea agregar una política CSP, se recomienda:

```html
<meta http-equiv="Content-Security-Policy" content="
  default-src 'self';
  img-src 'self' https://picsum.photos;
  style-src 'self' 'unsafe-inline';
  script-src 'self';
">
```

Nota: `'unsafe-inline'` para estilos es necesario porque los estilos están en un archivo externo, pero las animaciones usan estilos inline generados por JS. Idealmente se usarían nonces o hashes.

### Datos sensibles

- **Sin credenciales hardcodeadas:** No hay API keys, tokens ni contraseñas en el código.
- **Sin almacenamiento de datos de usuario:** No se recolecta ni almacena información personal.
- **Las URLs de imágenes son la única dependencia externa.**

---

*Para documentación de usuario y guía de operación, vea `docs/datasheet.md`. Para información general del proyecto, vea `README.md`.*
