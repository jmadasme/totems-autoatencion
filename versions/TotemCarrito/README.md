# TotemCarrito — Tótem de Autoatención con Carrito de Compras

![Versión](https://img.shields.io/badge/versión-1.0.0-0f766e)
![Tecnologías](https://img.shields.io/badge/HTML-CSS-JS-0f766e)
![Licencia](https://img.shields.io/badge/licencia-MIT-0f766e)

Aplicación web estática de carrito de compras de productos alimenticios, diseñada específicamente para un **tótem de autoatención** con pantalla táctil vertical de **1080 x 1920 píxeles**. Permite a los clientes explorar un catálogo de 12 productos, agregarlos al carrito, ajustar cantidades y confirmar su compra de forma autónoma, sin intervención de un vendedor.

---

## Índice

- [¿Qué es un tótem de autoatención?](#qué-es-un-tótem-de-autoatención)
- [Propósito del proyecto](#propósito-del-proyecto)
- [Forma de operar](#forma-de-operar)
- [Interfaz de usuario y layout de pantalla](#interfaz-de-usuario-y-layout-de-pantalla)
- [Estructura de la aplicación](#estructura-de-la-aplicación)
- [Ejemplos de uso paso a paso](#ejemplos-de-uso-paso-a-paso)
- [Configuración del viewport y resolución](#configuración-del-viewport-y-resolución)
- [Tecnologías utilizadas](#tecnologías-utilizadas)
- [Estructura de archivos](#estructura-de-archivos)
- [Paleta de colores](#paleta-de-colores)
- [Advertencias y precauciones](#advertencias-y-precauciones)
- [Créditos](#créditos)

---

## ¿Qué es un tótem de autoatención?

Un **tótem de autoatención** es un dispositivo electrónico interactivo con pantalla táctil que permite a los clientes realizar operaciones por sí mismos sin necesidad de asistencia de personal. Son comunes en restaurantes de comida rápida, supermercados, tiendas de autoservicio y puntos de venta minorista.

Este tipo de dispositivos suele montarse en formato vertical (retrato) y debe ofrecer una interfaz táctil intuitiva, con botones grandes, tipografía legible a distancia y un flujo de uso claro que minimice errores.

## Propósito del proyecto

**TotemCarrito** es la capa de _frontend_ de un sistema de autoatención para un local de productos alimenticios (panadería, verdulería, lácteos y almacén). Sus objetivos principales son:

- Permitir al cliente navegar por un catálogo de productos con imágenes y descripciones.
- Agregar productos al carrito con control preciso de cantidades (hasta 99 unidades por producto).
- Visualizar en tiempo real el resumen de la compra y el total acumulado.
- Confirmar la compra mediante un modal de resumen, con animación de éxito y limpieza automática del carrito.

> **Nota:** Este proyecto es puramente frontend. No incluye backend, base de datos, sistema de pago ni persistencia de datos entre recargas de página.

## Forma de operar

El flujo de uso está diseñado para ser simple y lineal:

```
VER PRODUCTOS  →  AGREGAR AL CARRITO  →  MODIFICAR CANTIDADES  →  CONFIRMAR COMPRA
```

1. **Ver productos:** La pantalla principal muestra una grilla de 2 columnas con los 12 productos del catálogo. Cada tarjeta incluye imagen, nombre, categoría, descripción y precio.

2. **Agregar al carrito:** El usuario presiona el botón _"Agregar al carrito"_ en cualquier producto. El producto aparece inmediatamente en el panel derecho con cantidad = 1, y el botón cambia a un control de cantidad (+ / −).

3. **Modificar cantidades:** Una vez que un producto está en el carrito, el usuario puede:
   - Presionar **+** para incrementar la cantidad (máximo 99 unidades).
   - Presionar **−** para reducir la cantidad. Si llega a 0, el producto se elimina del carrito.
   - Presionar el botón **×** (eliminar) en el panel del carrito para removerlo completamente.

4. **Gestionar el carrito:** El panel derecho muestra todos los ítems con su subtotal individual y el total acumulado. El usuario puede usar el botón _"Limpiar carrito"_ para vaciarlo completamente.

5. **Confirmar compra:** Al presionar _"Confirmar compra"_, se abre un modal con una tabla resumen de todos los productos, cantidades, precios unitarios, subtotales y total general. El usuario elige:
   - **Cancelar:** Cierra el modal y conserva el carrito intacto.
   - **Confirmar:** Finaliza la compra con una animación de éxito, limpia el carrito y restaura la vista de catálogo.

## Interfaz de usuario y layout de pantalla

La aplicación está optimizada para resolución fija **1080 x 1920 px** en orientación vertical (retrato).

### Zonas de la pantalla

| Zona | Descripción | Dimensiones |
|------|-------------|-------------|
| **Header** | Barra superior con logo y contador de ítems | Alto: 80 px, ancho: 1080 px |
| **Grilla de productos** | Catálogo en 2 columnas con scroll vertical | ~60% del ancho (~648 px) |
| **Panel del carrito** | Lista de ítems, subtotales y botones de acción | ~40% del ancho (432 px) |
| **Modal** | Overlay centrado con resumen de compra | 680 px de ancho, altura variable |

### Jerarquía visual

```
┌──────────────────────────────────────────────────────┐
│  HEADER (80 px)                                      │
│  [Logo]  Tótem de Autoatención          [Carrito: 3] │
├────────────────────────────────┬─────────────────────┤
│                                │                     │
│  GRILLA DE PRODUCTOS (60%)     │  PANEL DEL CARRITO  │
│  ┌──────────┐ ┌──────────┐    │  (40% - 432 px)     │
│  │ Producto 1│ │ Producto 2│   │                     │
│  │ Imagen    │ │ Imagen    │   │  Tu Carrito         │
│  │ Nombre    │ │ Nombre    │   │  ┌───────────────┐  │
│  │ $X.XXX    │ │ $X.XXX    │   │  │ Prod A  [− 2 +]│  │
│  │ [Agregar] │ │ [− 3 +]   │   │  │ $3.000 c/u    │  │
│  └──────────┘ └──────────┘    │  │ Subtotal $6.000│  │
│  ┌──────────┐ ┌──────────┐    │  └───────────────┘  │
│  │ Producto 3│ │ Producto 4│   │  ┌───────────────┐  │
│  │ ...       │ │ ...       │   │  │ Prod B  [− 1 +]│  │
│  └──────────┘ └──────────┘    │  │ ...          │  │
│  ... (scroll vertical)        │  └───────────────┘  │
│                                │  ─────────────────  │
│                                │  Subtotal    $8.500 │
│                                │  [Limpiar carrito]  │
│                                │  [Confirmar compra] │
└────────────────────────────────┴─────────────────────┘

Modal (cuando se abre):
┌──────────────────────────────────────────────────────┐
│               [Overlay semitransparente]              │
│        ┌─────────────────────────────┐               │
│        │  Resumen de tu compra       │               │
│        │  ┌─────────────────────────┐│               │
│        │  │ Producto  Cant.  P.Unit ││               │
│        │  │ Pan      2      $1.500  ││               │
│        │  │ Queso    1      $3.500  ││               │
│        │  └─────────────────────────┘│               │
│        │  Total general      $6.500  │               │
│        │  ¿Deseas confirmar tu compra?│               │
│        │  [Cancelar]   [Confirmar]   │               │
│        └─────────────────────────────┘               │
└──────────────────────────────────────────────────────┘
```

## Estructura de la aplicación

La aplicación sigue una arquitectura de **tres capas** con separación clara de responsabilidades:

```
index.html        ← Estructura semántica, contenedores y carga de scripts
    │
    ├── css/styles.css     ← Layout CSS Grid, paleta, animaciones, touch targets
    │
    └── js/
        ├── data.js        ← Catálogo de productos (fuente de verdad inmutable)
        ├── cart.js        ← Estado del carrito (Map, IIFE, API pública)
        ├── ui.js          ← Renderizado del DOM (IIFE, solo lectura de estado)
        └── app.js         ← Orquestador (event delegation, inicialización)
```

**Flujo de datos:**

```
[data.js] PRODUCTOS (constante)
     │
     ▼
[cart.js] Cart (Map<productId, quantity>)
     │         ▲
     │ lectura  │ mutación (agregar, quitar, eliminar, limpiar)
     ▼         │
[ui.js] UI.renderizarGrilla() / renderizarCarrito()
     │
     ▼
[app.js] Event listeners → Cart.mutacion() → UI.renderizarTodo()
```

## Ejemplos de uso paso a paso

### Ejemplo 1: Compra de pan

1. Al abrir la aplicación, se muestra la grilla con los 12 productos. El carrito está vacío y muestra _"Tu carrito está vacío"_.
2. El usuario encuentra **"Pan Artesanal"** ($1.500) y presiona el botón **"Agregar al carrito"**.
3. Inmediatamente:
   - El botón cambia a un control **− 1 +**.
   - El panel del carrito muestra _"Pan Artesanal — $1.500 c/u"_ con subtotal **$1.500**.
   - El contador del header cambia de **0** a **1** con animación.
   - El total general muestra **$1.500**.
   - El botón _"Confirmar compra"_ se habilita.
4. El usuario presiona **+** dos veces para llevar 3 panes. El control muestra **− 3 +** y el subtotal en el carrito es **$4.500**.
5. El usuario presiona **"Confirmar compra"**.
6. Aparece el modal con la tabla resumen:

   | Producto | Cant. | P. Unit. | Subtotal |
   |----------|-------|----------|----------|
   | Pan Artesanal | 3 | $1.500 | $4.500 |
   | **Total general** | | | **$4.500** |

7. El usuario presiona **"Confirmar"** en el modal.
8. Se muestra la animación de check verde _"¡Compra confirmada!"_ durante 1.8 segundos.
9. El carrito se vacía, la grilla se restaura y aparece un toast verde: _"¡Compra confirmada! Gracias por tu pedido."_

### Ejemplo 2: Compra múltiple con modificación

1. El usuario agrega **"Queso Fresco"** ($3.500) y **"Miel de Abeja"** ($4.500) al carrito.
2. Total actual: **$8.000** (2 productos).
3. Decide que solo quiere 1 queso. Presiona el botón **×** junto al queso en el panel del carrito.
4. El queso desaparece del carrito. Total actual: **$4.500** (1 producto).
5. Agrega **"Galletas de Avena"** ($1.800) y las incrementa a 3 unidades.
6. Total actual: **$9.900** (2 productos: Miel ×1 + Galletas ×3).
7. Confirma la compra y finaliza.

### Ejemplo 3: Limpiar carrito

1. El usuario ha agregado varios productos. Total: **$12.300**.
2. Cambia de opinión y presiona **"Limpiar carrito"**.
3. Aparece un toast verde: _"Carrito vaciado"_.
4. El carrito vuelve al estado _"Tu carrito está vacío"_, el total es **$0**, y todas las tarjetas de producto muestran el botón _"Agregar al carrito"_.

### Ejemplo 4: Carrito vacío

1. El usuario presiona **"Confirmar compra"** cuando el carrito está vacío.
2. El botón de confirmar está deshabilitado (color gris, no responde a clics).
3. Si el usuario presiona **"Limpiar carrito"** con el carrito vacío, aparece un toast: _"El carrito ya está vacío"_.

## Configuración del viewport y resolución

La aplicación está configurada para una resolución fija de **1080 x 1920 píxeles**, típica de pantallas táctiles verticales para tótems de autoatención.

```html
<meta name="viewport" content="width=1080, height=1920, initial-scale=1.0, user-scalable=no">
```

| Propiedad | Valor | Descripción |
|-----------|-------|-------------|
| `width` | `1080` | Ancho de viewport fijo en píxeles CSS |
| `height` | `1920` | Alto de viewport fijo en píxeles CSS |
| `initial-scale` | `1.0` | Sin zoom inicial |
| `user-scalable` | `no` | El usuario no puede hacer zoom (pantalla táctil, modo kiosko) |

La hoja de estilos también fija las dimensiones del `body`:

```css
body {
  width: 1080px;
  height: 1920px;
  overflow: hidden;
}
```

Esto garantiza que la experiencia visual sea consistente en el hardware del tótem. Si se desea probar en un monitor convencional, se recomienda usar las herramientas de desarrollo del navegador y configurar el modo responsive a 1080×1920.

## Tecnologías utilizadas

| Tecnología | Uso |
|------------|-----|
| **HTML5** | Estructura semántica de la página, meta viewport, SVG inline para iconos |
| **CSS3** | CSS Grid (layout principal), Flexbox (componentes), animaciones `@keyframes`, transiciones, scrollbar personalizado |
| **JavaScript (ES5/ES6)** | Lógica de carrito (patrón IIFE), manipulación del DOM, delegación de eventos, `Map` para estado interno |
| **SVG inline** | Todos los iconos (carrito, basurero, check, etc.) están embebidos como SVG en el HTML y JS |
| **picsum.photos** | Imágenes placeholder para los 12 productos (con seed fijo para consistencia visual) |

**Cero dependencias externas:** No se utiliza ningún framework, librería, CDN, ni gestor de paquetes. Todo es HTML, CSS y JavaScript puro.

## Estructura de archivos

```
TotemCarrito/
│
├── index.html                # Punto de entrada. Estructura HTML con
│                             #   header, grilla de productos, panel
│                             #   de carrito, modal y toast container.
│
├── css/
│   └── styles.css            # Hoja de estilos completa (~930 líneas).
│                             #   Incluye reset, layout Grid, tarjetas,
│                             #   panel carrito, modal, toast, animaciones.
│
├── js/
│   ├── data.js               # Catálogo inmutable de 12 productos.
│   │                         #   Constante PRODUCTOS (Object.freeze).
│   │
│   ├── cart.js               # Gestión del carrito (IIFE, ~192 líneas).
│   │                         #   API: agregar, quitar, eliminar, limpiar,
│   │                         #   obtenerItems, obtenerTotalGeneral, etc.
│   │
│   ├── ui.js                 # Renderizado del DOM (IIFE, ~520 líneas).
│   │                         #   Genera HTML, maneja errores de imagen,
│   │                         #   renderiza modal, toast y animación éxito.
│   │
│   └── app.js                # Orquestador (IIFE, ~266 líneas).
│                             #   Inicialización, delegación de eventos,
│                             #   coordinación entre Cart y UI.
│
├── docs/
│   ├── datasheet.md          # Documentación de usuario (esta guía)
│   └── developer.md          # Documentación para desarrolladores
│
├── .gitignore                # Exclusiones de Git
├── PLAN.md                   # Especificación y diseño técnico original
├── AUDIT_REPORT.md           # Informe de auditoría de código
└── README.md                 # Este archivo
```

### Orden de carga de scripts

Los scripts se cargan al final del `<body>` en orden de dependencia:

```
1. data.js    →  Define PRODUCTOS (variable global)
2. cart.js    →  Usa PRODUCTOS para calcular precios
3. ui.js      →  Usa Cart y PRODUCTOS para renderizar
4. app.js     →  Usa Cart y UI para orquestar la aplicación
```

## Paleta de colores

La paleta utiliza tonos **teal** (verde azulado) como color primario, combinados con una base neutra cálida (off-white), transmitiendo una sensación de producto natural, fresco y artesanal.

| Rol | Código | Nombre | Muestra |
|-----|--------|--------|---------|
| **Fondo principal** | `#f9f7f4` | Off-white cálido | 🟆 |
| **Superficie (tarjetas, panel, modal)** | `#ffffff` | Blanco | ⬜ |
| **Texto principal** | `#1e293b` | Slate-800 | ⬛ |
| **Texto secundario** | `#64748b` | Slate-500 | 🔘 |
| **Acento primario** | `#0f766e` | Teal-700 | 🟩 |
| **Acento hover** | `#0d9488` | Teal-600 | 🟢 |
| **Éxito** | `#16a34a` | Green-600 | 🟢 |
| **Error / Peligro** | `#dc2626` | Red-600 | 🔴 |
| **Bordes** | `#e2e8f0` | Slate-200 | ◽ |
| **Fondo modal overlay** | `rgba(15,23,42,0.6)` | Negro translúcido | 🌑 |
| **Header (gradiente)** | `#0f766e → #0d9488` | Teal 700 → 600 | 🟦 |

### Tipografía

- **Familia:** `'Segoe UI', system-ui, -apple-system, sans-serif`
- **Tamaños:** desde `0.75rem` (categorías) hasta `1.75rem` (título del header y total en modal)
- **Pesos:** 400 (regular), 500 (medium), 600 (semibold), 700 (bold)

## Advertencias y precauciones

### Requisitos de navegador

- **Navegador moderno requerido:** Se necesita un navegador basado en Chromium (Chrome/Edge 80+), Firefox 75+ o Safari 13+. Se utilizan características como CSS Grid, `Map`, `Object.freeze` y template literals.
- **Sin soporte para Internet Explorer 11:** Este proyecto no es compatible con IE11 ni navegadores obsoletos.

### Requisitos de resolución

- **Resolución fija 1080×1920:** La interfaz está diseñada exclusivamente para esta resolución en orientación vertical. En pantallas más pequeñas o con diferente relación de aspecto, la interfaz puede no mostrarse correctamente. Para pruebas en monitor de escritorio, configure el navegador en modo responsive a 1080×1920.

### Requisitos de conexión

- **Las imágenes requieren conexión a internet:** Las imágenes de los productos se obtienen de `https://picsum.photos`. Sin conexión a internet, las imágenes no se mostrarán y se sustituirán por un placeholder con las iniciales del producto en un recuadro gris claro con degradado.
- **Toda la funcionalidad principal (HTML, CSS, JS) funciona sin conexión.** Solo las imágenes se ven afectadas.

### Modo kiosko

- **Zoom deshabilitado:** El meta viewport tiene `user-scalable=no`. La aplicación está pensada para ejecutarse en un navegador en modo kiosko (pantalla completa sin barras de navegación).
- **Sin persistencia de datos:** Al recargar la página, el carrito se vacía. No se utiliza `localStorage` ni `sessionStorage`. Si se requiere persistencia, debe implementarse como mejora futura.

### Observaciones adicionales

- **Límite de 99 unidades por producto:** No se pueden agregar más de 99 unidades de un mismo producto.
- **Sin integración con pagos:** El botón "Confirmar" del modal solo muestra una animación de éxito y limpia el carrito. Es una simulación. En producción debe integrarse con un sistema de pago o pedido.
- **Moneda:** Todos los precios están en pesos chilenos (CLP) con formato `$X.XXX` (punto como separador de miles).

---

## Créditos

**TotemCarrito** — Aplicación de carrito de compras para tótem de autoatención.

| Rol | Detalle |
|-----|---------|
| **Stack** | HTML5 + CSS3 + JavaScript (ES5/ES6) |
| **Arquitectura** | 3 capas: datos, estado y UI — con patrón IIFE para encapsulamiento |
| **Diseño visual** | Paleta teal elegante, tipografía del sistema, iconos SVG inline |
| **Optimización** | Touch targets ≥ 48 px (WCAG 2.1), delegación de eventos, renderizado simplificado |

---

*Documentación generada en junio de 2026. Para documentación de usuario detallada, vea `docs/datasheet.md`. Para documentación técnica del código fuente, vea `docs/developer.md`.*
