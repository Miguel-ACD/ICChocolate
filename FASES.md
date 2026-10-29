# Plan por fases y línea de base de ICChocolate

Fecha de revisión: 27 de octubre de 2026 (America/Lima).
Referencias: `D:\UTEC\ICC_PROYECTO\especificaciones_mvp_inventario_chocolate (2).md` v1.1 y `D:\UTEC\ICC_PROYECTO\arquitectura_mvp_inventario_chocolate (2).md` v0.1. Son referencias funcionales y técnicas; las propuestas del segundo documento se revisan antes de convertirlas en reglas.

## Decisiones acordadas

- Las correcciones de movimientos confirmados se harán mediante reverso completo con motivo y, si corresponde, un movimiento nuevo correcto. No se borra el historial. Si el reverso dejaría un saldo negativo, se rechaza íntegramente.
- OCR y chatbot: preferencia inicial por herramientas locales y gratuitas. La comparación de la fase 5 justificó provisionalmente Gemini Free Tier para las fotos ficticias de la demo; el chatbot sigue pendiente de evaluación local.
- Las diez fotografías físicas ficticias aportadas por el usuario se conservaron como muestras reproducibles de la fase 5.
- La demo en AWS usará los créditos de la cuenta nueva con objetivo de cero gasto de bolsillo. Antes de crear recursos se verificarán plan, créditos restantes, fecha de vencimiento, región, estimación y límites. No se cambia a un plan que pueda generar cargos sin decisión expresa.
- Cada fase exige pruebas automáticas, recorridos manuales y evidencia; mocks y datos simulados se identifican como tales.

## Estado comprobado al iniciar el plan

El código local está en `main` en el commit `a62fed6` y sin cambios previos a esta revisión. La aplicación existente usa Django 6, PostgreSQL 17 y Docker Compose. Hay inventario manual, dos perfiles, movimientos de compra/venta/consumo/merma/traslado, historial y recepción del ESP32. El envío HTTPS por Tailscale Funnel se había verificado entre redes, pero Funnel está desactivado durante esta fase local. No se modificaron `.env`, `secrets.h` ni el volumen de PostgreSQL.

La fase 1 arrancó `db` y `web` localmente. `sensor-gateway` quedó detenido. La web responde en `http://127.0.0.1:8001/`; PostgreSQL no expone un puerto público.

## Fases y criterios de salida

| Fase | Entrega | Pruebas mínimas de cierre |
| --- | --- | --- |
| 1. Base local y diferencias | Entorno y datos existentes comprobados; brechas documentadas | Salud, migraciones, 41 pruebas en base temporal, acceso real de ambos roles, permisos y persistencia tras reinicio |
| 2. Inventario completo | Equivalencias, conversiones, reversos y administración pendiente | Compra, venta, traslado, conversión, fallo atómico, idempotencia, simultaneidad, permisos y saldo reconstruible |
| 3. Sensor local completo | Identidad y zona de dispositivo, ciclos válidos e inválidos, historial y desconexión | Promedio, duplicado, conflicto, dato inválido, 180 s sin datos, segundo dispositivo simulado y un ciclo físico real |
| 4. Alertas y correo | Umbral, episodios, avisos web y trabajador SMTP | Límite exacto, inicio, recordatorio, recuperación, reinicio, cambio de regla, fallo SMTP y correo real de prueba |
| 5. Cámara y OCR | Fotos privadas, preparación de imagen y propuestas revisables | JPEG/PNG, tamaño, legibilidad, ambigüedad, corrección humana, compra y venta con foto real desde celular |
| 6. Chatbot local | Consultas de solo lectura con fuentes y fecha | Respuestas contra datos conocidos, ambigüedad, dato antiguo, intento de escritura y fallo del motor |
| 7. Cierre local | Recorrido integral, respaldo y restauración | Suite completa, sensor y correo físicos, foto real, reinicio y restauración en volúmenes nuevos |
| 8. Despliegue AWS | Aplicación en nube con HTTPS y persistencia | Presupuesto verificado, acceso, permisos, movimiento, foto, correo, respaldo y reinicio |
| 9. Integración final en nube | ESP32 físico, cámara y alertas sobre la instalación desplegada | Lectura nueva y real en PostgreSQL de nube, foto desde celular, movimiento confirmado, alerta y correo reales |

## Resultado de la fase 1

- `docker compose run --rm web python manage.py makemigrations --check --dry-run`: sin cambios.
- `docker compose exec -T web python manage.py migrate --check`: sin migraciones pendientes.
- 41 pruebas automatizadas contra una base PostgreSQL temporal: aprobadas; la base de prueba fue destruida al terminar.
- `GET /salud/`: HTTP 200 y base `ok`, antes y después del reinicio.
- Inicio de sesión HTTP de dueño y empleado: exitoso. Inventario devuelve 200 para ambos. Creación de producto devuelve 200 al dueño y 403 al empleado.
- Antes y después de reiniciar `db` y `web`: 6 movimientos, 59 lecturas del sensor, 6 posiciones de stock y 57 unidades. No se hicieron movimientos de inventario durante esta fase.
- `icchocolate-db-1` y `icchocolate-web-1` quedaron activos; `sensor-gateway` y Tailscale Funnel permanecen detenidos.

## Brechas respecto a los documentos

- Inventario: aún faltan equivalencias, conversiones, borradores editables/versionados y reversos. El servicio actual confirma movimientos manuales directamente tras una pantalla de revisión.
- Sensor: la implementación actual usa un token compartido y `reading_id`; los documentos proponen dispositivos con identidad y asignación histórica por zona, ciclos inválidos y contrato `/api/v1/dispositivos/me/ciclos`. No se cambiará el firmware sin plan de migración y nueva prueba física.
- Alertas: no existen reglas, episodios ni correo; el trabajador actual es solo un marcador de futuro.
- Fotos y chatbot: aún no existen. El volumen persistente de fotos debe añadirse antes de probar la cámara.
- `QA.md` describe la primera demo del 19 de octubre; su lista de límites es histórica y no refleja la recepción posterior del ESP32. Este archivo registra la línea de base actual.

La fase 1 queda cerrada con las pruebas anteriores. La fase 2 comenzará por modelar equivalencias y reversos sin alterar los movimientos históricos ni los datos del volumen existente.

## Cierre de la fase 2 (27 de octubre de 2026)

La fase 2 añadió equivalencias dirigidas, conversiones atómicas, reversos completos con motivo, borradores persistentes con versión, administración de catálogo y cuentas, y dos equivalencias ficticias idempotentes. Se separó autor del borrador y confirmador en los movimientos nuevos. Los movimientos anteriores y las lecturas del sensor se conservaron.

Se creó un respaldo privado de PostgreSQL antes de aplicar la migración `0005`; no se modificó ni borró el volumen. La prueba `scripts/verify_phase2.ps1` pasó: 55 pruebas automatizadas en una base temporal de PostgreSQL, formularios y permisos HTTP para ambos roles, reinicio y comparación de datos. La base habitual siguió con 6 movimientos, 59 lecturas y 57 unidades; contiene 2 equivalencias activas. Web y DB están activos localmente; gateway y Funnel siguen apagados.

Alcance pendiente para fases posteriores: múltiples renglones de una foto y confirmación conjunta en fase 5; identidad y zonas de dispositivos en fase 3; alertas en fase 4. La fase 2 no declara esos recorridos completados.

## Cierre de la fase 3 (27 de octubre de 2026)

Se incorporaron identidad y token por dispositivo, asignación histórica de zona, ciclos válidos e inválidos, historial, estado de comunicación y administración para el dueño. La ruta v1 convive con la anterior. Las 59 lecturas anteriores quedaron vinculadas a ESP32-01 sin cambiar sus valores. Antes de migrar se creó un respaldo privado; no se eliminó el volumen.

`scripts/verify_phase3.ps1` pasó con 65 pruebas automatizadas en PostgreSQL temporal, accesos y permisos HTTP de ambos roles, gateway con rechazo de token incorrecto, reinicio y persistencia. El firmware compiló y el token privado del firmware, servidor y base coincide sin exponer su valor. Funnel HTTPS está activo y solo publica el gateway; Inventario devuelve 404 y un token falso devuelve 401.

El firmware v1 se grabó y verificó en el ESP32 físico. Tras cambiar a otro puerto USB por reinicios de alimentación, Windows lo detectó en COM30. El monitor serie registró cuatro muestras reales y promedio de 28.17 °C y 60.88 % HR; Funnel devolvió HTTP 201. PostgreSQL guardó el ciclo nuevo como `VALIDO`, `4/4`, `ESP32-01`, zona Almacén, a las 14:56:27 de Lima (19:56:27 UTC), con esos mismos valores. El conteo pasó de 59 ciclos históricos a 61 al comprobarlo; las pruebas simuladas permanecieron en la base temporal. La fase queda cerrada tras la verificación final y el commit/push.

## Cierre de la fase 4 (27 de octubre de 2026)

Se añadieron reglas de temperatura versionadas por dispositivo, episodios de inicio, recordatorio y recuperación, suspensión por 180 segundos sin datos válidos, avisos web por usuario y una cola SMTP persistente con estados pendiente, aceptado, fallido, incierto y cancelado. El dueño administra umbrales y destinatarios; el empleado consulta las alertas. La humedad no tiene una regla inicial. Los correos inciertos no se reenvían automáticamente.

Antes de la migración `0007` se creó un respaldo privado de PostgreSQL; se conservaron los 76 ciclos que había en ese momento, los 6 movimientos, las 57 unidades y el volumen. `scripts/verify_phase4.ps1` pasó con 77 pruebas automatizadas en base temporal, permisos HTTP de ambos perfiles, reinicio y persistencia, trabajador activo y avisos web vinculados al sensor real. Las pruebas simuladas no se insertaron en la base habitual.

Se configuró Gmail SMTP con credencial privada en `.env` (fuera de Git). La lectura física de `ESP32-01` recibida a las 15:17:26 de Lima (20:17:26 UTC), con 28.70 °C y 59.88 % HR, abrió un episodio bajo la regla restaurada de 10 °C. Gmail aceptó el aviso inicial a las 15:17:36, con un solo intento. También aceptó un recordatorio de un episodio anterior. El usuario confirmó que llegaron ambos mensajes al buzón. Tras reiniciar el trabajador, ambos conservaron estado aceptado e intento 1, sin reenvío. El cambio temporal de umbral para generar el evento real quedó trazado en las versiones 2 y 3; la versión vigente volvió a 10 °C.

Al iniciar la fase 5 se solicitarán fotografías reales de etiquetas y boletas para evaluar OCR local y revisión humana. La cuenta de AWS todavía no se usa.

## Fase 5: evaluación y cierre local (27 de octubre de 2026)

El usuario entregó diez fotos de celular: dos de la boleta de cuatro renglones y dos de cada una de las cuatro etiquetas. Son fotografías físicas de material de prueba, no imágenes generadas ni datos ingresados en inventario. La boleta y etiquetas son ficticias, sin valor fiscal.

**Decisión inicial de evaluación:** probar OCR **local** antes de adoptar una API. Tesseract con datos de español e inglés fue el primer candidato porque se ejecuta dentro del contenedor y no cobra por página. Amazon Textract tiene cuota gratuita temporal y cobro por página después; no se adoptó con el requisito de gasto cero. La comparación de visión gratuita posterior, al final de esta sección, actualiza la elección provisional para la demo.

La evaluación reproducible `scripts/evaluate_phase5_photos.py` preparó cada foto a JPEG, hasta 1600 px, y probó Tesseract 5.3 con orientaciones 0/90/270, imagen original/contraste/umbral y modos de página 6/11. El extractor estricto recuperó códigos de catálogo exactos en **4 de 16 oportunidades** (dos boletas × cuatro códigos + ocho etiquetas), sin atribuir cantidades a las etiquetas. El modo inicial sin búsqueda reconoció 2 de 16. Las fotos comprimidas y de bajo contraste son una dificultad real; este resultado **no cumple aún un criterio de aceptación** y no se usará para confirmar movimientos sin revisión. Tampoco hay un porcentaje mínimo pactado todavía.

La primera mitad implementa validación de JPEG/PNG, límite de 5 MB y 20 MP, orientación EXIF, reducción sin ampliar a 1600 px, JPEG calidad 85 sin metadatos, hash SHA-256, almacenamiento privado en volumen separado y rutas autenticadas para cargar y ver una copia. Añade un adaptador OCR local y propuestas solo por código exacto. Una foto subida **no crea borrador, movimiento ni cambio de stock**.

La migración `0008_photo_document` se aplicó tras guardar y validar `backups/icchocolate_pre_fase5.dump` (privado, excluido de Git). Las **85 pruebas automatizadas** pasaron en una base PostgreSQL temporal después de añadir la prueba de puntuación de visión; `makemigrations --check --dry-run` no detectó diferencias y `migrate --check` confirmó la base habitual. La salud de la web devolvió HTTP 200. DB, web, gateway y trabajador quedaron activos; las fotos de evaluación no se insertaron en la base habitual.

La segunda mitad añadió la pantalla móvil `/documentos/nuevo/` y la revisión `/documentos/<grupo>/revisar/`. La extracción por Gemini guarda propuestas con código, cantidad opcional y evidencia; los códigos desconocidos se señalan para elegir manualmente. En etiquetas se descarta siempre la cantidad propuesta. El usuario puede añadir hasta ocho fotos, corregir o descartar renglones, completar otros manualmente y elegir compra o venta y ubicación. Solo la confirmación humana ejecuta una transacción atómica de varios renglones. El movimiento registra confirmador, fecha y fotos; una misma operación es idempotente y una foto exacta ya confirmada no se reutiliza. Ante cuota gratuita agotada, error de red o respuesta inválida, el formulario manual sigue disponible.

Las **95 pruebas automatizadas** pasaron contra PostgreSQL temporal, incluidas regresiones de fases anteriores, permisos, límites de imagen, propuestas ambiguas, fallo simulado de Gemini, revisión humana, compra y venta, stock insuficiente, idempotencia y foto repetida. Una prueba integrada carga una de las fotos reales tomadas por celular como archivo y confirma sus cuatro renglones **con respuesta de IA simulada**; no toca la base habitual. La comparación independiente de las diez fotos sí usó Gemini real. `makemigrations --check --dry-run` y `migrate --check` quedaron limpios. Antes de la migración `0009` se validó y guardó un respaldo privado; la base habitual quedó con 6 movimientos, 57 unidades y 0 fotos de prueba. `/salud/` respondió HTTP 200 y `db`, `web`, `sensor-gateway` y `worker` están activos.

La fase 5 queda cerrada para la demo local con las diez muestras disponibles. La muestra corresponde a cinco pares de un mismo material ficticio, por lo que la tasa observada no predice precisión para documentos nuevos. La carga desde el navegador físico del teléfono y la integración sobre nube quedan para los recorridos integrales de fases 7 y 9; no se afirma que se hayan realizado. Si Gemini agota cuota en un uso futuro, se repetirá la verificación externa; el flujo manual ya está probado.

**Verificación ampliada posterior al cierre:** se añadieron seis pruebas de regresión para rollback de un segundo renglón sin stock, presentación desactivada, foto duplicada dentro de un grupo, doble envío HTTP, respuesta 429 de Gemini y acceso de otro empleado. La suite normal pasó con **102 pruebas descubiertas, una externa omitida**; las 101 restantes se ejecutaron en PostgreSQL temporal. `scripts/verify_phase4.ps1` pasó de extremo a extremo: salud, acceso de ambos roles, gateway, alertas y persistencia tras reiniciar DB/web; la base habitual mantuvo 6 movimientos y 57 unidades. `scripts/verify_phase5.ps1` pasó para ambos perfiles con cámara, CSRF, carga inválida, 404 de revisión inexistente, inventario y cuatro contenedores activos. La prueba opcional omitida en CI se ejecutó por separado contra **Gemini real** con una foto física de boleta en base temporal y obtuvo los cuatro códigos y cantidades esperados, sin crear stock ni movimientos; no sustituyó la revisión humana ni escribió en la base habitual.

### Comparación de IA de visión que motivó la elección

Tras la baja recuperación de Tesseract, se probó `gemini-3.6-flash` con la clave privada de un proyecto que AI Studio mostraba como **Nivel gratuito**. Se enviaron las mismas diez copias JPEG preparadas; ninguna foto ni salida se insertó en PostgreSQL. La solicitud incluía los cuatro códigos del catálogo, igual que el extractor local, y exigía cantidad vacía en etiquetas. El modelo `gemini-2.5-flash` no estaba disponible para usuarios nuevos; `gemini-3.8-flash` respondió 503 por alta demanda. `gemini-3.6-flash` completó las diez fotos con resultados guardados en `materials/fase5_pruebas/vision_gemini-3.6-flash_results.jsonl`.

Resultado medido: **16/16 códigos exactos**, **8/8 cantidades correctas** en las dos fotos de la boleta, **0/8 cantidades inventadas** en etiquetas y **0 códigos extra**. El benchmark local previo fue 4/16 códigos. Esto justifica elegir **visión por API en Free Tier** para la demo, con revisión humana obligatoria y registro manual cuando haya cuota, red o respuesta insuficiente. No se habilitó facturación ni se supone gratuidad ilimitada. Diez fotos del mismo material ficticio no prueban precisión sobre otras boletas o etiquetas; se ampliará el conjunto en la fase 7. [Precios oficiales de Gemini](https://ai.google.dev/gemini-api/docs/pricing).

El nivel gratuito de Gemini permite usar las fotos ficticias de prueba sin cargos en este proyecto, pero sus términos de precios indican que los datos del nivel gratuito pueden usarse para mejorar productos. Antes de procesar boletas reales con datos personales se revisará esta decisión. La clave privada está en `.env`, fuera de Git; la clave compartida accidentalmente en el chat se revocó y sustituyó por una nueva según confirmó el usuario.

## Cierre de la fase 6 (28 de octubre de 2026)

Se implementó un asistente **local y gratuito** de consultas acotadas, sin modelo generativo ni API externa. El alcance de preguntas del MVP es finito y los datos provienen de PostgreSQL; una selección determinista de consultas permite mostrar cantidades verificables y evitar SQL o código generado por texto del usuario. El asistente no guarda conversaciones. La web `/chat/` y la API `POST /api/v1/chat` exigen sesión y perfil activo; dueño y empleado pueden consultar. Las respuestas incluyen fecha de consulta y enlaces a inventario, movimiento específico, monitoreo o episodio de alerta. Los resultados se acotan a 10 posiciones de stock, 5 movimientos o alertas y un catálogo de hasta 200 presentaciones para búsqueda por nombre.

Responde existencias por presentación y ubicación, descripción de una unidad, últimos movimientos, última medición válida, umbral y alertas. Si un producto tiene varias presentaciones pide código exacto; si no hay datos lo indica. Una medición mayor de 180 segundos se marca antigua y no se presenta como estado actual. Las órdenes de escritura reciben una negativa y no pasan a servicios de inventario. Un fallo del motor o de PostgreSQL muestra indisponibilidad del asistente sin bloquear Inventario ni Monitoreo. No se añadieron credenciales, pagos, servicios ni migraciones.

Las **116 pruebas descubiertas** pasaron en PostgreSQL temporal: 115 ejecutadas y la prueba externa opcional de Gemini omitida. Las 14 nuevas pruebas de fase 6 cubren datos conocidos, fuente exacta, ambigüedad, dato inexistente y antiguo, ciclo inválido, alerta/umbral, permiso de ambos roles, longitud y formato de entrada, intento de escritura, SQL de solo lectura, contenido HTML no confiable y fallo del motor. `makemigrations --check --dry-run` no detectó cambios. `scripts/verify_phase6.ps1` pasó por HTTP con dueño y empleado, respuesta API con fecha/fuente, rechazo de escritura, salud e inventario convencional. Antes y después del recorrido la base habitual mantuvo **6 movimientos, 0 fotos de prueba y 57 unidades**; `db`, `web`, `sensor-gateway` y `worker` quedaron activos.

## Cierre de la fase 7 (28 de octubre de 2026)

La web conserva `127.0.0.1:8001` en Windows y ofrece `192.168.18.244:8003` en la Wi-Fi local **Carlos Win** mediante `ICCHOCOLATE_WEB_BIND` en el `.env` privado. El usuario abrió la página e inició sesión desde el celular. El gateway del sensor continúa en `127.0.0.1:8002`; PostgreSQL no expone puerto.

La primera foto móvil dejó al descubierto un fallo real: la subida guardaba el archivo, pero el análisis síncrono de Gemini superó los 30 segundos del trabajador web y el teléfono recibió HTTP 500. También `capture="environment"` forzaba la cámara en Android. Se corrigió el flujo: subir abre de inmediato la revisión, **Analizar con IA** es una acción separada y el selector admite cámara o archivo. El servidor da hasta 60 segundos a la consulta externa, cuyo límite propio es 45 segundos; si no responde, queda la revisión manual. Las pruebas de fotos se actualizaron para comprobar que Gemini no se invoca durante la subida. La foto fallida quedó como documento pendiente, sin movimiento ni cambio de stock.

En el segundo recorrido, el usuario eligió una foto física desde el celular, la subió, pulsó **Analizar con IA** y confirmó que la propuesta apareció. Gemini real propuso `BARRA-100` con cantidad vacía, como corresponde a una etiqueta. El usuario revisó y confirmó una compra ficticia de **1 BARRA-100 en Almacén** a las 21:04:05 de Lima; PostgreSQL registró la foto, el movimiento, el confirmador y el aumento temporal de 57 a 58 unidades. Después se creó un reverso auditado con motivo; el saldo volvió a **57**, con ambos movimientos conservados. No se atribuye a la IA la cantidad que eligió la persona.

`scripts/verify_phase7.ps1` pasó: **116 pruebas descubiertas, 115 ejecutadas y una prueba externa opcional omitida**, además de permisos y recorridos HTTP de fases 1 a 6, reinicio de DB/web, persistencia de **8 movimientos, 2 fotos, 1 foto confirmada y 57 unidades**, salud de PostgreSQL y acceso por la IP local. La última lectura física verificada de `ESP32-01` tras el reinicio fue el ciclo 239, válido `4/4`, recibido a las **21:08:37 de Lima**, con **27.78 °C** y **61.35 % HR**. Los datos simulados de la suite estuvieron en una base temporal. Gmail aceptó siete avisos vinculados al ESP32 en total; el más reciente se aceptó a las **20:51:31 de Lima** como recordatorio del episodio iniciado por el ciclo 218. La entrega a la bandeja se verifica por separado con el usuario.

Se validó el respaldo privado `backups/icchocolate_fase7_final_20261028.dump` y se guardó también `backups/icchocolate_fase7_photos_20261028.tar.gz`, ambos fuera de Git. La base y las fotos se restauraron en los volúmenes **nuevos** `icchocolate_fase7_restore_postgres_data` y `icchocolate_fase7_restore_photo_data`. Django abrió la copia, `migrate --check` pasó y la restauración contenía **8 movimientos, 2 fotos, 1 foto confirmada, 237 ciclos al momento del respaldo y 57 unidades**. Los SHA-256 de las dos fotos restauradas coincidieron con los registros. El contenedor aislado quedó detenido; sus volúmenes y los originales se conservaron. Los cuatro servicios de la aplicación principal permanecen activos.
