# Plan por fases y línea de base de ICChocolate

Fecha de revisión: 27 de octubre de 2026 (America/Lima).
Referencias: `D:\UTEC\ICC_PROYECTO\especificaciones_mvp_inventario_chocolate (2).md` v1.1 y `D:\UTEC\ICC_PROYECTO\arquitectura_mvp_inventario_chocolate (2).md` v0.1. Son referencias funcionales y técnicas; las propuestas del segundo documento se revisan antes de convertirlas en reglas.

## Decisiones acordadas

- Las correcciones de movimientos confirmados se harán mediante reverso completo con motivo y, si corresponde, un movimiento nuevo correcto. No se borra el historial. Si el reverso dejaría un saldo negativo, se rechaza íntegramente.
- OCR y chatbot: preferencia por herramientas locales y gratuitas. Una API externa requeriría una justificación basada en pruebas y una decisión nueva; no se asume de entrada.
- Las fotografías de prueba se pedirán al terminar la fase 4, antes de iniciar la evaluación de la fase 5. No se necesitan ahora.
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
