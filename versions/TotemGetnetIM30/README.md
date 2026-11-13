# 🛒 Tótem Getnet IM30 — Autoatención con cobro en PAX IM30

Tótem de **autoatención** (kiosco de pantalla táctil) que vende bebidas y snacks cobrando con la
**máquina de cobro PAX IM30 de Getnet** conectada por cable **USB/serie**, usando la integración
**Integrated POS (SDK USB/Serial)** con fallback **HTTP** y **Cloud2Cloud**, más un **modo
simulación** que permite probar todo el flujo sin hardware ni credenciales.

| Componente | Tecnología |
|---|---|
| Backend | Python 3.12 + **FastAPI** / uvicorn |
| Frontend táctil | SPA ligera **HTML/CSS/JS** (sin build) servida por el mismo proceso |
| Máquina de cobro | **PAX IM30 de Getnet** (`2fb8:225e`, serial `1640353821`) |
| Transporte de pago | Integrated POS: **USB/Serial** (primario), **HTTP** (fallback) y **Cloud2Cloud** |
| Comunicación serie | `pyserial` · 57600 8N1 · framing configurable |
| Persistencia | SQLite (`data/orders.db`) |
| Comprobante | Digital: **pantalla (HTML) + PDF (ReportLab)** |
| Estado | ✅ 51 tests en verde · Auditoría ciclo 3 aprobada (0 incidencias) |

---

## Índice

1. [Principio de funcionamiento](#principio-de-funcionamiento)
2. [Forma de operar — secuencia de compra](#forma-de-operar--secuencia-de-compra-en-el-tótem)
3. [Diagrama de conexión: tótem ↔ IM30](#diagrama-de-conexión-tótem--im30)
4. [Despliegue](#despliegue)
5. [Modo sandbox / homologación y producción](#modo-sandbox--homologación-y-producción)
6. [Ejemplos de uso](#ejemplos-de-uso)
7. [Advertencias y precauciones](#advertencias-y-precauciones)
8. [Estructura del repositorio](#estructura-del-repositorio)
9. [Documentación adicional](#documentación-adicional)

---

## Principio de funcionamiento

El tótem es un **sistema de automatización** (host con pantalla táctil) que presenta un catálogo,
arma un carrito y dispara operaciones de pago sobre el terminal **PAX IM30 de Getnet**. El IM30 es
un terminal **Android/PayDroid orientado a *unattended*** (vending, EV charging) con lector EMV
contact/contactless; en este proyecto **no se usa su impresora térmica**: el comprobante es 100 %
digital (pantalla + PDF).

Toda venta sigue el **ciclo de vida Integrated POS**:

```
create()  →  polling()  →  sale()/refund()  →  close()
```

1. **`create()`** — abre el conector (abre el puerto serie `pyserial`, o inicializa el cliente
   HTTP/HTTPS) y valida conectividad con el terminal mediante `Polling`. Un `Code=0` significa
   terminal listo.
2. **`polling()`** — consulta el estado/health del terminal (se valida en `create()` para todos los
   conectores).
3. **`sale()`** — envía `SaleRequest` con `Amount` (en **unidades menores**: CLP no tiene
   decimales, `10000 = $10.000`), `SaleType=Card`, `Currency=CLP` y `OrderId`. El terminal procesa
   y responde un `SaleResult` con `Code`, `Message`, `AuthorizationCode`, `TerminalId`,
   `CommerceCode`, `RealDate`, `AccountingDate`, etc.
4. **`close()`** — libera el conector (cierra el puerto serie/cliente HTTP). La instancia **no se
   reutiliza**: cada orden usa un conector nuevo.

La orden pasa por una **máquina de estados** con idempotencia y reconciliación ante casos ambiguos:

```
pending → charging → paid → emitted
              │   └─→ failed | timeout | cancelled | error
```

- Una orden **solo puede pagarse una vez** (`charging → paid` es único; `paid → emitted` es
  idempotente para re-emitir comprobantes).
- Ante **timeout, cancelación o error de transporte** durante `charging`, la operación es
  **ambigua** (el terminal pudo autorizar aunque la respuesta se haya perdido): el sistema marca la
  orden `ambiguous`, intenta una **reversión (refund/void)** con un conector nuevo y registra el
  resultado. Si la reversión falla, el reintento queda **bloqueado (HTTP 409)** hasta revisión
  manual, evitando el doble cobro.

### Modos de integración

El transporte se elige con `GETNET_MODE` / `GETNET_CONNECTOR` y se construye con la factory
`create_connector()`:

| Modo | Conector | Cuándo usarlo |
|---|---|---|
| `GETNET_MODE=simulation` | `SimulatedConnector` | Desarrollo/pruebas **sin hardware ni credenciales**. Emula `Polling OK` y `SaleResult` (aprobado/rechazado/timeout/error según configuración). **Forzado** cuando `mode=simulation`. |
| `GETNET_MODE=sandbox|production` + `GETNET_CONNECTOR=usb` | `UsbConnector` | **Integrated POS SDK USB/Serial** (`CreateUsb`) contra el puerto serie del IM30. Primario para tótem físico. |
| `GETNET_MODE=sandbox|production` + `GETNET_CONNECTOR=http` | `HttpConnector` | **Integrated POS por HTTP** (`CreateHttp`) contra un servidor/terminal en la misma red (`GETNET_HTTP_HOST:GETNET_HTTP_PORT`, por defecto `127.0.0.1:8080`). Fallback sobre red local. |
| `GETNET_MODE=sandbox|production` + `GETNET_CONNECTOR=cloud` | `CloudConnector` | **Cloud2Cloud** (`CreateCloud`) vía HTTPS contra la nube Getnet (`GETNET_CLOUD_URL` + API keys). Timeout largo (~300 s) porque el terminal remoto puede tardar hasta ~5 min. |
| `GETNET_MODE=sandbox|production` + `GETNET_CONNECTOR=app2app` | `App2AppConnector` | **App2App (Intents Android vía ADB)** contra la app de pagos de Getnet ya instalada en el IM30 (`cl.getnet.payment.prod2`). No requiere SDK. Detalles abajo. |

#### Modo App2App (`GETNET_CONNECTOR=app2app`)

Dispara la actividad `cl.getnet.payment.ApiActivity` con `adb shell am start` y captura la
respuesta desde `logcat` (tag `ApiActivity`). Sin SDK propietario ni Connector App.

```bash
# .env
GETNET_MODE=production
GETNET_CONNECTOR=app2app
GETNET_ADB_SERIAL=            # vacío = autodetecta con `adb devices`
GETNET_TERMINAL_ID=AR001P0B   # requerido: el terminal debe estar PROVISIONADO (TID)
```

Pre-requisitos: `adb` disponible en el host, IM30 conectado por USB (`adb devices` → `device`),
app `cl.getnet.payment.prod2` instalada y **terminal provisionado por Getnet (TID/TMS)**. Sin TID
la app no procesa operaciones y el conector **degrada a simulación** de forma transparente
(se refleja en el estado y en `SaleResult.raw["App2AppFallback"]`). Contrato completo en
`docs/apk_dump/APP2APP_INTEGRATION.md`.

> **Importante (protocolo propietario):** el protocolo serie exacto de Getnet Integrated POS no es
> público. La capa USB usa `serial_im30.SerialTransport` con **framing configurable**
> (delimitadores, largo y checksum definidos en `config.yaml`) y un sobre JSON de referencia. Para
> operar contra hardware homologado hay que sustituir `_encode_operation`/`_decode_response` en
> `UsbConnector` por el framing/SDK oficial de Getnet. El **modo simulación no depende de este
> framing** y es totalmente funcional.

---

## Forma de operar — secuencia de compra en el tótem

1. **Pantalla de bienvenida (atractor):** el tótem muestra "Toque la pantalla para comenzar".
2. **Catálogo:** al tocar la pantalla se muestran las categorías **Bebidas** 🥤 y **Snacks** 🍫 con
   sus productos y precios en CLP.
3. **Carrito:** tocar un producto lo agrega al carrito (panel derecho). Se puede cambiar la
   cantidad con `+`/`−`, vaciar el carrito y ver el **total en vivo**. Los montos se validan en el
   backend (1 a 999.999 CLP).
4. **Pagar:** tocar **Pagar** crea una orden (`pending`) y dispara el cobro.
5. **Espera de pago:** la pantalla muestra "Acerque o inserte su tarjeta" y el monto. El cliente
   acerca/inserta la tarjeta en el **PAX IM30**.
6. **Resultado:**
   - ✅ **Aprobado** (`Code=0`, `APPROVED`): pantalla de éxito con código de autorización y botón
     **Ver comprobante**.
   - ❌ **Rechazado / timeout / cancelado / error:** pantalla de error con motivo y botón
     **Reintentar** (se reutiliza la misma orden, salvo bloqueo por ambigüedad sin reconciliar).
7. **Comprobante:** vista en pantalla con folio, fecha, terminal, autorización, comercio, items y
   total. Botones **Descargar PDF** y **Nueva venta**. Se puede **re-emitir** desde el historial.
8. **Inactividad:** tras 60 s sin interacción y sin orden en curso, el tótem vuelve al atractor y
   descarta el carrito.

El historial de ventas está disponible desde el botón **"Historial de ventas"** del catálogo.

---

## Diagrama de conexión: tótem ↔ IM30

### Topología física (modo USB/Serial — el principal)

```
          ┌────────────────────────────────────────────────────┐
          │                     TÓTEM (host)                   │
          │  Ubuntu 24.04 x86_64 · notebook con pantalla táctil│
          │                                                    │
          │  app.py / FastAPI :8000  ◄── UI web táctil (HTML)  │
          │  payments_getnet.UsbConnector (Integrated POS SDK  │
          │    USB/Serial — CreateUsb)                         │
          │  serial_im30.SerialTransport (pyserial)            │
          │                                                    │
          │  /dev/serial/by-id/usb-PAX_IM30_1640353821-*       │
          └───────────────┬────────────────────────────────────┘
                          │  CABLE USB  (3 interfaces CDC-ACM)
                          │
   ┌──────────────────────┼────────────────────────────────────┐
   │                      ▼                                    │
   │             ┌─────────────────────┐                       │
   │             │   PAX IM30 Getnet   │  idVendor=0x2fb8      │
   │             │   (Android/PayDroid,│  idProduct=0x225e     │
   │             │    unattended)      │  serial=1640353821    │
   │             └─────────────────────┘  bcdDevice 4.40       │
   │                                                           │
   │  Interfaces expuestas (sysfs /sys/bus/usb/devices/1-2/):  │
   │  ┌──────────────────────────────────────────────────────┐ │
   │  │ -if00 → /dev/ttyACM0  AT commands / posible ModemManager│ │
   │  │ -if02 → /dev/ttyACM1  DATA  · 57600 8N1 (default)    │ │
   │  │ -if04 → /dev/ttyACM2  DATA  · 57600 8N1              │ │
   │  └──────────────────────────────────────────────────────┘ │
   └────────────────────────────────────────────────────────────┘
```

- El IM30 se expone como **tres interfaces CDC-ACM**. La capa `serial_im30.py` las detecta por
  **`by-id`** (`/dev/serial/by-id/usb-PAX_IM30_1640353821-if00/-if02/-if04`) y mapea a
  `/dev/ttyACM0/1/2`.
- **Interfaz preferida: `if02` (`/dev/ttyACM1`)** a **57600 baud, 8N1, sin flow control**
  (configurable con `GETNET_SERIAL_PREFERENCE` / `GETNET_SERIAL_PORT`). Si no aparece, se usa la
  primera interfaz no-`if00`.
- El cliente **acerca o inserta la tarjeta directamente en el IM30**; el host solo envía las
  operaciones y lee las respuestas por el cable USB.
- ⚠️ **ACM0** (`if00`) suele estar ocupado por **ModemManager** (`Device or resource busy`). Si se
  necesita usar ese puerto, deshabilitar ModemManager para `/dev/ttyACM*` (regla udev). Con
  `if02`/`if04` no es necesario.
- **Error de puerto/reconexión:** si el cable se desconecta, `UsbConnector` reintenta con backoff y
  recrea el transporte. El diagnóstico live está en `GET /api/terminal/status` y
  `GET /api/terminal/ports`.

### Flujo de datos durante una venta (USB/Serial)

```
UI  ──POST /api/orders──────────►  Backend: crea orden pending (SQLite)
UI  ──POST /api/orders/{id}/pay──►  Backend: create_connector() → create() → Polling (Code=0)
                                    Backend: Sale(Amount, SaleType=Card) ──USB──► IM30
                                    Cliente acerca/inserta tarjeta en el IM30
                                    IM30 ──USB──► SaleResult (Code=0, AuthorizationCode, ...)
                                    Backend: persiste transacción → orden paid
UI (polling SSE/1s ──GET /api/orders/{id}/status)  ◄── estado actualizado
UI  ──GET /api/orders/{id}/receipt(.pdf)──►  Comprobante digital (HTML + PDF)
Backend: close()  (conector liberado; no se reutiliza)
```

### Modos alternativos de conexión

- **HTTP (fallback, misma red):** el conector habla JSON contra `http://{GETNET_HTTP_HOST}:{GETNET_HTTP_PORT}`
  (`/polling`, `/sale`, `/refund`, `/close`) — p. ej. el IM30 o un intermediario en la LAN del local.
- **Cloud2Cloud:** el conector habla JSON/HTTPS contra `GETNET_CLOUD_URL` de la nube Getnet con
  API key/client credentials (`X-Api-Key`, `X-Client-Id`, `X-Client-Secret`). Timeout ~300 s.
- **Simulación:** no hay cable ni red; `SimulatedConnector` responde localmente (`Polling OK`,
  `SaleResult` aprobado/rechazado/timeout/error).

---

## Despliegue

### Requisitos

- Python **3.12+** (`python3 --version`)
- Linux con `pyserial` (el IM30 se conecta por USB; en ACK/Windows el path de puerto cambia)
- Para modo real: terminal **PAX IM30** homologado (Connector App en modo Integrated POS),
  credenciales Getnet y permisos de lectura/escritura sobre `/dev/ttyACM*`

### 1. Clonar y crear el entorno

```bash
git clone <repo> TotemGetnetIM30
cd TotemGetnetIM30

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

### 2. Configurar variables de entorno

```bash
cp .env.example .env
# editar .env con terminal ID, merchant, API keys y modo sandbox/producción
```

Variables principales (todas documentadas en `.env.example`):

| Variable | Valores | Descripción |
|---|---|---|
| `GETNET_MODE` | `simulation` \| `sandbox` \| `production` | `simulation` fuerza el conector simulado. |
| `GETNET_CONNECTOR` | `usb` \| `http` \| `cloud` | Transporte del conector (en modo real). |
| `GETNET_TERMINAL_ID` | secreto | Terminal ID Getnet. |
| `GETNET_MERCHANT_ID` | secreto | Merchant ID Getnet. |
| `GETNET_COMMERCE_CODE` | secreto | Código de comercio Getnet. |
| `GETNET_SERIAL_PORT` | `/dev/ttyACM1` o `by-id/...` | Puerto serie (vacío = autodetección por `by-id`). |
| `GETNET_SERIAL_PREFERENCE` | `if02` \| `if04` | Interfaz preferida al autodetectar. |
| `GETNET_BAUDRATE` | `57600` | Baudrate serie. |
| `GETNET_HTTP_HOST` / `GETNET_HTTP_PORT` | — | Fallback HTTP (`CreateHttp`). |
| `GETNET_CLOUD_URL` / `GETNET_API_KEY` / `GETNET_CLIENT_ID` / `GETNET_CLIENT_SECRET` | — | Cloud2Cloud (`CreateCloud`). |
| `ORDER_TIMEOUT_SECONDS` | `120` | Timeout de espera de tarjeta. |
| `IDLE_TIMEOUT_SECONDS` | `60` | Vuelta al atractor por inactividad. |
| `DB_PATH` | `data/orders.db` | Base SQLite. |
| `APP_HOST` / `APP_PORT` | `0.0.0.0:8000` | Binding del servidor. |

### 3. Modo simulación (pruebas sin credenciales)

```bash
# En .env:
GETNET_MODE=simulation
GETNET_SIM_OUTCOME=approved      # approved | declined | timeout | error | random
GETNET_SIM_REFUND_OUTCOME=approved
GETNET_SIM_DELAY=1.5

# Ejecutar
.venv/bin/python app.py
# o
./run.sh
```

### 4. Ejecutar

```bash
# Directo con Python
.venv/bin/python app.py

# Con run.sh (crea el venv si no existe, carga .env, levanta uvicorn)
./run.sh

# O con uvicorn explícito
.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
```

Abrir la UI táctil en el tótem: `http://<host>:8000/` (por ejemplo `http://localhost:8000`).
La API vive bajo `/api/*` y los endpoints se listan en [Ejemplos de uso](#ejemplos-de-uso).

### 5. Verificar (tests)

```bash
.venv/bin/python -m pytest          # 51 tests en modo simulación
```

### 6. Arranque automático del tótem (systemd)

Para que el tótem arranque solo al encender, crea el servicio:

```bash
sudo tee /etc/systemd/system/totem-getnet.service >/dev/null <<'EOF'
[Unit]
Description=Tótem Getnet IM30 — autoatención
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=<TU_USUARIO>
WorkingDirectory=/home/<TU_USUARIO>/TotemGetnetIM30
EnvironmentFile=/home/<TU_USUARIO>/TotemGetnetIM30/.env
ExecStart=/home/<TU_USUARIO>/TotemGetnetIM30/.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now totem-getnet
sudo systemctl status totem-getnet
```

### 7. Modo kiosco (navegador a pantalla completa)

El navegador debe abrir la UI en **kiosco** y auto-recuperarse si falla. Ejemplo con Firefox:

```bash
# Sesión de un usuario dedicado del tótem
firefox --kiosk http://127.0.0.1:8000/ --no-remote
```

Opcional: crear también un servicio/autostart del navegador (por ej. en `~/.config/autostart/`
del usuario del tótem o un segundo unit systemd) para que la UI aparezca al encender.

---

## Modo sandbox / homologación y producción

```bash
# --- Homologación / sandbox ----------------------------------
cp .env.example .env
# Editar .env:
GETNET_MODE=sandbox
GETNET_CONNECTOR=usb            # o http / cloud según tu integración
GETNET_TERMINAL_ID=<TU_TERMINAL_ID>
GETNET_MERCHANT_ID=<TU_MERCHANT_ID>
GETNET_COMMERCE_CODE=<TU_COMMERCE_CODE>
GETNET_SERIAL_PORT=             # vacío → autodetección by-id (if02)
GETNET_SERIAL_PREFERENCE=if02
GETNET_BAUDRATE=57600
# (si usas cloud, completa GETNET_CLOUD_URL, GETNET_API_KEY, GETNET_CLIENT_ID, GETNET_CLIENT_SECRET)

.venv/bin/python app.py         # levanta con credenciales de sandbox

# --- Producción ----------------------------------------------
# Igual que sandbox pero:
GETNET_MODE=production
# y NUNCA subir el .env a git (está en .gitignore)
```

> Verifica antes de operar en producción:
> `GET /api/terminal/status` debe mostrar `mode=production`, el conector elegido y `polling.connected=true`.

---

## Ejemplos de uso

### Flujo de pago completo (API REST con curl)

```bash
BASE=http://127.0.0.1:8000

# 1. Health y configuración pública (sin secretos)
curl -s $BASE/api/health
curl -s $BASE/api/config

# 2. Catálogo
curl -s $BASE/api/catalog | python3 -m json.tool

# 3. Crear orden (por ejemplo 2 aguas + 1 chocolate)
curl -s -X POST $BASE/api/orders \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"product_id":"beb-agua","qty":2},{"product_id":"snk-choco","qty":1}]}'

# Salida esperada (id, estado pending y total calculado server-side):
# {
#   "id": "3F9A2C1B8E4D",
#   "status": "pending",
#   "total": 3700,
#   "currency": "CLP",
#   "items": [
#     {"product_id":"beb-agua","name":"Agua Mineral 500ml","qty":2,
#      "unit_price":1200,"subtotal":2400, ...},
#     {"product_id":"snk-choco","name":"Chocolate","qty":1,
#      "unit_price":1300,"subtotal":1300, ...}
#   ]
# }

# 4. Iniciar el pago (respuesta 202 Accepted; el cobro corre en background)
curl -s -X POST $BASE/api/orders/3F9A2C1B8E4D/pay -H 'Content-Type: application/json' -d '{}'

# En modo simulación puede forzarse el resultado por operación:
curl -s -X POST $BASE/api/orders/<ID>/pay \
  -H 'Content-Type: application/json' \
  -d '{"simulate_outcome":"approved"}'   # approved|declined|timeout|error

# 5. Consultar estado / transacción (polling de la UI, ~1 s)
curl -s $BASE/api/orders/3F9A2C1B8E4D/status | python3 -m json.tool

# Salida esperada tras aprobación (mode=simulation):
# {
#   "order": {"id":"3F9A2C1B8E4D","status":"paid","total":3700, ...},
#   "transaction": {
#     "code": 0,
#     "message": "APPROVED",
#     "terminal_id": "SIM-IM30-01",
#     "commerce_code": "DEMO0001",
#     "authorization_code": "AUTH483920",
#     "amount": 3700,
#     "real_date": "2026-09-14T10:31:00-04:00",
#     "operation_mode": "Integrated",
#     "sale_type": "Card",
#     ...
#   },
#   "charging": false
# }

# 6. Comprobante digital
curl -s $BASE/api/orders/3F9A2C1B8E4D/receipt       # HTML (marca la orden emitted)
curl -s -o comprobante.pdf $BASE/api/orders/3F9A2C1B8E4D/receipt.pdf

# 7. Cancelar (antes de aprobación) o reembolsar (tras aprobación)
curl -s -X POST $BASE/api/orders/<ID>/cancel
curl -s -X POST $BASE/api/orders/<ID>/refund -H 'Content-Type: application/json' -d '{}'

# 8. Diagnóstico del terminal
curl -s $BASE/api/terminal/status | python3 -m json.tool
curl -s $BASE/api/terminal/ports  | python3 -m json.tool
```

**Salida esperada de un cobro aprobado en modo simulación** (así se ve la transacción persistida):

```json
{
  "code": 0,
  "message": "APPROVED",
  "commerce_code": "DEMO0001",
  "terminal_id": "SIM-IM30-01",
  "authorization_code": "AUTH483920",
  "amount": 3700,
  "accounting_date": "2026-09-14T14:31:00Z",
  "real_date": "2026-09-14T10:31:00-04:00",
  "sale_type": "Card",
  "operation_mode": "Integrated",
  "original_amount": 3700,
  "approved": true
}
```

### Flujo de UI (usuario final)

1. Toque la pantalla de bienvenida → catálogo.
2. Toque "Bebidas" → "Agua Mineral 500ml" (x2) → "Snacks" → "Chocolate".
3. El panel derecho muestra el total **$3.700**; toque **Pagar**.
4. En el IM30: acerque o inserte la tarjeta. La pantalla del tótem muestra el spinner.
5. Resultado ✅ → **Ver comprobante** → **Descargar PDF**.
6. **Nueva venta** para reiniciar el ciclo.

---

## Advertencias y precauciones

- 🔒 **Credenciales:** `GETNET_TERMINAL_ID`, `GETNET_MERCHANT_ID`, `GETNET_COMMERCE_CODE` y las
  API keys de Cloud2Cloud son **secretos**. Se leen únicamente de variables de entorno (`.env`,
  que **está en `.gitignore` y nunca debe subirse al repo**). `/api/config` **no** expone estos
  valores (solo el booleano `credentials_configured`).
- ⚠️ **Protocolo propietario:** el protocolo serie exacto del Integrated POS de Getnet **no es
  público**. La implementación USB usa framing configurable + sobre JSON de referencia. Se requiere
  **homologación con Getnet** y la **Connector App** corriendo en el IM30 (modo Integrated POS)
  para operación real; hasta entonces entra el **modo simulación**.
- 💳 **Doble cobro:** el sistema lo evita con idempotencia (una orden se paga una sola vez) y
  **reconciliación**: ante timeout/cancelación/error de transporte, se intenta una reversión
  (`refund`/`void`) antes de permitir reintento. Si la reversión falla, el reintento devuelve
  **HTTP 409** y se requiere revisión manual del terminal.
- ⏱️ **Timeouts:** `ORDER_TIMEOUT_SECONDS=120` por defecto. En modo `cloud` el timeout efectivo de
  venta es `max(orden, 300s)` (el terminal remoto puede tardar ~5 min). Un timeout no es
  necesariamente un rechazo: la operación queda marcada ambigua y se reconcilia.
- 🖥️ **ModemManager:** si usas `/dev/ttyACM0` (`if00`) puede dar "Device or resource busy".
  Deshabilítalo con una regla udev o usa `if02`/`if04` (recomendado).
- 🔌 **Cable USB:** si se desconecta durante un cobro, la venta entra en estado `error`;
  `UsbConnector` reintenta con backoff y reconexión. No reinicies el proceso sin revisar el
  historial de ventas (una venta ambigua sin reconciliar bloquea el reintento).
- 🧮 **Moneda:** CLP **sin decimales**. `Amount` viaja en unidades menores: `10000` = `$10.000`.
  Los totales se calculan siempre en el servidor; el cliente solo envía `product_id` + `qty`.
- 🌐 **Exposición:** por defecto la app escucha en `0.0.0.0:8000`. En un tótem público conviene
  proteger la red / usar el kiosco en localhost con firewall (los endpoints de administración no
  tienen autenticación).
- 🧪 **Homologación vs producción:** prueba SIEMPRE en `sandbox` primero; en `production` las
  operaciones son reales y no reembolsables automáticamente sin validación del terminal.

---

## Estructura del repositorio

```
TotemGetnetIM30/
├── app.py                  # App principal FastAPI: UI, API de órdenes, orquestación del pago
├── payments_getnet.py      # Capa de integración IM30 (Connector: usb/http/cloud/simulation)
├── serial_im30.py          # Detección /dev/ttyACM* por by-id, pyserial, framing, reconexión
├── catalog.py              # Catálogo demo (bebidas/snacks, CLP)
├── orders.py               # Modelo de orden/estado/transacción + SQLite (idempotencia)
├── receipt.py              # Comprobante digital: HTML (Jinja2) + PDF (ReportLab)
├── config.py               # Configuración (env > config.yaml > defaults)
├── config.yaml             # Configuración no sensible (puertos, baudrate, timeouts, framing)
├── run.sh                  # Arranque: venv + uvicorn
├── requirements.txt        # Dependencias
├── .env.example            # Plantilla de variables sensibles (copiar a .env)
├── .gitignore              # Excluye .env, data/, *.db, *.pdf, etc.
├── ui/                     # Frontend táctil (index.html, app.js, styles.css, assets/)
├── tests/                  # 51 tests (unitarios + e2e en modo simulación)
├── data/                   # SQLite y comprobantes generados (no versionado)
├── docs/                   # Documentación: datasheet.md, developer.md
├── PLAN.md                 # Plan de implementación
└── AUDIT_REPORT.md         # Informe de auditoría (ciclo 3 aprobado)
```

---

## Documentación adicional

| Documento | Contenido |
|---|---|
| [Guía de usuario y especificaciones](docs/datasheet.md) | Qué hace el tótem, operación de la pantalla, pagos, comprobante, solución de problemas, compatibilidad de modos. |
| [Guía de desarrollo](docs/developer.md) | Arquitectura, módulos, máquina de estados, integración de pagos, framing serie, configuración, tests, extensión (agregar productos, activar producción). |

---

© 2026 · Proyecto de tótem de autoatención con cobro Integrated POS en PAX IM30 de Getnet.