# ICChocolate — demostración local funcional

Aplicación local de inventario de chocolate. Incluye acceso, catálogo, compras, ventas, consumo, merma, traslados y conversiones manuales, con PostgreSQL persistente y un historial auditable. La interfaz toma la paleta crema y cacao de la referencia visual.

## Lo que funciona ahora

- Dos perfiles: **dueño** y **empleado**. Ambos consultan inventario e historial y registran movimientos manuales. Solo el dueño crea productos y ubicaciones.
- Catálogo ficticio inicial: barras, cajas, polvo y chispas, distribuido entre Almacén y Display. Las existencias iniciales se registran como movimientos, no como saldos puestos a mano.
- Antes de afectar el stock, la persona revisa un resumen y confirma. Cada operación queda atribuida a un usuario y fecha.
- Cantidades enteras positivas, disponibilidad no negativa, motivos obligatorios en consumo y merma, traslados entre ubicaciones distintas, transacciones atómicas y clave de idempotencia para evitar doble aplicación.
- Datos conservados en un volumen de PostgreSQL al reiniciar o reconstruir contenedores.
- Borradores persistentes y editables con versión: ningún cambio afecta stock hasta confirmar. El creador o el dueño pueden confirmar o cancelar; el historial distingue al creador y al confirmador.
- Equivalencias dirigidas entre presentaciones del mismo producto con contenido exactamente igual. El dueño las define; dueño y empleado pueden convertir múltiplos enteros en una ubicación.
- El dueño puede corregir un movimiento confirmado mediante reverso completo con motivo, siempre que ninguna existencia quede negativa. El original permanece en el historial.
- El dueño administra productos, presentaciones, ubicaciones y usuarios. No se puede desactivar una posición con stock ni cambiar la descripción de unidad de una presentación que ya tiene movimientos.
- Los formularios de producto y movimiento se abren como ventanas centradas sobre la pantalla actual. La revisión del movimiento continúa antes de guardar stock.

## Operaciones de la fase 2

- **Borradores:** inicia un movimiento manual o una conversión, revisa el resumen, edita si hace falta y confirma. La lista de borradores permite cancelar uno sin afectar existencias.
- **Conversiones:** el dueño define una equivalencia en **Equivalencias**. Ejemplo: una caja de 12 barras equivale a 12 barras del mismo producto. Después, **Convertir presentaciones** descuenta el origen y agrega el destino en una sola transacción.
- **Correcciones:** en **Historial**, el dueño abre **Corregir con reverso**, escribe el motivo y revisa antes de confirmar. Si corresponde, registra después el movimiento correcto.
- **Catálogo y usuarios:** el dueño puede crear presentaciones adicionales, renombrar datos descriptivos, activar o desactivar sin borrar historial y crear o desactivar cuentas. Los códigos y el contenido de una presentación no se alteran desde estas pantallas.

La carga demo añade dos equivalencias iniciales de forma idempotente: `CAJA-BARRA-12 → BARRA-100` (1:12) y `POLVO-1000 → POLVO-100` (1:10). Las operaciones manuales actuales trabajan con una presentación por formulario; el flujo de varios renglones desde fotografía corresponde a la fase 5.

Para repetir la verificación de integración en Windows, ejecuta `./scripts/verify_phase2.ps1`: incluye la suite PostgreSQL en base temporal, acceso HTTP por rol, permisos, reinicio y conservación de datos. El respaldo previo a la migración local se guarda de forma privada en `backups/`, excluida de Git.

## Alias de responsables

Cada perfil tiene un `alias` de hasta 40 caracteres en PostgreSQL. Se cambia desde **Configurar alias**, al pie de la barra izquierda. El correo sigue siendo la credencial de acceso y aparece en el bloque de cuenta de esa barra; el resumen, historial y encabezado muestran el alias. Cada usuario solo puede cambiar el suyo; enviar otros campos en el formulario no modifica el rol ni el correo.

La migración `0003_userprofile_alias` asigna un alias inicial a las cuentas existentes a partir de su nombre de usuario; las cuentas demo nuevas se crean como **Dueño** y **Empleado**. Los movimientos continúan relacionados con la cuenta real mediante `Movement.created_by`. Al cambiar el alias, también cambia el nombre visible en movimientos anteriores, porque el historial consulta el alias vigente; el autor registrado y el stock no se modifican.

## Sensor DHT11 en Inventario

La pestaña **Inventario** muestra un solo recuadro bajo la tabla y su paginación. Indica temperatura, humedad, hora de recepción y comunicación. Muestra **Esperando sensor** hasta recibir la primera medición y **Lectura antigua** si pasan más de 180 segundos sin otra. La página consulta la última lectura cada 15 segundos sin recargarse ni afectar los formularios. Dueño y empleado pueden verla con su sesión normal.

La recepción es `POST /api/sensor/lecturas/` con JSON (`reading_id` UUID, `temperature_c`, `humidity_percent`, `sample_count`) y encabezado `Authorization: Bearer <token>`. El token de dispositivo vive únicamente en `.env` y `firmware/ICChocolate_DHT11/secrets.h`; no es una cuenta de usuario. El servidor valida el rango del DHT11, registra cada lectura en PostgreSQL y acepta reintentos con el mismo `reading_id` sin crear duplicados. La consulta `GET /api/sensor/ultima/` exige una sesión de dueño o empleado.

Para cargar el ESP32 desde Arduino IDE:

1. Instala **esp32 by Espressif Systems**, **DHT sensor library by Adafruit** y **Adafruit Unified Sensor**.
2. Abre `firmware/ICChocolate_DHT11/ICChocolate_DHT11.ino`. El archivo local `secrets.h` contiene el Wi-Fi, el token y `REMOTE_INGEST_URL`; está excluido de Git. No publiques ese archivo.
3. Selecciona **ESP32 Dev Module** y el puerto USB de la placa. Conecta DHT11: DATA a GPIO4 (D4), VCC a 3V3 y GND a GND. Carga el sketch y abre el monitor serie a **115200 baudios**.
4. El ESP32 toma cuatro muestras separadas por 10 segundos en cada ciclo de 60 segundos y envía el promedio de las válidas por HTTPS. Al arrancar sincroniza la hora para validar el certificado. Busca **Lectura recibida por ICChocolate (HTTP 201)** en el monitor. Abre <http://localhost:8001/inventario/> con tu sesión; el recuadro se actualiza cada 15 segundos.

### Envío entre redes

El ESP32 usa la URL pública HTTPS de **Tailscale Funnel** definida en `REMOTE_INGEST_URL`. Valida el certificado TLS y prueba las direcciones IPv4 que publica Funnel si uno de sus relays falla. El Funnel termina TLS en la PC y entrega las peticiones a `127.0.0.1:8002`. El contenedor `sensor-gateway` acepta únicamente `POST /api/sensor/lecturas/` y lo reenvía a la web. Django exige el token del sensor. Inventario y el resto de la aplicación no se publican por Funnel: se consultan localmente en <http://localhost:8001/inventario/>.

Para esta instalación personal, la URL de Funnel es `https://miguellenovo.tail15a9af.ts.net`. Si se instala en otra PC, cambia la URL en el `secrets.h` local y vuelve a cargar el firmware. La PC puede cambiar de red sin modificar el firmware; debe permanecer encendida con Docker Desktop y Tailscale conectados. El ESP32 puede usar otra red con salida a Internet. Si cambia el Wi-Fi al que se conecta el ESP32, actualiza `WIFI_SSID` y `WIFI_PASSWORD` en `secrets.h` y vuelve a cargarlo. Funnel se configuró para seguir activo en segundo plano, y los contenedores usan `restart: unless-stopped`.

`config/lan_bridge.py` y la URL HTTP local del firmware se conservan como alternativa de red local. El puente solo sirve en la subred `192.168.18.0/24` con la PC en `192.168.18.244`; no es necesario para el envío HTTPS entre redes. Si no se define `REMOTE_INGEST_URL`, el firmware usa esa URL local.
La suite automatizada genera mediciones simuladas **solo en una base temporal de pruebas**. La base de uso recibió lecturas reales del ESP32 por HTTPS; no se insertaron mediciones simuladas en ella.

## Iniciar en Windows con Docker Desktop

1. Copia `.env.example` como `.env` y reemplaza **todos** los valores que dicen `replace-with-...` por claves y contraseñas propias. `.env` está excluido del repositorio. También puedes conservar el `.env` local que se entregó junto al proyecto.
2. En esta carpeta, ejecuta:

   ```powershell
   docker compose build
   docker compose run --rm web python manage.py migrate --noinput
   docker compose run --rm web python manage.py seed_demo
   docker compose up -d web sensor-gateway
   ```

3. Abre <http://localhost:8001>. Usa las cuentas definidas por `DEMO_OWNER_EMAIL`, `DEMO_OWNER_PASSWORD`, `DEMO_EMPLOYEE_EMAIL` y `DEMO_EMPLOYEE_PASSWORD` en tu `.env` local.
4. Para detener sin borrar datos: `docker compose down`. Para iniciar de nuevo: `docker compose up -d web sensor-gateway`. **No** uses `docker compose down -v` si quieres conservar los datos.

`seed_demo` es idempotente: repetirlo no duplica cuentas ni existencias iniciales. Las contraseñas de cuentas ya existentes no cambian al repetirlo.

La web escucha en `127.0.0.1:8001`. El gateway del sensor escucha en `127.0.0.1:8002`, y Tailscale Funnel publica solo esa entrada HTTPS. PostgreSQL no publica un puerto. Si se quiere usar el puente local anterior, se inicia aparte con `python config/lan_bridge.py` mientras la PC mantiene la IP indicada.

Para activar Funnel en una instalación nueva de Tailscale: `tailscale funnel --bg --yes 8002`. La cuenta debe permitir Funnel. Comprueba `tailscale funnel status` y coloca la URL HTTPS resultante en `REMOTE_INGEST_URL` del `secrets.h` local. La URL es pública; conserva el token privado y cámbialo si se expone. Para detener la publicación: `tailscale funnel reset`.
## Pruebas

```powershell
docker compose run --rm web python manage.py test inventory -v 2
```

Los tests crean su propia base de datos temporal de PostgreSQL. Cubren acceso y permisos, compra, venta, traslado, rechazo de stock insuficiente, operación incompleta, motivo obligatorio, atomicidad e idempotencia. Véase [QA.md](QA.md) para el recorrido manual y el resultado comprobado.

La misma suite corre en GitHub Actions en cada cambio de `main` y en cada pull request. El flujo comprueba también que los modelos y las migraciones estén sincronizados.

## Respaldo

Detén temporalmente las escrituras de la web antes de un respaldo para tener un punto consistente:

```powershell
docker compose stop web
docker compose exec -T db pg_dump -U icchocolate -d icchocolate -Fc > respaldo_icchocolate.dump
docker compose start web
```

El archivo `respaldo_icchocolate.dump` contiene datos y usuarios: guárdalo de forma privada. Para restaurarlo en una instalación separada, crea una base vacía con las mismas migraciones, detén la web y usa `pg_restore` dentro de `db`; verifica primero el procedimiento sobre una copia. La restauración no forma parte de esta demostración inicial.

## Estructura

```text
config/                         configuración y rutas Django
inventory/models.py             datos e integridad de PostgreSQL
inventory/services.py           reglas y transacciones de inventario
inventory/forms.py              validación de entradas manuales
inventory/views.py              pantallas y permisos
inventory/templates/inventory/  interfaz HTML
inventory/static/inventory/     estilo visual y apertura de ventanas
inventory/management/commands/  carga idempotente y trabajador reservado
inventory/tests/                pruebas automáticas
compose.yaml                    web + PostgreSQL + gateway; trabajador futuro opcional
```

La lógica de stock se concentra en `register_movement`. Las futuras entradas desde OCR deberán terminar en el mismo servicio **después** de revisión humana. La ingesta ESP32 usa `inventory/sensors.py` y `SensorReading`, sin modificar existencias ni movimientos. El proceso `worker` queda reservado. La elección y prueba de OCR, alertas, chatbot, fotografías y despliegue AWS corresponde a próximas entregas.

## Fuentes de requisitos

Esta etapa toma las reglas de los documentos `especificaciones_mvp_inventario_chocolate` v1.1 y `arquitectura_mvp_inventario_chocolate` v0.1. Las decisiones técnicas del documento de arquitectura se trataron como propuestas; para esta demo se eligió Django 6.0, PostgreSQL 17 y Docker Compose. [Documentación oficial de Django 6.0](https://docs.djangoproject.com/en/6.0/).
