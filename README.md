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

## Sensor DHT11 y monitoreo local

El ESP32-WROOM-32 toma cuatro muestras del DHT11 (DATA en GPIO4) cada 60 segundos. Solo publica temperatura y humedad promedio cuando las cuatro son válidas. Si falla alguna, envía un ciclo `INVALIDO` con cantidad de muestras y sin promedios. Inventario muestra la última medición válida, la zona del dispositivo y el estado de comunicación; tras 180 segundos sin datos válidos señala «Lectura antigua». El historial en `/monitoreo/` distingue ciclos válidos, inválidos y zonas históricas. Dueño y empleado pueden consultarlo. Solo el dueño administra dispositivos en `/dispositivos/`, asigna zonas, activa o desactiva equipos y rota sus tokens.

El contrato nuevo es `POST /api/v1/dispositivos/me/ciclos` con `Authorization: Bearer <token>` y JSON con `version: 1`, `ciclo_id` UUID, `estado`, `muestras_validas`, `temperatura_c`, `humedad_pct` y, para ciclos inválidos, `error_codigo: SENSOR_LECTURA`. `ciclo_en` es una fecha UTC opcional. Un reintento idéntico devuelve HTTP 200 y no duplica; el mismo ID con datos distintos devuelve HTTP 409. Cada token identifica un dispositivo y en PostgreSQL solo se guarda su hash. La ruta previa `/api/sensor/lecturas/` sigue disponible para firmware antiguo; los ciclos parciales de esa ruta se guardan como inválidos sin promedio.

`seed_demo` registra `ESP32-01` en Almacén usando el token privado local si aún no existe y vincula las lecturas históricas sin cambiar sus valores. Los archivos `.env` y `firmware/ICChocolate_DHT11/secrets.h` permanecen fuera de Git. Para cargar el firmware, abre `firmware/ICChocolate_DHT11/ICChocolate_DHT11.ino` en Arduino IDE con **esp32 by Espressif Systems**, **DHT sensor library by Adafruit** y **Adafruit Unified Sensor**, selecciona **ESP32 Dev Module** y el puerto USB de la placa. El monitor serie usa 115200 baudios.

### Envío entre redes

El firmware usa la URL HTTPS de Tailscale Funnel configurada en `REMOTE_INGEST_URL`. Funnel entrega solo el endpoint del sensor al contenedor `sensor-gateway` en `127.0.0.1:8002`; las páginas y sesiones web permanecen en `127.0.0.1:8001`. Django valida el token. El ESP32 puede estar en otra red con Internet; la PC debe permanecer encendida con Docker Desktop y Tailscale conectados. Si cambia el Wi-Fi del ESP32, actualiza sus credenciales en el `secrets.h` privado y vuelve a cargarlo. Si no hay URL remota, el sketch usa la ruta HTTP local configurada para `192.168.18.244`.

La suite automatizada crea ciclos simulados solo en una base PostgreSQL temporal. Para la comprobación física se exige un ciclo nuevo desde el ESP32 y se contrasta con el monitor serie y la fila nueva en la base habitual.
## Alertas y correo (fase 4)

La temperatura activa un episodio cuando un promedio válido supera **10 °C**; a 10 °C exactos no se activa. El dueño puede cambiar el umbral por dispositivo en `/alertas/reglas/`. Cada cambio crea una versión nueva y cierra el episodio previo sin declarar una recuperación ficticia. La humedad se muestra sin alerta inicial. `/alertas/` muestra episodios y avisos web para dueño y empleado; `/monitoreo/` muestra el estado térmico junto al de comunicación.

Un episodio genera un aviso inicial, como máximo un recordatorio cuando llega otra lectura válida tras tres minutos y un aviso de recuperación al recibir un promedio dentro del umbral. Un ciclo inválido o 180 segundos sin datos válidos no equivale a recuperación. El trabajador `worker` detecta la falta de datos y procesa la cola de correos aunque no haya un navegador abierto. Los correos pendientes, aceptados, fallidos e inciertos se muestran al dueño. Un resultado SMTP incierto no se reenvía automáticamente.

El dueño configura destinatarios en `/alertas/destinatarios/`. Las cuentas demo terminadas en `.local` no reciben correo por defecto. El remitente SMTP se define en el `.env` privado con `ALERT_SMTP_HOST`, `ALERT_SMTP_PORT`, `ALERT_SMTP_STARTTLS`, `ALERT_SMTP_USERNAME`, `ALERT_SMTP_PASSWORD` y `ALERT_SMTP_FROM`. Para Gmail personal, usa `smtp.gmail.com`, puerto `587`, STARTTLS y una [contraseña de aplicación](https://support.google.com/accounts/answer/185833?hl=es) con verificación en dos pasos; nunca guardes esa contraseña en Git. La [configuración SMTP de Gmail](https://support.google.com/mail/answer/7104828?hl=es) confirma esos parámetros. Un correo aceptado por SMTP prueba el envío al proveedor, pero no confirma su llegada al buzón.

Las pruebas automatizadas generan ciclos simulados en PostgreSQL temporal y usan remitentes simulados. La prueba integrada de esta PC vinculó un aviso y un correo SMTP real a una lectura física nueva del ESP32.

## Iniciar en Windows con Docker Desktop

### Registro con fotos (fase 5)

Abre `/documentos/nuevo/` desde el menú **Registrar con fotos**. Toma o elige una foto JPEG/PNG de hasta 5 MB, añade otras fotos si hacen falta y revisa las propuestas de Gemini. La pantalla permite corregir cada presentación y cantidad, descartar propuestas erróneas, añadir renglones manuales y elegir compra o venta y ubicación. **Subir o analizar fotos no modifica stock**: solo la confirmación humana crea un movimiento atómico con todos los renglones y fotos, usuario confirmador y fecha. Repetir la confirmación no duplica stock; una foto idéntica a otra ya confirmada no puede volver a confirmar un movimiento.

`POST /documentos/` sigue disponible para subir `multipart/form-data` con `kind=BOLETA|ETIQUETA|OTRO` e `image`; devuelve identificador y `review_url`. `GET /documentos/<id>/imagen/` exige sesión, perfil activo y autoría o rol dueño. El volumen `photo_data` conserva copias JPEG preparadas sin metadatos al recrear contenedores; las fotos no se publican como contenido estático. La clave `GEMINI_API_KEY` está solo en `.env`, fuera de Git. Si no hay clave, red, respuesta válida o cuota gratuita, el formulario queda disponible para completar manualmente. No se activa facturación de Gemini. En Free Tier, Google puede usar entradas para mejorar sus productos; por ahora se prueban documentos ficticios.

El ensayo inicial de OCR local con Tesseract sobre diez fotos reales solo encontró 4 de 16 códigos esperados al probar varias orientaciones y tratamientos de contraste. Véase `FASES.md`.

La comparación con `gemini-3.6-flash` Free Tier sobre las mismas diez fotos reconoció 16/16 códigos y 8/8 cantidades de boleta sin inventar cantidades para etiquetas. Por eso la demo usa esa API con revisión humana y opción manual. La suite automatizada usa respuestas simuladas y una foto real tomada por celular como archivo de entrada; el benchmark de diez fotos sí consultó la API real. Ninguna prueba automática escribe movimientos en la base habitual.

1. Copia `.env.example` como `.env` y reemplaza **todos** los valores que dicen `replace-with-...` por claves y contraseñas propias. `.env` está excluido del repositorio. También puedes conservar el `.env` local que se entregó junto al proyecto.
2. En esta carpeta, ejecuta:

   ```powershell
   docker compose build
   docker compose run --rm web python manage.py migrate --noinput
   docker compose run --rm web python manage.py seed_demo
   docker compose up -d web sensor-gateway worker
   ```

3. Abre <http://localhost:8001>. Usa las cuentas definidas por `DEMO_OWNER_EMAIL`, `DEMO_OWNER_PASSWORD`, `DEMO_EMPLOYEE_EMAIL` y `DEMO_EMPLOYEE_PASSWORD` en tu `.env` local.
4. Para detener sin borrar datos: `docker compose down`. Para iniciar de nuevo: `docker compose up -d web sensor-gateway worker`. **No** uses `docker compose down -v` si quieres conservar los datos.

`seed_demo` es idempotente: repetirlo no duplica cuentas ni existencias iniciales. Las contraseñas de cuentas ya existentes no cambian al repetirlo.

La web escucha en `127.0.0.1:8001`. El gateway del sensor escucha en `127.0.0.1:8002`, y Tailscale Funnel publica solo esa entrada HTTPS. PostgreSQL no publica un puerto. Si se quiere usar el puente local anterior, se inicia aparte con `python config/lan_bridge.py` mientras la PC mantiene la IP indicada.

Para activar Funnel en una instalación nueva de Tailscale: `tailscale funnel --bg --yes 8002`. La cuenta debe permitir Funnel. Comprueba `tailscale funnel status` y coloca la URL HTTPS resultante en `REMOTE_INGEST_URL` del `secrets.h` local. La URL es pública; conserva el token privado y cámbialo si se expone. Para detener la publicación: `tailscale funnel reset`.
## Pruebas

```powershell
docker compose run --rm --no-deps web python manage.py test inventory.tests --noinput
scripts/verify_phase5.ps1
```

Los tests crean su propia base de datos temporal de PostgreSQL. Cubren acceso y permisos, compra, venta, traslado, rechazo de stock insuficiente, operación incompleta, motivo obligatorio, atomicidad e idempotencia. El comprobador de fase 5 verifica además las pantallas HTTP de cámara y el estado de Docker sin crear movimientos. Para probar Gemini real con una foto de boleta en la base temporal, usa `docker compose run --rm --no-deps -e PHASE5_LIVE_GEMINI=1 web python manage.py test inventory.tests.test_phase5_live --noinput`; esta prueba opcional consume una solicitud de la cuota gratuita y se omite en CI. Véase [QA.md](QA.md) para el recorrido manual y el resultado comprobado.

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
inventory/management/commands/  carga idempotente y trabajador de alertas
inventory/tests/                pruebas automáticas
compose.yaml                    web + PostgreSQL + gateway + trabajador de alertas
```

La lógica de stock manual se concentra en `register_movement`; el flujo de fotos usa `confirm_photo_group`, que aplica varios renglones en una sola transacción **después** de revisión humana. La ingesta ESP32 usa `inventory/sensors.py`, `inventory/device_service.py` y `SensorReading`, sin modificar existencias ni movimientos. El proceso `worker` evalúa desconexiones y despacha la cola SMTP. El chatbot y despliegue AWS corresponden a próximas entregas.

## Fuentes de requisitos

Esta etapa toma las reglas de los documentos `especificaciones_mvp_inventario_chocolate` v1.1 y `arquitectura_mvp_inventario_chocolate` v0.1. Las decisiones técnicas del documento de arquitectura se trataron como propuestas; para esta demo se eligió Django 6.0, PostgreSQL 17 y Docker Compose. [Documentación oficial de Django 6.0](https://docs.djangoproject.com/en/6.0/).
