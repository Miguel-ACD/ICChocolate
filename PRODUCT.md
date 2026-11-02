# ICChocolate · contexto del producto

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Dueño y empleado de una repostería pequeña. Usan la aplicación para registrar entradas y salidas de productos, consultar existencias y revisar el ambiente del almacén. La interfaz debe resultar comprensible para personas no técnicas.

## Product Purpose

Mantener existencias por presentación y ubicación con movimientos confirmados y trazables, mostrar las lecturas del ESP32/DHT11 y avisar de desviaciones térmicas. La prueba de escritorio prioriza que registrar un movimiento sea inmediato y evidente.

## Positioning

Combina operaciones de inventario revisables, registro asistido por fotos y monitoreo ambiental real en una sola demo de repostería. Las propuestas de IA no alteran el stock hasta que una persona confirma.

## Operating Context

La demo se usa en una PC Windows con Docker Desktop y PostgreSQL; también se ha probado desde un celular en la misma Wi-Fi. El usuario trabaja con presentaciones de barras, cajas, polvo y chispas, fotos de boletas o etiquetas, y un ESP32 con DHT11 asociado a una zona.

## Capabilities and Constraints

- Dos perfiles con permisos distintos; el empleado registra operaciones y el dueño administra catálogo, cuentas, reglas y dispositivos.
- Compras, ventas, consumo, merma, traslado, conversión y reverso trazable. Solo los movimientos confirmados cambian existencias.
- Fotos privadas con propuestas de Gemini Free Tier, revisión humana y camino manual si la IA falla o agota cuota.
- Lecturas y alertas con correo; el asistente de consulta es local y de solo lectura.
- Conservar el backend, los datos, las rutas y los controles existentes durante el rediseño. El trabajo de esta prueba permanece local, sin commit ni push.
- No introducir servicios de pago. La futura demo en AWS requiere revisar créditos y límites antes de crear recursos.

## Brand Commitments

Conservar el nombre ICChocolate y la familia de colores cacao y crema. Para este rediseño el usuario eligió una sensación amigable y cálida, con prioridad visual en registrar movimientos. Se acepta una renovación visual casi completa del escritorio.

## Evidence on Hand

- Datos ficticios de catálogo y movimientos en PostgreSQL; no se presentan como inventario comercial real.
- Fotos físicas de materiales de demostración y una prueba real de carga desde celular, análisis con IA y movimiento confirmado con reverso posterior.
- Lecturas físicas verificadas del ESP32 y correo de alerta recibido en la fase local.

## Product Principles

1. Hacer obvia la siguiente acción sin ocultar el estado actual.
2. Explicar cada cambio de inventario antes de confirmarlo.
3. Distinguir datos reales del sensor, datos antiguos y pruebas simuladas.
4. Mantener rutas claras de recuperación cuando la IA o el sensor no respondan.
