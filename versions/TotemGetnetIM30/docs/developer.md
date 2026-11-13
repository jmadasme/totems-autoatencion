# Guía de desarrollo — Tótem Getnet IM30

Documentación técnica del código fuente: arquitectura, módulos, máquina de estados, integración de
pagos, framing serie, configuración, tests y guía de extensión.

| Versión | Fecha | Suite de tests |
|---|---|---|
| 1.0.0 | 2026-09-14 | 51 passed (modo simulación) |

---

## 1. Arquitectura de módulos

```
                        ┌────────────────────────────┐
   Navegador táctil     │          app.py            │   FastAPI (ASGI)
   (ui/ HTML/CSS/JS)    │  ├─ sirve ui/ (static)     │
        │  /api/*       │  ├─ API de órdenes/pago    │
        ▼               │  ├─ orquestación de pago   │
        ───────────────►│  └─ SSE events /status     │
                        └─────────┬──────────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
      ┌───────────────┐   ┌─────────────────┐   ┌────────────┐
      │ payments_getnet.py │ │  orders.py       │   │ receipt.py │
      │ Connector ABC  │   │  OrderStore      │   │ HTML+PDF   │
      │ usb/http/cloud │──►│  SQLite          │   │ Jinja2     │
      │ simulation     │   │  transiciones    │   │ ReportLab  │
      └───────┬────────┘   └─────────────────┘   └────────────┘
              │ usa
              ▼
      ┌───────────────┐    ┌──────────────┐
      │ serial_im30.py│    │   config.py  │
      │ SerialTransport│   │  env > yaml  │
      │ Framing       │    │  Settings    │
      │ detección by-id│   └──────────────┘
      └───────────────┘
```

### Responsabilidades por módulo

| Módulo | Responsabilidad |
|---|---|
| `app.py` | App principal. Arranca FastAPI+uvicorn, monta `ui/`, expone la API REST/SSE, orquesta el ciclo de pago por orden (tareas asíncronas), implementa la **reconciliación** anti doble cobro y emite comprobantes. |
| `payments_getnet.py` | Capa de integración con la máquina de cobro. Define la abstracción `Connector` (abstract) y 5 implementaciones: `UsbConnector`, `HttpConnector`, `CloudConnector`, `App2AppConnector`, `SimulatedConnector`. Ciclo `create → polling → sale/refund → close`. Modelos `SaleRequest`, `SaleResult`, `PollingResult`, `RefundResult`. Factory `create_connector()`. |
| `serial_im30.py` | Capa serie. Detección del PAX IM30 por `by-id` (`find_im30_ports`, `detect_im30_port`), transporte `SerialTransport` sobre `pyserial` (57600 8N1), **framing configurable** (`Framing`: delimitadores, largo, checksum LRC/sum/CRC16), reconexión y diagnóstico. |
| `orders.py` | Modelo de dominio y persistencia. Máquina de estados (`ALLOWED_TRANSITIONS`), idempotencia, flags (`refunded`, `ambiguous`, `reconciled`), `OrderStore` (SQLite) y `Transaction`. |
| `catalog.py` | Catálogo demo. Categorías, productos (dataclass `Product`), `build_line_items`, `compute_total`. |
| `receipt.py` | Comprobante digital. Plantilla Jinja2 (`render_html`) y PDF ReportLab (`generate_pdf`), formateo CLP. |
| `config.py` | Configuración tipada. Precedencia **env (`.env`) > `config.yaml` > defaults**. `Settings`, `SerialFraming`, `get_settings()` (caché), `override_settings()` (tests). |

---

## 2. Máquina de estados de la orden

Definida en `orders.py` (`ALLOWED_TRANSITIONS`):

```
                    ┌───────────┐
      crear orden   │  pending  │◄─────── reintento desde failed/timeout/error/cancelled
        (POST)      └─────┬─────┘
                          │ pay (POST /pay) → transición a CHARGING
                          ▼
                    ┌───────────┐
                    │ charging  │◄── reintentos permitidos SOLO si no hay
                    └──┬───┬────┘    ambigüedad sin reconciliar (409 en caso contrario)
         resultado sale│   │
         ┌──────────┬──┘   └──┬─────────────┬─────────────┐
         ▼          ▼        ▼             ▼             ▼
      ┌──────┐  ┌───────┐ ┌────────┐  ┌──────────┐  ┌────────┐
      │ paid │  │ failed│ │ timeout│  │ cancelled│  │ error  │
      └──┬───┘  └───────┘ └────────┘  └──────────┘  └────────┘
         │  (única vez)                  │ ambigüedad → _reconcile_order()
         ▼                               (refund/void con conector NUEVO)
    ┌──────────┐
    │ emitted  │  ←─ idempotente (re-emisión del comprobante)
    └──────────┘
```

Reglas clave:

- `pending → charging` solo desde `pending` (o desde `failed/timeout/cancelled/error` en reintento).
- `charging → paid` es **único**: una orden no puede pagarse dos veces (guard en `_run_payment` +
  `store.transition` con `InvalidTransition` → el endpoint `pay` responde **409** si ya está pagada).
- `paid → emitted` idempotente: re-emitir el comprobante no cambia el estado (solo incrementa
  `receipt_count`).
- `charging` **no** puede volver a `pending`.
- **Ambigüedad + reconciliación:** todo timeout/cancelación (durante `charging`) o error de
  transporte durante la venta marca la orden `ambiguous=True` y ejecuta `_reconcile_order()`, que
  intenta un `refund`/`void` del importe con un **conector nuevo**. Solo si `reconciled=True` se
  permite reintentar; si no, el endpoint `pay` responde **409**.

### `_run_payment` (núcleo del cobro)

```
POST /api/orders/{id}/pay
   │  (lock por orden: _lock_for)
   ▼
create_connector(settings)
   │
   ├─ connector.create()  → Polling (Code=0)  ──NO──► transition(ERROR)
   │                                                        │
   │                                                         ▼
   │   SaleRequest(amount=order.total, SaleType="Card")      fin
   │   result = asyncio.wait_for(connector.sale(req),
   │                             timeout=connector.sale_timeout)
   │
   ├─ TimeoutError ──► transition(TIMEOUT) · mark_ambiguous(True)
   │                     → _reconcile_order(reason="timeout")  (conector nuevo)
   │
   ├─ SaleResult → add_transaction(...)
   │     ├─ approved ──► transition(PAID)
   │     └─ rechazado ──► transition(FAILED, error="... (code=N)")
   │
   └─ except ConnectorError/Exception:
         si sale_attempted y status==CHARGING:
             mark_ambiguous(True) → _reconcile_order(reason="transport-error")
         transition(ERROR, error=f"{type}: {exc}")
   │
   └─ finally: connector.close()  (siempre se libera)
```

> `asyncio.wait_for(..., timeout=connector.sale_timeout)`: cada conector define su propio timeout
> de venta. `CloudConnector` usa `max(ORDER_TIMEOUT_SECONDS, 300)` para no cortar ventas legítimas
> de Cloud2Cloud (incidencia I-03 resuelta).

---

## 3. Capa de pagos (`payments_getnet.py`)

### 3.1 Modelos

| Dataclass | Campos principales | Notas |
|---|---|---|
| `SaleRequest` | `amount: int`, `sale_type="Card"`, `currency="CLP"`, `order_id`, `extra` | `Amount` en unidades menores (CLP: 1 = $1). `extra` permite override de simulación (`simulate_outcome`, `simulate_delay`). |
| `SaleResult` | `code`, `message`, `commerce_code`, `terminal_id`, `authorization_code`, `amount`, `accounting_date`, `real_date`, `sale_type`, `operation_mode`, `original_amount`, `raw` | `approved == (code == 0)`. `from_dict()` mapea tanto camelCase (`Code`) como snake_case (`code`). |
| `PollingResult` | `code`, `message`, `connected` | `ok == (code == 0)`. |
| `RefundResult` | `code`, `message`, `authorization_code`, `amount`, `raw` | `approved == (code == 0)`. |

### 3.2 Interfaz `Connector`

```python
class Connector(abc.ABC):
    name = "base"
    @property
    def sale_timeout(self) -> float: ...          # default = order_timeout_seconds
    async def create(self) -> PollingResult: ...  # abre + valida Polling Code=0
    async def polling(self) -> PollingResult: ...
    async def sale(self, request: SaleRequest) -> SaleResult: ...
    async def refund(self, amount: int, order_id="") -> RefundResult: ...
    async def get_reports(self, report_type="daily") -> dict: ...
    async def close(self) -> None: ...
    # __aenter__ / __aexit__ -> create/close
```

`_validate_polling()` (heredado) **lanza `ConnectorError` si `Code != 0`** en `create()` para todos
los conectores (incidencia I-04 resuelta).

### 3.3 Implementaciones

| Conector | Transporte | Detalles |
|---|---|---|
| `UsbConnector` | `serial_im30.SerialTransport` | `CreateUsb`. `_encode_operation` arma un sobre JSON `{Operation, TerminalId, MerchantId, Timestamp, ...}` (de **referencia** — sustituir por el SDK oficial en producción). `_request` reintenta con backoff y reconexión. `close()` envía `Close` y cierra el puerto. |
| `HttpConnector` | `httpx.AsyncClient` | `CreateHttp`. POST JSON a `/{polling,sale,refund,close}` en `http://{host}:{port}`. Reintentos con backoff. |
| `CloudConnector` | `httpx.AsyncClient` | `CreateCloud`. Headers `X-Api-Key`, `X-Client-Id`, `X-Client-Secret`. Requiere `GETNET_CLOUD_URL`. `sale_timeout = max(order, 300)`. |
| `App2AppConnector` | `adb` (subprocess asíncrono) | `App2App`. Dispara la app de pagos del IM30 por Intents (`am start -n cl.getnet.payment.prod2/cl.getnet.payment.ApiActivity -a <action> --es params <json>`) y captura la respuesta de `logcat` (tag `ApiActivity`). Ver §3.5. |
| `SimulatedConnector` | Local | Emula `Polling OK` y `SaleResult`/`RefundResult`. Outcome: `approved \| declined \| timeout \| error \| random` (por `extra.simulate_outcome` o `GETNET_SIM_OUTCOME`). `timeout` lanza `asyncio.TimeoutError`; `error` lanza `ConnectorError`. |

### 3.4 Factory

```python
def create_connector(settings: Settings) -> Connector:
    kind = settings.effective_connector        # simulation SIEMPRE fuerza SimulatedConnector
    if kind == "simulation": return SimulatedConnector(settings)
    if kind == "usb":       return UsbConnector(settings)
    if kind == "http":      return HttpConnector(settings)
    if kind == "cloud":     return CloudConnector(settings)
    if kind == "app2app":   return App2AppConnector(settings)
    raise ConnectorError(...)
```

### 3.5 Conector App2App (`GETNET_CONNECTOR=app2app`)

Integra el tótem con la **app de pagos de Getnet** ya instalada en el IM30
(`cl.getnet.payment.prod2`, `cl.getnet.payment.ApiActivity`) usando **Intents Android por ADB**,
sin SDK propietario. Contrato oficial: Manual "Integración Getnet - A2A para Aplicaciones Android 1.22".

**Flujo de una operación:**

```bash
adb [-s $GETNET_ADB_SERIAL] logcat -c
adb ... shell am start -n cl.getnet.payment.prod2/cl.getnet.payment.ApiActivity \
  -a cl.getnet.payment.action.SALE --es params '{"Amount":3500,"TicketNumber":"0042",...}'
adb ... logcat -d -s ApiActivity:W      # se sondea hasta ver la respuesta
```

- `build_sale_params()` arma el JSON de `params` con el contrato A2A 1.22 (claves PascalCase):
  `Amount` (pesos CLP enteros), `TicketNumber`, `PrintOnPos`, `SaleType=1` (Compra Afecta),
  `EmployeeId=1`, `TypeApp=0` (app), `RestrictedCards/AllowedCards=null`,
  `PlaceCardToPayTimeout`/`PaymentResultTimeout` (SEGUNDOS), `IntegrationType=3` (App to App),
  `SoftwareName="TotemGetnetIM30"`, `SoftwareVersion="1.0"`.
- `build_refund_params()` → `{AuthorizationCode, Amount, PrintOnPos, TypeApp, timeouts}` (action `REFUND`).
- `build_cancellation_params()` → `{OperationId, PrintOnPos, TypeApp, timeouts}` (action `CANCELLATION`).
- `parse_logcat_response()` extrae `responseToApplication = {...}` (JSON `SaleResponse` lowercase:
  `functionCode/responseCode/responseMessage/commerceCode/terminalId/ticket/authorizationCode/amount/...`)
  o `responseError: ...`; `responseCode ∈ {"00","0"}` → aprobado, cualquier otro → rechazado.
- **Quoting ADB**: el JSON se envuelve en comillas simples a nivel del dispositivo
  (`--es params '<json>'`) para que el shell de Android no elimine las comillas dobles.
- `sale_timeout = max(order_timeout_seconds, paymentResultTimeout + 5)`.
- Todo el I/O de `adb` corre con `asyncio.create_subprocess_exec` (no bloquea el event loop).

**Degradación elegante:** si `GETNET_MODE=simulation`, `adb` no está disponible, el terminal no
está detectado o la app de pagos no está instalada, el conector opera en simulación y lo reporta
en `PollingResult.message` y en `SaleResult.raw["App2AppFallback"]`.

**Requisito de activación del terminal:** el IM30 debe estar **provisionado** por Getnet
(parámetros TMS descargados con el código TID del comercio). Si el terminal muestra
"Sin parámetros TMS — Ingrese su código TID", la venta real será rechazada (código 1006
"Cancelado por POS") y la app puede mostrar el diálogo de rechazo. El `GETNET_TERMINAL_ID`
del env es solo referencia; la verificación de provisioning se hace contra el hardware.

Variables: `GETNET_ADB_SERIAL` (vacío = autodetecta), `GETNET_ADB_PATH`,
`GETNET_APP2APP_PACKAGE`, `GETNET_APP2APP_ACTIVITY`, `GETNET_APP2APP_PAYMENT_TIMEOUT_MS`,
`GETNET_APP2APP_PLACE_CARD_TIMEOUT_MS`, `GETNET_APP2APP_POLL_INTERVAL`,
`GETNET_APP2APP_PRINT_ON_POS`.

---

## 4. Capa serie (`serial_im30.py`)

### 4.1 Detección del IM30

- Constantes: `PAX_VID=0x2FB8`, `PAX_PID=0x225E`, `PRODUCT_HINT="IM30"`, `DEFAULT_INTERFACE="if02"`.
- `find_im30_ports()`: busca `/dev/serial/by-id/*` que contenga `IM30`/`PAX` y los mapea a
  `Im30Port(by_id, device, interface, ...)`; fallback por VID/PID con `pyserial list_ports`.
- `detect_im30_port(preference="if02")`: prioriza la interfaz preferida, luego la primera
  no-`if00` (evita ACM0/ModemManager), luego la primera.
- El IM30 expone 3 interfaces: `if00`→ttyACM0 (AT), `if02`→ttyACM1 (datos), `if04`→ttyACM2 (datos).

### 4.2 Framing configurable (`Framing`)

El protocolo serie exacto de Getnet Integrated POS es **propietario/no público**. Por eso el framing
es configurable (en `config.yaml` → `getnet.serial.framing`):

| Campo | Default | Opciones |
|---|---|---|
| `start_delimiter` | `STX` | `STX`(0x02), `ETX`(0x03), `EOT`, `ENQ`, `ACK`, `NAK`, `0xNN`, decimal, `""`/`none` |
| `end_delimiter` | `ETX` | igual que start |
| `include_length` | `true` | prefijo de largo big-endian (2 bytes) tras el start (si hay) |
| `checksum` | `lrc` | `none` \| `lrc` (XOR) \| `sum` (sum & 0xFF) \| `crc16` (Modbus, 2 bytes little-endian) |

Trama real por USB = `[start] [length:2BE] [payload] [checksum] [end]`.

- `encode(payload) -> bytes` construye la trama.
- `decode(frame) -> payload` valida delimitadores, largo y checksum y extrae el payload.
- `expected_total_length(buf)` calcula la terminación cuando **no hay** delimitador de fin, usando
  la longitud REAL del checksum (`len(compute_checksum(b"", kind))`) — corrige el bug de terminación
  fija (incidencia I-05 resuelta).

> **En producción real:** para operar contra hardware homologado, reemplazar el sobre JSON de
> `UsbConnector._encode_operation`/`_decode_response` por el framing/SDK oficial de Getnet. El modo
> simulación **no** depende del framing.

### 4.3 `SerialTransport`

- `open()`: resuelve puerto (`resolve_port`: explícito o `detect_im30_port`), abre `serial.Serial`
  con 57600 8N1, timeouts, sin flow control. Traduce `busy/resource` a `PortBusyError` (aviso de
  ModemManager) y puerto no encontrado a `TerminalNotConnected`.
- `write_frame(payload)` / `read_frame(timeout)` / `request(payload)` (escribe trama + lee +
  decodifica, devolviendo el payload).
- `reconnect()`: cierra, espera 200 ms y reabre.
- Excepciones: `SerialTransportError`, `PortBusyError`, `TerminalNotConnected`.

---

## 5. API de funciones

### `app.py`

| Función | Propósito |
|---|---|
| `_lock_for(order_id)` | Retorna un `asyncio.Lock` por orden (exclusión mutua real en pay/cancel/refund; I-06/I-09). |
| `lifespan(app)` | Arranque/cierre: crea `data/receipts` y `ui/`; cancela tareas de pago en `shutdown`. |
| `_reconcile_order(order_id, amount, reason, connector=None)` | Reversión (refund/void) de una operación ambigua. Crea/usa conector; persiste `Transaction(operation_mode="Reconciliation", sale_type="VOID")`; marca `reconciled` con el resultado. **Conector nuevo** por defecto (evita contención sobre el puerto cancelado; I-08). |
| `_run_payment(order_id, simulate_outcome)` | Ejecuta `create → polling → sale → close` para una orden, maneja timeout/rechazo/error/ambigüedad/reconciliación y persiste la transacción. |
| `create_order(payload)` | `POST /api/orders`: valida items, total en rango, crea orden `pending`. |
| `list_orders(limit=50)` | `GET /api/orders`: historial. |
| `get_order(order_id)` | `GET /api/orders/{id}`. |
| `order_status(order_id)` | `GET /api/orders/{id}/status`: orden + última transacción + `charging`. |
| `pay_order(order_id, payload)` | `POST /api/orders/{id}/pay`: valida estados, blquea si ambigua sin reconciliar (409), transiciona a `CHARGING` y lanza tarea `_run_payment`. Acepta `simulate_outcome`. |
| `cancel_order(order_id)` | `POST /api/orders/{id}/cancel`: cancela tarea/estado y reconcilia si hubo ambigüedad. |
| `refund_order(order_id, payload)` | `POST /api/orders/{id}/refund`: solo órdenes `paid/emitted` y no reembolsadas; valida Polling; persiste intento; marca `refunded` de forma atómica (409 si ya reembolsada; 502 si rechazado). |
| `_require_receipt_order(order_id)` | Carga orden + última transacción (u `Transaction` vacía). |
| `receipt_html(order_id)` | `GET /api/orders/{id}/receipt`: HTML del comprobante; transiciona `paid→emitted` (idempotente) o reemite. |
| `receipt_pdf(order_id)` | `GET /api/orders/{id}/receipt.pdf`: bytes PDF con `Content-Disposition`. |
| `order_events(order_id, request)` | `GET /api/orders/{id}/events`: SSE con estado de la orden hasta estado terminal. |
| `terminal_status()` | `GET /api/terminal/status`: modo, conector, puerto, diagnóstico serie + polling real. |
| `terminal_ports()` | `GET /api/terminal/ports`: lista de puertos IM30 detectados. |
| `health()` / `api_config()` / `api_catalog()` / `index()` | Health, config sin secretos, catálogo y UI. |

### `payments_getnet.py`

| Función | Propósito |
|---|---|
| `_now_gmt()` / `_now_local()` | Timestamps ISO (UTC y local) para envío/persistencia. |
| `SaleResult.from_dict(data)` | Normaliza respuesta (CamelCase/snake_case) a dataclass. |
| `Connector._validate_polling(polling)` | Lanza `ConnectorError` si `Code != 0`. |
| `UsbConnector._encode_operation(operation, payload)` | Sobre JSON de referencia (`Operation`, IDs, Timestamp, payload). |
| `UsbConnector._decode_response(payload)` | Decodifica JSON; `ProtocolError` si no interpretable. |
| `UsbConnector._request(...)` | I/O serie con reintentos + backoff + reconexión. |
| `UsbConnector.create/polling/sale/refund/close` | Ciclo Integrated POS por serie. |
| `HttpConnector._post(path, payload)` | POST JSON con reintentos (máx. `max_retries`). |
| `CloudConnector._headers()` / `_get_client()` / `_post()` | Headers de auth, cliente httpx con timeout 300 s, POST HTTPS. |
| `SimulatedConnector._pick_outcome(req)` / `_sleep(req)` | Selección de outcome simulado y delay (por request o settings). |
| `SimulatedConnector.sale/refund` | Emulan resultados (incluye `Asyncio.TimeoutError` y `ConnectorError`). |
| `create_connector(settings)` | Factory pública. |

### `serial_im30.py`

| Función | Propósito |
|---|---|
| `_resolve_delimiter(value)` | Convierte nombre/hex/decimal a byte delimitador. |
| `lrc` / `checksum_sum` / `crc16_modbus` | Algoritmos de checksum. |
| `compute_checksum(data, kind)` | Genera bytes de checksum según kind. |
| `Framing.from_config(cfg)` | Construye framing desde `SerialFraming`. |
| `Framing.encode/decode/expected_total_length` | Construcción/parseo de tramas y cálculo de longitud. |
| `find_im30_ports()` / `detect_im30_port(pref)` / `describe_ports()` | Detección/diagnóstico del IM30. |
| `Im30Port.to_dict()` | Serialización para la API. |
| `SerialTransport.resolve_port/open/close/reconnect` | Lifecycle del puerto. |
| `SerialTransport.write_frame/read_frame/request` | I/O serie. |
| `serial_im30.error classes` | `SerialTransportError`, `PortBusyError`, `TerminalNotConnected`. |

### `orders.py`

| Función | Propósito |
|---|---|
| `OrderStore.create_order(items, total, currency, order_id)` | Inserta orden `pending` (id autogenerado UUID hex 12). |
| `OrderStore.get_order/list_orders` | Lecturas. |
| `OrderStore.transition(order_id, new_status, error)` | Máquina de estados validada; `paid→emitted` idempotente (bump receipt); lanza `InvalidTransition`. |
| `OrderStore.add_transaction(tx)` / `get_transactions` / `get_last_transaction` | Persistencia de transacciones. |
| `OrderStore.mark_refunded(order_id, True)` | Guarda atómica `UPDATE ... WHERE refunded=0` + rowcount (evita doble reembolso). |
| `OrderStore.mark_ambiguous` / `mark_reconciled` | Flags de operación ambigua/reconciliada. |
| `OrderStore._migrate(conn)` | ALTER TABLE idempotente para columnas nuevas. |
| `Order.to_dict()` / `Transaction.to_dict()` | Serialización. |

### `catalog.py`, `receipt.py`, `config.py`

| Función | Propósito |
|---|---|
| `get_catalog/get_categories/get_products/get_product` | Lectura del catálogo. |
| `build_line_items(items)` | Valida y convierte `[{product_id, qty}]` en líneas con precios server-side. |
| `compute_total(lines)` | Total en CLP. |
| `format_clp(amount)` | `$12.500` (punto miles es-CL). |
| `render_html(order, tx)` | Comprobante HTML con plantilla Jinja2 + filtro `clp`. |
| `generate_pdf(order, tx, output_path=None)` | PDF A4 (ReportLab) en memoria o archivo. |
| `receipt_context(order, tx)` | Contexto de datos para vistas. |
| `load_settings(config_path)` | Configuración efectiva (env > yaml > defaults). |
| `get_settings()` | Settings cacheados por `lru_cache`. |
| `override_settings(base, **kwargs)` | Copia modificada (tests). |
| `Settings.effective_connector` / `db_full_path` / `to_public_dict` | Helpers: simulación forzada, ruta absoluta DB, dict sin secretos. |

---

## 6. Diagrama de flujo de una venta (síncrono, transporte USB)

```
UI                              Backend (app.py)          PAX IM30 / serie
│  POST /api/orders              │                          │
│────────────────────────────────►│ create_order()          │
│                                │ order=pending (SQLite)   │
│  POST /api/orders/{id}/pay     │                          │
│────────────────────────────────►│ pay_order() (lock)       │
│                                │ transition → CHARGING    │
│                                │ _run_payment (task)      │
│                                │  create_connector()      │
│                                │  connector.create()  ────►│  apertura puerto
│                                │  (polling Code=0) ◄───────│  respuesta OK
│                                │  Sale(3700, Card)  ──────►│  cliente acerca tarjeta
│  GET /status (SSE/1s)          │                          │
│◄───────────────────────────────│  estado actualizado      │
│                                │  SaleResult Code=0  ◄────│  aprueba en el IM30
│                                │  add_transaction()       │
│                                │  transition → PAID       │
│  GET /receipt(.pdf)            │                          │
│────────────────────────────────►│ receipt_html/pdf        │
│◄───────────────────────────────│  comprobante (HTML/PDF)  │
│                                │  transition → EMITTED    │
│                                │  connector.close()       │  cierre puerto
```

---

## 7. Configuración

### Precedencia

```
variables de entorno (.env, NO versionado)  >  config.yaml  >  defaults del dataclass
```

`config.py` carga `.env` con `load_dotenv(..., override=False)`, luego `load_settings()` combina
`yaml` y env. Las credenciales Getnet **solo** vienen de env.

### Variables clave (ver también `.env.example` y `config.yaml`)

| Variable | Default | Descripción |
|---|---|---|
| `GETNET_MODE` | `simulation` | `simulation` \| `sandbox` \| `production` |
| `GETNET_CONNECTOR` | `usb` | `usb` \| `http` \| `cloud` (ignorado en simulación) |
| `GETNET_SERIAL_PORT` | `""` | Puerto serie explícito (vacío → autodetección por `by-id`) |
| `GETNET_SERIAL_PREFERENCE` | `if02` | Interfaz preferida al autodetectar |
| `GETNET_BAUDRATE` | `57600` | Baudrate |
| `GETNET_TERMINAL_ID` / `GETNET_MERCHANT_ID` / `GETNET_COMMERCE_CODE` | vacío | Identificadores Getnet (secretos) |
| `GETNET_HTTP_HOST` / `GETNET_HTTP_PORT` | `127.0.0.1:8080` | Fallback HTTP |
| `GETNET_CLOUD_URL` / `GETNET_API_KEY` / `GETNET_CLIENT_ID` / `GETNET_CLIENT_SECRET` | vacío | Cloud2Cloud |
| `ORDER_TIMEOUT_SECONDS` | `120` | Timeout de espera de tarjeta |
| `IDLE_TIMEOUT_SECONDS` | `60` | Vuelta al atractor |
| `GETNET_MAX_RETRIES` / `GETNET_RETRY_BACKOFF` | `2` / `1.0` | Reintentos de transporte |
| `DB_PATH` | `data/orders.db` | Ruta SQLite |
| `APP_HOST` / `APP_PORT` | `0.0.0.0:8000` | Binding |
| `GETNET_SIM_OUTCOME` | `approved` | Outcome simulado global (`approved\|declined\|timeout\|error\|random`) |
| `GETNET_SIM_REFUND_OUTCOME` | `approved` | Outcome simulado de refund |
| `GETNET_SIM_DELAY` | `1.5` | Delay simulado (s) |
| `GETNET_SIM_APPROVE_PROB` | `1.0` | Probabilidad de aprobación con outcome `random` |

---

## 8. Tests

### Ejecutar

```bash
.venv/bin/python -m pytest           # 51 passed
.venv/bin/python -m pytest -v        # detalle
```

### Estructura

| Archivo | Cubre |
|---|---|
| `tests/conftest.py` | Fixtures: `sim_settings` (simulación, delay 0, timeout 5) y `store` (SQLite temporal). |
| `tests/test_e2e.py` | Flujo end-to-end con `TestClient`: health/config sin secretos, catálogo, venta aprobada + comprobante/PDF, rechazo + reintento, timeout + reconciliación, error de transporte + reconciliación, bloqueo de reintento si reversión falla (409), refund 502/OK/idempotente, doble pago 409, cancelación, carrito inválido, terminal status/ports, índice, historial. |
| `tests/test_orders.py` | Máquina de estados, doble cobro, `emitted` idempotente, reintento desde `failed`, flags refund/ambiguous/reconciled, `mark_refunded` atómico. |
| `tests/test_payments_getnet.py` | Factory simulación, mapeo `SaleResult`, polling/sale/refund simulados (approved/declined/timeout/error), `sale_timeout` cloud ≥ 300, validación de polling ≠ 0, y App2App: `build_sale_params`, parseo de logcat (aprobado/rechazado/error) y fallback a simulación. |
| `tests/test_serial_im30.py` | Checksums, roundtrip de framing (con/sin delimitadores), checksum inválido, longitud esperada con/sin start, detección del IM30 real (marcada `hardware`, se ignora si no hay terminal). |
| `tests/test_receipt.py` | `format_clp`, HTML contiene campos, PDF bytes/válido `%PDF`, PDF a archivo, contexto. |

> El marker `hardware` (definido en `pytest.ini`) excluye la prueba de detección real si no hay IM30
> conectado. La suite completa sigue 51 tests en verde sin hardware.

---

## 9. Guía de modificación y extensión

### 9.1 Agregar productos al catálogo

Editar `catalog.py` (lista `PRODUCTS`):

```python
Product("beb-fanta", "Fanta 350ml", "bebidas", 1500, "🍊"),
```

Reglas:
- `id` único (prefijo de categoría recomendado, p. ej. `beb-`, `snk-`).
- `category` debe existir en `CATEGORIES` (o agregarla).
- `price` entero en **CLP** (sin decimales).

Los precios del carrito se recalculan en el servidor; el cliente solo envía `product_id`+`qty`.

### 9.2 Configurar otro terminal (otra máquina de cobro)

1. Conectalo por USB y detectá el puerto:
   ```bash
   ls -l /dev/serial/by-id/ | grep -i pax        # ver by-id del terminal
   .venv/bin/python - <<'PY'
   import serial_im30
   print([p.to_dict() for p in serial_im30.find_im30_ports()])
   PY
   ```
2. En `.env`:
   ```bash
   GETNET_TERMINAL_ID=<NUEVO_TERMINAL_ID>
   GETNET_MERCHANT_ID=<NUEVO_MERCHANT_ID>
   GETNET_COMMERCE_CODE=<NUEVO_COMMERCE_CODE>
   GETNET_SERIAL_PORT=/dev/serial/by-id/usb-PAX_IM30_<SERIAL>-if02
   GETNET_SERIAL_PREFERENCE=if02
   GETNET_BAUDRATE=57600
   ```
3. Levanta y verifica `GET /api/terminal/status` (polling debe dar `connected=true` en modo real).

### 9.3 Cambiar de entorno (simulación → sandbox → producción)

```bash
# .env
GETNET_MODE=simulation      # sin credenciales
GETNET_MODE=sandbox         # homologación, credenciales demo de Getnet
GETNET_MODE=production      # operación real
```

`GETNET_MODE=simulation` **siempre** fuerza `SimulatedConnector` (property `effective_connector`),
así que basta con cambiar la variable para alternar sin tocar código.

### 9.4 Operar con otro transporte (HTTP / Cloud)

```bash
# HTTP (fallback por red local)
GETNET_CONNECTOR=http
GETNET_HTTP_HOST=192.168.1.50
GETNET_HTTP_PORT=8080

# Cloud2Cloud
GETNET_CONNECTOR=cloud
GETNET_CLOUD_URL=https://api.getnet.example/v1
GETNET_API_KEY=<KEY>
GETNET_CLIENT_ID=<CLIENT_ID>
GETNET_CLIENT_SECRET=[REDACTED]
```

### 9.5 Ajustar timeouts / montos

| Qué | Variable |
|---|---|
| Tiempo de espera de tarjeta | `ORDER_TIMEOUT_SECONDS` |
| Inactividad → atractor | `IDLE_TIMEOUT_SECONDS` |
| Rango de montos | `MIN_AMOUNT` / `MAX_AMOUNT` |
| Reintentos de transporte | `GETNET_MAX_RETRIES` / `GETNET_RETRY_BACKOFF` |

### 9.6 Conectar el protocolo oficial de Getnet (integración real USB)

Puntos de sustitución, cuando tengas el SDK/protocolo oficial y terminal homologado:

1. En `serial_im30.py`: ajustar `Framing` (`config.yaml` → `getnet.serial.framing`) a los
   delimitadores/largo/checksum reales; o reemplazar `SerialTransport.request` por el intercambio
   nativo del SDK.
2. En `payments_getnet.py`: reescribir `UsbConnector._encode_operation` y `_decode_response` para
   emitir/interpretar las operaciones reales (`Polling`, `Sale`, `Refund`, `Close`).
3. Validar en **sandbox/homologación** antes de producción (la Connector App del IM30 debe correr en
   modo Integrated POS).
4. Mantener el `mode=simulation` como fallback de desarrollo: los tests no dependen del framing.

### 9.7 Recomendaciones al modificar

- **No romper la idempotencia:** las transiciones validan en `orders.py`; los reintentos de venta
  y reemisión de comprobante deben seguir pasando por `store.transition`.
- **No exponer secretos:** `Settings.to_public_dict()` filtra credenciales; mantener ese contrato en
  `/api/config` (test: `test_config_does_not_expose_sensitive_identifiers`).
- **Revisar tras cambios:** `pytest` debe quedar en verde (51 tests). Los cambios de protocolo en
  USB se prueban con el marker `hardware` en un terminal real.
- **Concurrencia:** usar `_lock_for(order_id)` alrededor de secuencias pay/cancel/refund; la
  reconciliación usa conector nuevo para no competir por el puerto serie.

---

## 10. Limitaciones conocidas

- **Protocolo serie propietario:** el framing/servicio USB actual es de referencia; la operación en
  producción requiere homologación y el protocolo/SDK oficial.
- **Cancelación por timeout (I-08):** `asyncio.wait_for` no detiene el hilo subyacente de
  `asyncio.to_thread` en I/O; la reversión usa un conector nuevo y se documenta que en hardware
  homologado debe validarse que la venta previa terminó de desenrollarse.
- **Crecimiento de `_order_locks`:** el dict de locks no purga entradas (memoria despreciable en un
  kiosco).
- **UI en español/CLP:** el catálogo y formatos están pensados para Chile; cambiar `CURRENCY`,
  catálogo y `format_clp` si se despliega en otra moneda.