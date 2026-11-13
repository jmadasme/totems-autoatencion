# Datasheet — Tótem de autoatención Getnet IM30

**Documentación de usuario y especificaciones técnicas del tótem.**

| Versión | Fecha | Estado |
|---|---|---|
| 1.0.0 | 2026-09-14 | Aprobado (auditoría ciclo 3, 0 incidencias) |

---

## 1. Qué hace el tótem

El tótem es un **kiosco de autoatención** que permite al cliente:

1. Elegir productos del catálogo (bebidas y snacks) en una **pantalla táctil**.
2. Armar un carrito y ver el total en tiempo real.
3. Pagar con tarjeta **directamente en la máquina de cobro PAX IM30 de Getnet** (contact o
   contactless), conectada al tótem por **USB/serie**.
4. Recibir un **comprobante digital** (en pantalla y descargable en PDF).
5. Consultar el **historial de ventas** y re-emitir comprobantes.

El tótem está pensado para operación **sin operador**: el cliente se atiende solo y el sistema
vuelve a la pantalla de bienvenida tras un periodo de inactividad.

---

## 2. Operación de la pantalla táctil

### 2.1 Pantalla de bienvenida (atractor)

- Muestra el branding del tótem y el mensaje **"Toque la pantalla para comenzar"**.
- Al tocar cualquier parte, se abre el catálogo.
- Si no se usa durante el tiempo de inactividad configurado (por defecto **60 s**) y no hay una
  venta en curso, el tótem vuelve aquí y **descarta el carrito**.

### 2.2 Catálogo

- Dos categorías con pestañas: **Bebidas** 🥤 y **Snacks** 🍫.
- Cada producto es una tarjeta táctil con ícono, nombre y precio; tocar la tarjeta lo agrega al
  carrito.
- El panel derecho (Tu pedido) muestra los items agregados, cantidades y el **total en vivo**.
- Controles del carrito:
  - `+` / `−` para cambiar la cantidad (máximo 99 unidades por producto).
  - **Vaciar** para limpiar el carrito.
  - **Pagar** para iniciar el cobro (se habilita con al menos un item).
  - **Historial de ventas** para ver ventas anteriores.

### 2.3 Pago en curso

- La pantalla muestra **"Acerque o inserte su tarjeta"** con el monto a pagar y un indicador de
  progreso.
- El cliente opera **directamente el PAX IM30**: acercar tarjeta contactless o insertar en el lector
  EMV.
- El botón **Cancelar** permite abortar antes de la aprobación (no factura).

### 2.4 Resultado

| Estado | Pantalla | Acciones |
|---|---|---|
| ✅ Aprobado | "Pago aprobado" + código de autorización | **Ver comprobante** · **Nueva venta** |
| ❌ Rechazado | "Pago rechazado" + motivo (p. ej. `REJECTED (code=5)`) | **Reintentar** · **Nueva venta** |
| ⏱️ Tiempo agotado | "No se detectó la tarjeta a tiempo" | **Reintentar** (previa reconciliación automática) |
| 🚫 Cancelado | "La operación fue cancelada" | **Reintentar** · **Nueva venta** |
| ⚠️ Error | "Ocurrió un error inesperado" + detalle | **Reintentar** · **Nueva venta** |

> **Importante:** si una operación previa fue ambigua (timeout/cancelación/error durante el cobro)
> y la reversión automática **no** pudo completarse, el sistema **bloqueará el reintento** para
> evitar el doble cobro. Habrá que revisar manualmente el terminal y el historial antes de continuar
> (el reintento devuelve HTTP 409 y en la UI se muestra el aviso).

### 2.5 Comprobante

- Pantalla con: **Folio** (ID de orden), **Estado**, **Fecha** (`RealDate`), **Terminal**
  (`TerminalId`), **Comercio** (`CommerceCode`), **Autorización** (`AuthorizationCode`), código de
  respuesta (`Code`/`Message`), detalle de items (producto, cantidad, precio unitario, subtotal) y
  **TOTAL**.
- Botones: **Descargar PDF** y **Nueva venta**.
- El comprobante puede **re-emitirse** (idempotente) desde el historial.

### 2.6 Historial

- Lista las últimas **50 ventas** (folio, monto, estado, fecha).
- Tocar una venta abre su comprobante (reemisión).

---

## 3. Especificaciones técnicas

### 3.1 Tótem / equipo anfitrión

| Parámetro | Valor |
|---|---|
| Sistema anfitrión | Notebook/PC Ubuntu 24.04.5 LTS x86_64 (kernel 7.0.0-31) con pantalla táctil |
| Rol | Sistema de automatización que dispara operaciones de pago (host) |
| Entrada | Pantalla táctil + navegador en modo kiosco |
| Frontend | HTML/CSS/JavaScript (vanilla, sin build) |

### 3.2 Máquina de cobro PAX IM30 de Getnet

| Parámetro | Valor |
|---|---|
| Fabricante / equipo | PAX **IM30** (Getnet) |
| Plataforma | Android / PayDroid orientado a **unattended** (vending, EV charging) |
| `idVendor` / `idProduct` | `0x2fb8` / `0x225e` |
| Serial | `1640353821` |
| `bcdDevice` | `4.40` |
| Ruta sysfs | `/sys/bus/usb/devices/1-2/` |
| Lector | EMV contact + contactless (NFC) |
| Impresora integrada | **No se utiliza** (comprobante digital) |
| Interfaces USB | 3 × CDC-ACM: `if00` (ttyACM0, AT), `if02` (ttyACM1, datos), `if04` (ttyACM2, datos) |
| Configuración serie | **57600 baud, 8N1**, sin flow control |
| Integración | Integrated POS — SDK USB/Serial (`CreateUsb`), fallback HTTP (`CreateHttp`) y Cloud2Cloud |

### 3.3 Backend

| Parámetro | Valor |
|---|---|
| Lenguaje | Python 3.12 |
| Framework | FastAPI + uvicorn (ASGI) |
| HTTP binding por defecto | `0.0.0.0:8000` |
| Persistencia | SQLite (`data/orders.db`) · tablas `orders`, `transactions` |
| Comprobante | HTML (Jinja2) + PDF (ReportLab, A4) |
| Serie | `pyserial`, autodetección por `/dev/serial/by-id/usb-PAX_IM30_*` |

### 3.4 Montos y moneda

- Moneda: **CLP** (peso chileno, sin decimales).
- `Amount` en unidades menores: **1 unidad = $1 CLP** (ej. `10000` = `$10.000`).
- Rango válido por orden: **1 a 999.999 CLP** (configurable).
- Máximo 99 unidades por producto en el carrito.

---

## 4. Dependencias requeridas

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

| Paquete | Versión | Propósito |
|---|---|---|
| `fastapi` | ≥0.115 | Backend y API REST |
| `uvicorn[standard]` | ≥0.30 | Servidor ASGI |
| `pyserial` | ≥3.5 | Comunicación serie con el IM30 |
| `jinja2` | ≥3.1 | Plantilla HTML del comprobante |
| `reportlab` | ≥4.0 | Generación de PDF |
| `python-dotenv` | ≥1.0 | Carga de `.env` |
| `pydantic` | ≥2.7 | Modelos y validación |
| `pydantic-settings` | ≥2.2 | Configuración tipada (opcional) |
| `httpx` | ≥0.27 | Cliente HTTP/HTTPS (conectores http/cloud) |
| `PyYAML` | ≥6.0 | Carga de `config.yaml` |
| `pytest` | ≥8.0 | Pruebas |
| `pytest-asyncio` | ≥0.23 | Pruebas async |

---

## 5. Guía rápida de solución de problemas

| Problema | Causa probable | Solución |
|---|---|---|
| **El pago no se detecta / tarjeta ignorada** | Terminal no conectado, puerto equivocado o ModemManager ocupando el puerto | Ver `GET /api/terminal/status` y `GET /api/terminal/ports`. Asegurar cable USB y que aparezca `PAX IM30`. Usar `if02`/`if04`; deshabilitar ModemManager si usas `ACM0`. |
| **"Device or resource busy" al abrir el puerto** | ModemManager u otro proceso usa `/dev/ttyACM0` | Usar `/dev/ttyACM1`/`/dev/ttyACM2` (`GETNET_SERIAL_PORT`), o regla udev para excluir ModemManager de `/dev/ttyACM*`. |
| **Terminal sin conexión / polling falla** | Cable desconectado, terminal apagado o Conector en `sandbox`/`production` sin credenciales | Revisar el cable y la energía del IM30; verificar `.env` con credenciales Getnet y `GETNET_MODE`; probar primero `simulation`. |
| **El comprobante no imprime** | Diseño intencional: no hay impresora térmica | El comprobante es digital: vista en pantalla + **Descargar PDF**. Buscar `comprobante-<ID>.pdf`. |
| **Timeout esperando la tarjeta** | El cliente tardó más de `ORDER_TIMEOUT_SECONDS`; el terminal no detectó la tarjeta | La operación se marca ambigua y se intenta reversión automática. Reintentar tras reconciliación; si el reintento da 409, revisar el terminal manualmente. |
| **Reintento bloqueado (409)** | Operación previa ambigua **sin reconciliar** (la reversión falló) | Revisar el historial/terminal; verificar si el cargo se autorizó. La orden queda bloqueada a propósito para evitar doble cobro. |
| **Pago rechazado** | Tarjeta sin fondos, bloqueada o datos inválidos | Ver el motivo en pantalla/`GET /api/orders/{id}/status` (`Code`/`Message`). Reintentar con otra tarjeta. |
| **La UI no carga** | Servidor caído o puerto equivocado | `systemctl status totem-getnet` (si usas systemd) o lanzar `./run.sh`; abrir `http://localhost:8000`. |
| **Ventas no aparecen en el historial** | Base borrada o `DB_PATH` distinto | El historial se persiste en SQLite (`data/orders.db`); no borrar `data/`. |
| **HTTP 502 en reembolso** | Polling falló o el refund fue rechazado por el terminal | Verificar conexión del terminal y el código del reembolso en `transactions`. |
| **Modo cloud muy lento** | Cloud2Cloud puede tardar hasta ~5 min | Es esperado: el timeout de venta en cloud es `max(orden, 300s)`. No cortar el proceso. |
| **Errores raros de framing en USB** | Protocolo serie propietario aún no homologado | En modo real, reemplazar el sobre JSON/framing por el SDK oficial de Getnet (ver `docs/developer.md`). |

---

## 6. Tabla de compatibilidad con modos de integración

| Modo / transport | Hardware necesario | Credenciales | Dónde corre el cobro | Uso recomendado | Estado |
|---|---|---|---|---|---|
| **Simulación** (`SimulatedConnector`) | Ninguno | Ninguna | Local (sin terminal) | Desarrollo, demos, CI | ✅ Funcional inmediato |
| **USB / Serial** (`UsbConnector` — Integrated POS `CreateUsb`) | PAX IM30 por cable USB (interfaces CDC-ACM) | Terminal/Merchant/Commerce codes | En el IM30 (el cliente opera la tarjeta allí) | Tótem físico con cable | ⚠️ Requiere homologación + Connector App; framing debe sustituirse por el SDK oficial |
| **HTTP** (`HttpConnector` — Integrated POS `CreateHttp`) | Terminal o servidor Getnet en la misma red | Terminal/Merchant/Commerce codes | En el dispositivo/servidor HTTP local | Fallback por red local | ⚠️ Requiere homologación/env point real |
| **Cloud2Cloud** (`CloudConnector` — `CreateCloud`) | Ninguno local (terminal remoto de Getnet) | URL cloud + API key/client-id/secret | En la nube Getnet (terminal remoto asignado) | Tótem sin cable, terminal remoto | ⚠️ Requiere credenciales Cloud2Cloud; timeout ~300 s |

**Forma de elegir:**
1. `GETNET_MODE=simulation` para desarrollo/pruebas (sin credenciales).
2. `GETNET_MODE=sandbox` + `GETNET_CONNECTOR=usb` para homologar contra tu PAX IM30.
3. `GETNET_MODE=production` + el conector seleccionado al operar en producción.

---

## 7. Datos de contacto / soporte

- Credenciales y terminal: **Getnet** (comercial y soporte técnico; homologación de Integrated POS).
- Operación y despliegue del tótem: administrador de TI del local.
- Documentación técnica avanzada: [docs/developer.md](developer.md).