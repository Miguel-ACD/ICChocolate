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

## Preparación del cierre final (11 de noviembre de 2026)

Las fases 1 a 9 se implementaron. El 11 de noviembre la suite local encontró **119 pruebas**: 118 pasaron y se omitió una prueba externa opcional de Gemini. La base de pruebas de PostgreSQL se creó y destruyó sin modificar el inventario habitual.

Se restauró el respaldo final `backups/icchocolate_fase9_20261102.dump` en el volumen aislado `icchocolate_fase9_restore_20261111_postgres`: **10 movimientos, 3 documentos fotográficos y 220 lecturas**. Las fotos se extrajeron al volumen aislado `icchocolate_fase9_restore_20261111_photos`; los tres SHA-256 coincidieron con los registros de la base. Django abrió la copia, `migrate --check` y `check` pasaron. Los volúmenes normales no se reemplazaron.

`https://icchocolate.lat/salud/` respondió 200 con `database: ok`. `https://www.icchocolate.lat/salud/` respondió 301 hacia el dominio principal con certificado válido. Al reiniciar AWS se detectó un defecto de integración: el gateway omitía `X-Forwarded-Proto: https` al transmitir los POST del ESP32 a Django, que contestaba 301. Se corrigió el gateway, se añadieron dos pruebas y se desplegó. Una solicitud sin token recibió 401 en vez de 301. El ESP32 físico en COM30 envió un ciclo nuevo `VALIDO` el **11 de noviembre a las 18:00:39 de Lima**, con **27.60 °C y 64.33 % HR**, registrado en PostgreSQL de AWS. Esta lectura es real; las lecturas de la suite pertenecen a la base temporal.

Se comprobó otro ciclo real a las **18:03:39 de Lima**, con **27.65 °C y 66.00 % HR**. Tras reactivar el trabajador, la base conservaba 20 lecturas recientes conforme a la retención de siete días. Se crearon `backups/icchocolate_pre_final_20261111.dump` y `backups/icchocolate_pre_final_photos_20261111.tar.gz`; se validaron los archivos y sus SHA-256 coincidieron con los del servidor. Ambos están excluidos de Git. La restauración completa comprobada arriba corresponde al respaldo del 2 de noviembre; el respaldo posterior a la demo se volverá a restaurar como evidencia final.

## Evidencias finales por capturar

1. Registrar el estado y presupuesto de AWS antes de la demo; iniciar la instancia `icchocolate-demo` y comprobar los cinco servicios, `/salud/` y la redirección de `www`.
2. Desde computadora y celular, iniciar sesión con dueño y empleado. Mostrar que el empleado registra movimientos, pero recibe 403 al intentar una ruta administrativa del dueño.
3. Fotografiar una etiqueta o boleta ficticia distinta de una ya confirmada. Subirla, ejecutar IA, revisar o corregir código y cantidad, confirmar una compra y una venta, y comprobar foto, usuario, movimiento e inventario. Revertir las operaciones de prueba con motivo.
4. Mostrar una medición física nueva del ESP32 en la tabla y en la gráfica, con hora, cuatro muestras y estado. Capturar el aviso real y el correo recibido; distinguir cualquier simulación usada para probar recuperación.
5. Mostrar el asistente de solo lectura con una respuesta contrastada con Inventario y una consulta sin datos. Mostrar el flujo manual si Gemini no responde.
6. Guardar un respaldo posterior a la demo de PostgreSQL y fotos; verificar su restauración en volúmenes nuevos. Capturar el resultado de la suite y la ausencia de migraciones pendientes.

La evaluación de OCR disponible usó diez fotos del mismo material ficticio. El usuario decidió usar esas fotos para la entrega final. Se presentará el resultado como prueba de esas muestras, sin afirmar una precisión general; la revisión humana seguirá siendo obligatoria. Para una evaluación general futura harán falta boletas y etiquetas diferentes y una tasa mínima acordada para códigos y cantidades.
