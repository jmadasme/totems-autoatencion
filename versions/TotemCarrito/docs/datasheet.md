# Datasheet de Usuario — TotemCarrito

## Documentación para el operador del tótem de autoatención

---

### Índice

1. [Requisitos del sistema](#1-requisitos-del-sistema)
2. [Pantalla de inicio y navegación](#2-pantalla-de-inicio-y-navegación)
3. [Catálogo de productos](#3-catálogo-de-productos)
4. [Cómo agregar productos al carrito](#4-cómo-agregar-productos-al-carrito)
5. [Cómo modificar cantidades](#5-cómo-modificar-cantidades)
6. [Cómo eliminar productos del carrito](#6-cómo-eliminar-productos-del-carrito)
7. [Cómo limpiar el carrito completo](#7-cómo-limpiar-el-carrito-completo)
8. [Cómo confirmar una compra](#8-cómo-confirmar-una-compra)
9. [Resumen de compra (modal)](#9-resumen-de-compra-modal)
10. [Notificaciones y feedback visual](#10-notificaciones-y-feedback-visual)
11. [Solución de problemas comunes](#11-solución-de-problemas-comunes)
12. [Glosario de la interfaz](#12-glosario-de-la-interfaz)

---

## 1. Requisitos del sistema

### Hardware del tótem

| Componente | Requisito |
|------------|-----------|
| **Pantalla** | Táctil capacitiva, 1080 x 1920 píxeles, orientación vertical (retrato) |
| **Navegador** | Chromium 80+, Firefox 75+ o Safari 13+ (se recomienda Chrome/Edge en modo kiosko) |
| **Memoria RAM** | Mínimo 512 MB disponible para el navegador |
| **Conexión a internet** | Requerida para cargar las imágenes de los productos desde `picsum.photos`. Opcional para la funcionalidad del carrito. |

### Software

| Componente | Detalle |
|------------|---------|
| **Sistema operativo** | Windows 10+, Linux (Ubuntu 20.04+, Debian 11+) o Android 9+ |
| **Modo de ejecución** | Navegador en **modo kiosko** (pantalla completa, sin barras de navegación, sin cursor visible) |
| **Idioma** | Español (CL) |
| **Archivos necesarios** | `index.html`, `css/styles.css`, `js/data.js`, `js/cart.js`, `js/ui.js`, `js/app.js` |

### Configuración del navegador (modo kiosko)

Para Chrome/Chromium, ejecute:

```bash
chrome --kiosk --disable-pinch --overscroll-history-navigation=0 file:///ruta/a/TotemCarrito/index.html
```

Para Firefox:

```bash
firefox --kiosk file:///ruta/a/TotemCarrito/index.html
```

---

## 2. Pantalla de inicio y navegación

Al abrir la aplicación, verá la pantalla principal compuesta por tres zonas:

### 2.1 Barra superior (Header)

- **Izquierda:** Icono SVG de una bolsa de compras junto al texto _"Tótem de Autoatención"_.
- **Derecha:** Contador numérico de ítems en el carrito (badge circular con fondo blanco). Inicialmente muestra **0**.

### 2.2 Catálogo de productos (lado izquierdo, ~60% de la pantalla)

Muestra los 12 productos en una grilla de **2 columnas**. Haga scroll vertical hacia abajo para ver todos los productos (6 filas en total).

### 2.3 Panel del carrito (lado derecho, ~40% de la pantalla)

Muestra el estado actual del carrito. Inicialmente indica _"Tu carrito está vacío"_ con un icono de bolsa en gris claro.

El panel es **sticky**: permanece siempre visible aunque haga scroll en el catálogo.

---

## 3. Catálogo de productos

El catálogo contiene **12 productos alimenticios** organizados en 4 categorías:

| # | Producto | Precio (CLP) | Categoría |
|---|----------|-------------|-----------|
| 1 | Pan Artesanal | $1.500 | Panadería |
| 2 | Lechuga Hidropónica | $1.200 | Verduras |
| 3 | Tomate Orgánico (kg) | $2.800 | Verduras |
| 4 | Queso Fresco | $3.500 | Lácteos |
| 5 | Huevos de Campo (12u) | $3.200 | Lácteos |
| 6 | Miel de Abeja (500g) | $4.500 | Almacén |
| 7 | Aceite de Oliva (500ml) | $5.900 | Almacén |
| 8 | Mermelada de Frutilla | $2.100 | Almacén |
| 9 | Leche Entera (1L) | $1.100 | Lácteos |
| 10 | Mantequilla (250g) | $2.400 | Lácteos |
| 11 | Galletas de Avena | $1.800 | Panadería |
| 12 | Café de Grano (250g) | $3.900 | Almacén |

Cada tarjeta de producto contiene:
- **Imagen** (parte superior, 400x300 px escalada).
- **Nombre** en negrita.
- **Categoría** (etiqueta pequeña con fondo teal claro).
- **Descripción** breve en gris.
- **Precio** destacado en teal, en la parte inferior izquierda.
- **Botón de acción** en la parte inferior derecha.

---

## 4. Cómo agregar productos al carrito

### Método principal: botón "Agregar al carrito"

1. Localice el producto deseado en la grilla del catálogo.
2. Presione el botón verde **"Agregar al carrito"** (con ícono **+**).
3. Resultado inmediato:
   - El botón cambia a un **control de cantidad** con tres elementos: **−** / [cantidad] / **+**.
   - El producto aparece en el panel derecho del carrito.
   - El contador del header se incrementa en 1.
   - El total del carrito se actualiza.

### Comportamiento adicional

- Si presiona _"Agregar al carrito"_ en un producto que ya está en el carrito (por ejemplo, después de haberlo eliminado o si el control no se muestra por alguna razón), la cantidad se incrementa en 1 adicional.

---

## 5. Cómo modificar cantidades

Una vez que un producto está en el carrito, aparecen controles de cantidad tanto en la tarjeta del producto (grilla) como en el panel del carrito.

### En la grilla de productos

- **Botón + (verde):** Incrementa la cantidad en 1.
- **Botón − (verde):** Reduce la cantidad en 1. Si la cantidad llega a **0**, el producto se elimina automáticamente del carrito y la tarjeta vuelve a mostrar _"Agregar al carrito"_.

### En el panel del carrito

- **Botón +:** Incrementa la cantidad en 1. El subtotal se actualiza automáticamente.
- **Botón −:** Reduce la cantidad en 1. Si llega a 0, el producto se elimina del carrito.

### Límite de cantidad

- El límite máximo es **99 unidades** por producto.
- Al alcanzar 99 unidades, el botón **+** se deshabilita (aparece en gris y no responde a toques).
- El botón **−** sigue funcionando normalmente.

---

## 6. Cómo eliminar productos del carrito

Hay dos formas de eliminar un producto del carrito:

### Opción A: desde el panel del carrito (recomendado)

1. Localice el ítem a eliminar en la lista del panel derecho.
2. Presione el botón **×** (ícono de basurero, fondo rojo claro) ubicado a la derecha del subtotal.
3. Resultado: el ítem desaparece inmediatamente. La tarjeta del producto en la grilla vuelve a mostrar _"Agregar al carrito"_.

### Opción B: desde la grilla de productos

1. Localice la tarjeta del producto (que muestra el control − / cantidad / +).
2. Presione el botón **−** repetidamente hasta que la cantidad llegue a 0.
3. Resultado: al llegar a 1 y presionar **−** una vez más, el producto se elimina del carrito.

---

## 7. Cómo limpiar el carrito completo

Para vaciar todo el carrito de una sola vez:

1. Presione el botón rojo **"Limpiar carrito"** (con ícono de basurero) en la parte inferior del panel derecho.

2. Resultado inmediato:
   - Todos los ítems desaparecen del carrito.
   - Todas las tarjetas de producto vuelven a mostrar el botón _"Agregar al carrito"_.
   - El total del carrito vuelve a **$0**.
   - El contador del header vuelve a **0**.
   - Aparece un toast verde en la esquina inferior derecha con el mensaje _"Carrito vaciado"_ (desaparece automáticamente después de 3 segundos).

### Si el carrito ya está vacío

Si presiona _"Limpiar carrito"_ cuando no hay productos, aparece un toast informativo: _"El carrito ya está vacío"_.

---

## 8. Cómo confirmar una compra

### Paso 1: verificar el carrito

Asegúrese de que el carrito contenga al menos un producto. El botón **"Confirmar compra"** está deshabilitado (gris) si el carrito está vacío. Solo se habilita (verde teal) cuando hay al menos un ítem.

### Paso 2: abrir el resumen

Presione el botón **"Confirmar compra"** (con ícono de check ✓). Se abrirá un modal (ventana emergente) con el resumen de la compra.

### Paso 3: revisar y decidir

En el modal, revise el detalle de su compra. Tiene dos opciones:

- **Cancelar** (botón con borde gris): cierra el modal y **conserva el carrito intacto**. Puede seguir agregando o quitando productos.
- **Confirmar** (botón verde): finaliza la compra.

### Paso 4: confirmar

Al presionar **"Confirmar"**, ocurre lo siguiente en secuencia:

1. El modal se cierra.
2. Aparece una **animación de éxito**: un círculo verde con un check blanco y el mensaje _"¡Compra confirmada!"_ centrado en la pantalla (dura ~1.8 segundos).
3. El carrito se vacía automáticamente.
4. Todas las tarjetas de producto vuelven a su estado inicial.
5. Aparece un toast verde: _"¡Compra confirmada! Gracias por tu pedido."_

---

## 9. Resumen de compra (modal)

El modal de resumen es una ventana centrada que muestra toda la información de la compra antes de confirmarla.

### Contenido del modal

| Sección | Descripción |
|---------|-------------|
| **Encabezado** | Icono de check ✓ y título _"Resumen de tu compra"_ |
| **Tabla de productos** | Columnas: Producto, Cant., P. Unit., Subtotal |
| **Línea separadora** | Divisor horizontal |
| **Total general** | Monto total en formato grande y destacado ($X.XXX) |
| **Pregunta** | _"¿Deseas confirmar tu compra?"_ |
| **Botones** | _Cancelar_ (outline) y _Confirmar_ (primario) |

### Ejemplo visual del modal

```
┌─────────────────────────────────────────┐
│  ✓  Resumen de tu compra                │
├─────────────────────────────────────────┤
│  Producto            Cant.  P.Unit Subt │
│  ─────────────────────────────────────  │
│  Pan Artesanal         3    $1.500 $4.500│
│  Queso Fresco          1    $3.500 $3.500│
│  Mermelada de Frutilla 2    $2.100 $4.200│
│  ─────────────────────────────────────  │
│  Total general               $12.200   │
│                                         │
│  ¿Deseas confirmar tu compra?           │
│                                         │
│  [ Cancelar ]     [ Confirmar ]         │
└─────────────────────────────────────────┘
```

### Cerrar el modal sin confirmar

Puede cerrar el modal de dos maneras:
- Presionando el botón **"Cancelar"**.
- Presionando **fuera del modal** (en el fondo oscuro translúcido).

En ambos casos, el carrito se conserva exactamente como estaba.

---

## 10. Notificaciones y feedback visual

La aplicación proporciona feedback visual constante para que el operador sepa qué está ocurriendo.

### Tipos de notificaciones

| Tipo | Color | Situaciones |
|------|-------|-------------|
| **Toast de éxito** | Verde (`#16a34a`) | Carrito vaciado, compra confirmada |
| **Toast informativo** | Teal (`#0f766e`) | Carrito ya está vacío |
| **Toast de error** | Rojo (`#dc2626`) | (Reservado para futuras extensiones) |

### Animaciones

| Animación | Descripción |
|-----------|-------------|
| **Badge pop** | El contador del header rebota ligeramente al cambiar su valor |
| **Fade in** | El modal y los toasts aparecen con desvanecimiento progresivo |
| **Slide up** | El modal y los ítems del carrito se deslizan hacia arriba al aparecer |
| **Shake** | El botón _"Confirmar compra"_ tiembla horizontalmente si se presiona con el carrito vacío |
| **Checkmark** | El círculo verde de éxito crece desde escala 0 al confirmar una compra |
| **Scale activo** | Los botones se reducen ligeramente (`scale(0.96)`) al ser presionados, dando feedback táctil |

### Estados de botones

| Estado | Apariencia |
|--------|------------|
| **Normal** | Color completo |
| **Hover** | Color ligeramente más claro |
| **Active** | Color más oscuro + reducción de escala |
| **Disabled** | Opacidad al 50%, cursor bloqueado, color gris |

---

## 11. Solución de problemas comunes

### Problema: Las imágenes de los productos no se cargan

**Causa:** No hay conexión a internet, o el servicio `picsum.photos` no está disponible.

**Qué ocurre:** Las imágenes se reemplazan automáticamente por un recuadro gris con las iniciales del producto (por ejemplo, "PA" para Pan Artesanal, "LH" para Lechuga Hidropónica).

**Solución:**
- Verifique la conexión a internet del tótem.
- Si el tótem debe funcionar sin internet, considere reemplazar las URLs de imágenes por archivos locales. Modifique `js/data.js` y cambie la propiedad `imagen` de cada producto por una ruta relativa (ej: `"img/pan.jpg"`).

### Problema: La pantalla se ve cortada o con scroll horizontal

**Causa:** La aplicación está diseñada exclusivamente para 1080×1920 px. Si se ejecuta en una resolución diferente, el layout puede romperse.

**Solución:**
- Asegúrese de que el monitor del tótem esté configurado a 1080×1920.
- Si está probando en un monitor de escritorio, use las herramientas de desarrollo del navegador (F12) y configure el modo responsive a 1080×1920.
- En Chrome: `F12` → Toggle device toolbar → Seleccione o cree un perfil de 1080×1920.

### Problema: El botón "Confirmar compra" no responde

**Causa probable:** El carrito está vacío.

**Solución:** Agregue al menos un producto al carrito. El botón se habilitará automáticamente.

### Problema: El botón "+" de un producto no funciona

**Causa probable:** El producto ya alcanzó el límite máximo de **99 unidades**.

**Solución:** El botón aparece deshabilitado (gris). Reduzca la cantidad usando el botón **−** si desea modificar el pedido.

### Problema: La página no carga o muestra errores en consola

**Causas posibles:**
1. Navegador incompatible (se requiere Chrome 80+, Firefox 75+ o Safari 13+).
2. Los archivos JS no se cargaron en el orden correcto.
3. La ruta del proyecto es incorrecta y los archivos CSS/JS no se encuentran.

**Solución:**
- Verifique que todos los archivos estén presentes: `index.html`, `css/styles.css`, `js/data.js`, `js/cart.js`, `js/ui.js`, `js/app.js`.
- Abra la consola del navegador (F12 → Console) y revise si hay errores.
- Asegúrese de que el navegador soporte `CSS Grid`, `Map` y `Object.freeze`.

### Problema: Al recargar la página, el carrito se vacía

**Causa:** Por diseño, la aplicación no persiste el estado del carrito. Es un frontend estático sin backend ni `localStorage`.

**Solución:** Esta es una limitación conocida. Si se requiere persistencia entre recargas, debe implementarse `localStorage` en `cart.js`. Consulte la documentación de desarrollador (`docs/developer.md`) para guía de extensión.

---

## 12. Glosario de la interfaz

| Término | Descripción |
|---------|-------------|
| **Grilla de productos** | Zona izquierda que muestra el catálogo en 2 columnas con scroll vertical. |
| **Tarjeta de producto** | Cada recuadro individual con imagen, nombre, categoría, descripción, precio y botón de acción. |
| **Panel del carrito** | Zona derecha (sticky) que muestra los ítems agregados, subtotales y botones de acción. |
| **Control de cantidad** | Botones **−** / [número] / **+** que permiten modificar la cantidad de un producto en el carrito. |
| **Badge** | Contador numérico circular en el header que indica el total de ítems en el carrito. |
| **Toast** | Notificación efímera que aparece en la esquina inferior derecha y desaparece tras 3 segundos. |
| **Modal** | Ventana emergente con fondo oscuro que muestra el resumen de la compra. |
| **Backdrop** | Fondo oscuro translúcido detrás del modal. Al presionarlo, se cierra el modal. |
| **Overlay** | Capa superpuesta sobre el contenido principal (usada por el modal y la animación de éxito). |
| **Sticky** | Elemento que permanece fijo en su posición aunque se haga scroll en el resto de la página. |
| **Kiosko** | Modo de navegador a pantalla completa, sin barras de herramientas ni navegación. |

---

*Para documentación técnica del código fuente y guía de desarrollo, vea `docs/developer.md`.*
