# QA de la primera demo

> Registro histórico del 19 de octubre. Para el estado actual, fases y pruebas recientes, consulta `FASES.md`.

## Resultado comprobado el 19 de octubre de 2026

- La imagen Docker se construyó y PostgreSQL inició con el volumen `postgres_data`.
- Las migraciones se aplicaron y `seed_demo` creó dos cuentas, tres productos, cinco presentaciones y cinco movimientos iniciales. Stock inicial: 57 unidades distribuidas en cinco posiciones.
- Las 32 pruebas automáticas de PostgreSQL comprueban recorridos completos, formularios manipulados, CSRF, permisos, doble confirmación, operaciones vencidas entre vista previa y confirmación, idempotencia y ventas concurrentes.
- En el navegador, el dueño inició sesión, revisó inventario e hizo un traslado de **2 barras BARRA-100 de Display a Almacén**. El historial mostró `-2` en Display y `+2` en Almacén. El inventario mostró 22 y 2 respectivamente.
- Tras reiniciar los contenedores de web y base de datos, el inventario siguió mostrando 22 y 2. Total: 57.
- Repetir `seed_demo` dejó seis movimientos (cinco iniciales y el traslado de QA) y 57 unidades: no duplicó la carga inicial.

## Pruebas adversas añadidas

- Rechazo de cantidades decimales, booleanas, negativas, excesivas y motivos mal formados sin escritura parcial.
- Si otro usuario consume stock tras la vista previa, la confirmación rechaza la venta obsoleta.
- Un producto o ubicación desactivado antes de confirmar no se puede usar.
- Doble confirmación, reintentos simultáneos con la misma clave y claves reutilizadas por otra cuenta no duplican stock.
- Los códigos de catálogo son únicos sin distinguir mayúsculas incluso a nivel de base de datos.
- Una cuenta desactivada no puede registrar movimientos.
- Una secuencia seudoaleatoria reproducible contrasta el saldo con la suma de movimientos confirmados tras cada paso.
- La carga de demostración se prueba automáticamente para asegurar que repetirla no duplica existencias ni restablece contraseñas cambiadas.

## Recorrido para la presentación

1. Inicia sesión como dueño y abre **Resumen**. Explica las 57 unidades ficticias y los movimientos de carga inicial.
2. Abre **Inventario**. Busca una presentación por código y muestra las ubicaciones.
3. Ve a **Nuevo movimiento**. Selecciona `Traslado`, una presentación con stock, una cantidad válida, ubicación de origen y destino distintos. La pantalla siguiente permite revisar antes de confirmar.
4. Confirma y abre **Historial** para mostrar responsable, fecha y los dos efectos del traslado.
5. Vuelve a **Inventario** para observar que el total se conserva.
6. Intenta una venta mayor al stock disponible. Debe aparecer “Stock insuficiente” y no debe crearse un movimiento.
7. Intenta enviar el formulario sin presentación, cantidad o ubicación. Debe señalar los campos faltantes y no registrar nada.
8. Inicia sesión como empleado. Puede comprar, vender y trasladar, pero no debe poder abrir las rutas de creación de productos o ubicaciones; el servidor responde 403.
9. Regresa como dueño y crea un producto. Después registra una compra manual para darle stock.

## Límites de esta etapa

La demo todavía no hace OCR, carga de fotografías, conversiones, correcciones de movimientos confirmados, ingestión ESP32, alertas, correo, chatbot ni despliegue AWS. Las pantallas no muestran mediciones ficticias como si provinieran de hardware real.
