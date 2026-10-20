# ICChocolate — primera demostración funcional

Aplicación local de inventario de chocolate para escritorio. Esta entrega muestra el flujo real de acceso, catálogo, compras, ventas, consumo, merma y traslados manuales, con PostgreSQL persistente y un historial auditable. La interfaz toma la paleta crema y cacao de la referencia visual.

## Lo que funciona ahora

- Dos perfiles: **dueño** y **empleado**. Ambos consultan inventario e historial y registran movimientos manuales. Solo el dueño crea productos y ubicaciones.
- Catálogo ficticio inicial: barras, cajas, polvo y chispas, distribuido entre Almacén y Display. Las existencias iniciales se registran como movimientos, no como saldos puestos a mano.
- Antes de afectar el stock, la persona revisa un resumen y confirma. Cada operación queda atribuida a un usuario y fecha.
- Cantidades enteras positivas, disponibilidad no negativa, motivos obligatorios en consumo y merma, traslados entre ubicaciones distintas, transacciones atómicas y clave de idempotencia para evitar doble aplicación.
- Datos conservados en un volumen de PostgreSQL al reiniciar o reconstruir contenedores.
- Los formularios de producto y movimiento se abren como ventanas centradas sobre la pantalla actual. La revisión del movimiento continúa antes de guardar stock.

## Alias de responsables

Cada perfil tiene un `alias` de hasta 40 caracteres en PostgreSQL. Se cambia desde **Configurar alias**, al pie de la barra izquierda. El correo sigue siendo la credencial de acceso y aparece en el bloque de cuenta de esa barra; el resumen, historial y encabezado muestran el alias. Cada usuario solo puede cambiar el suyo; enviar otros campos en el formulario no modifica el rol ni el correo.

La migración `0003_userprofile_alias` asigna un alias inicial a las cuentas existentes a partir de su nombre de usuario; las cuentas demo nuevas se crean como **Dueño** y **Empleado**. Los movimientos continúan relacionados con la cuenta real mediante `Movement.created_by`. Al cambiar el alias, también cambia el nombre visible en movimientos anteriores, porque el historial consulta el alias vigente; el autor registrado y el stock no se modifican.

## Iniciar en Windows con Docker Desktop

1. Copia `.env.example` como `.env` y reemplaza **todos** los valores que dicen `replace-with-...` por claves y contraseñas propias. `.env` está excluido del repositorio. También puedes conservar el `.env` local que se entregó junto al proyecto.
2. En esta carpeta, ejecuta:

   ```powershell
   docker compose build
   docker compose run --rm web python manage.py migrate --noinput
   docker compose run --rm web python manage.py seed_demo
   docker compose up -d web
   ```

3. Abre <http://localhost:8000>. Usa las cuentas definidas por `DEMO_OWNER_EMAIL`, `DEMO_OWNER_PASSWORD`, `DEMO_EMPLOYEE_EMAIL` y `DEMO_EMPLOYEE_PASSWORD` en tu `.env` local.
4. Para detener sin borrar datos: `docker compose down`. Para iniciar de nuevo: `docker compose up -d web`. **No** uses `docker compose down -v` si quieres conservar los datos.

`seed_demo` es idempotente: repetirlo no duplica cuentas ni existencias iniciales. Las contraseñas de cuentas ya existentes no cambian al repetirlo.

La web escucha solo en `127.0.0.1:8000`; PostgreSQL no publica un puerto. Estas credenciales son exclusivas de la demo local. Antes de una futura publicación con acceso externo se deberá configurar HTTPS, dominio, secretos nuevos y políticas de operación.

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
compose.yaml                    web + PostgreSQL; trabajador futuro opcional
```

La lógica de stock se concentra en `register_movement`. Las futuras entradas desde OCR deberán terminar en el mismo servicio **después** de revisión humana. La integración ESP32 tendrá su propio adaptador de ingesta y modelos de medición; el proceso `worker` queda reservado, sin simular lecturas ni correos. La elección y prueba de OCR, sensores, alertas, chatbot, conversiones, reversos, fotografías y despliegue AWS corresponde a próximas entregas.

## Fuentes de requisitos

Esta etapa toma las reglas de los documentos `especificaciones_mvp_inventario_chocolate` v1.1 y `arquitectura_mvp_inventario_chocolate` v0.1. Las decisiones técnicas del documento de arquitectura se trataron como propuestas; para esta demo se eligió Django 6.0, PostgreSQL 17 y Docker Compose. [Documentación oficial de Django 6.0](https://docs.djangoproject.com/en/6.0/).
