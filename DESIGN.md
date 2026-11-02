---
name: ICChocolate
description: Mesa de trabajo cálida para registrar y consultar inventario de repostería.
colors:
  chocolate: "#4a3028"
  chocolate-light: "#684336"
  cocoa: "#865441"
  rose: "#dfb9a2"
  ink: "#30231e"
  muted: "#6d5b51"
  line: "#e8dbcd"
  surface: "#fffdf8"
  background: "#f8f3eb"
  action: "#704332"
  action-hover: "#563326"
  manual-choice: "#623d2e"
  stage: "#ecd9c6"
  photo: "#fffaf3"
  alert-calm: "#e9f2e9"
  alert-calm-ink: "#29533b"
  alert-active: "#fff0de"
  alert-active-ink: "#814524"
typography:
  headline:
    fontFamily: '"Fraunces ICC", Georgia, serif'
    fontSize: "32px"
    fontWeight: 700
    lineHeight: 1.16
    letterSpacing: "-.03em"
  title:
    fontFamily: '"Fraunces ICC", Georgia, serif'
    fontSize: "23px"
    fontWeight: 700
    letterSpacing: "-.025em"
  body:
    fontFamily: '"Segoe UI", Arial, sans-serif'
    fontSize: "15px"
  label:
    fontFamily: '"Segoe UI", Arial, sans-serif'
    fontSize: "13px"
    fontWeight: 650
rounded:
  control: "10px"
  field: "9px"
  panel: "14px"
  choice: "15px"
  stage: "20px"
spacing:
  choice-gap: "13px"
  workbench-gap: "22px"
  panel-inset: "29px"
  stage-inset: "31px"
  page-gutter: "34px"
components:
  button-primary:
    backgroundColor: "{colors.action}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "10px 17px"
    height: "43px"
  button-primary-hover:
    backgroundColor: "{colors.action-hover}"
  button-outline:
    backgroundColor: "{colors.photo}"
    textColor: "{colors.chocolate-light}"
    rounded: "{rounded.control}"
    padding: "10px 17px"
  action-choice-manual:
    backgroundColor: "{colors.manual-choice}"
    textColor: "{colors.surface}"
    rounded: "{rounded.choice}"
    padding: "23px"
    height: "202px"
  action-choice-photo:
    backgroundColor: "{colors.photo}"
    textColor: "{colors.chocolate}"
    rounded: "{rounded.choice}"
    padding: "23px"
    height: "202px"
  snapshot-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.stage}"
    padding: "29px"
  field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.field}"
    height: "44px"
---

# Design System: ICChocolate

## Overview

**Creative North Star: "Mesa de trabajo de repostería"**

Una superficie luminosa de crema y papel con el cacao como tinta y acción. La interfaz es cálida y serena, pero sigue siendo una herramienta de operación: títulos expresivos, controles familiares, datos legibles y pasos de revisión explícitos. La marca aparece en el color, la tipografía y detalles pequeños, sin ilustración decorativa dominante.

La familia cacao y crema es un compromiso de marca. En el escritorio, la opción manual recibe mayor contraste, la ruta con foto queda claramente disponible y la consulta del inventario permanece a la vista. La composición concreta de esa primera pantalla se documenta en `.impeccable/surfaces/inventory-templates-inventory-dashboard-html.md`.

**Key Characteristics:**
- Papel claro, tinta cacao y acentos albaricoque y salvia.
- Fraunces para títulos; Segoe UI para operación y datos.
- Superficies amplias, bordes suaves y separación por tono.
- Estados y recorrido de confirmación visibles antes de cambiar existencias.

## Colors

La paleta usa cacao oscuro para orientar la acción, crema para sostener la lectura y color semántico solo donde expresa el estado real.

### Primary
- **Cacao de acción:** `chocolate` y `action` sostienen la marca y el control principal; `action-hover` confirma la interacción.
- **Cacao medio:** `chocolate-light` y `cocoa` sirven para texto secundario y acentos cálidos.

### Secondary
- **Albaricoque suave:** `rose` y `stage` aportan calidez al área de trabajo sin competir con el botón principal.
- **Salvia de estado:** `alert-calm` y `alert-calm-ink` indican ausencia de alertas activas.
- **Ámbar de atención:** `alert-active` y `alert-active-ink` señalan alertas activas sin convertirlas en decoración.

### Neutral
- **Papel y crema:** `surface`, `photo` y `background` separan panel, ruta secundaria y fondo general.
- **Tinta y apoyo:** `ink` es lectura principal; `muted` baja la jerarquía de la explicación; `line` delimita superficies y tablas.

**The Semantic State Rule.** Los colores de salvia y ámbar se reservan para estados de inventario y alertas; el cacao identifica la acción principal.

## Typography

**Display Font:** Fraunces ICC, alojada localmente en `inventory/static/inventory/fonts/Fraunces.ttf`, con Georgia y serif de respaldo. La fuente variable admite pesos 100–900; los títulos observados usan 700 y los ejes `SOFT` 35 y `WONK` 0.

**Body Font:** Segoe UI, con Arial y sans-serif de respaldo.

**Character:** La serif aporta calidez a los encabezados. La sans conserva la claridad de formularios, navegación, tablas y cifras.

### Hierarchy
- **Headline:** título de página en Fraunces (32px, 700, 1.16), reducido a 26px en móvil.
- **Title:** títulos de área en Fraunces (23px, 700); subtítulos de sección y resumen cercanos a 19–20px.
- **Body:** texto operativo en Segoe UI (15px base); descripciones de panel en 14px con interlínea 1.55.
- **Label:** navegación y etiquetas en Segoe UI (13–14px, peso 650–700); encabezados de tabla en 10px.
- **Data:** números de existencias en Segoe UI con cifras tabulares; el total del resumen se muestra a 62px en escritorio y 52px en móvil.

**The Two Voice Rule.** Fraunces queda en títulos; Segoe UI carga instrucciones, controles, navegación y datos.

## Layout

El escritorio tiene ancho máximo de 1440px y canal lateral de 34px. La cabecera horizontal permanece visible; a 1150px permite otra fila de navegación. El área de trabajo usa una cuadrícula de dos columnas (1.38fr / .72fr) con separación de 22px. A 850px se convierte en una sola columna. A 620px las dos opciones de registro se apilan, la navegación puede desplazarse horizontalmente y el canal de página baja a 17px.

Los paneles principales usan interiores de 29–31px y las opciones de registro 23px; en móvil se reduce el espacio interior. La actividad reciente se coloca debajo de la mesa de trabajo. Las tablas pueden desplazarse horizontalmente cuando su contenido lo exige.

## Elevation & Depth

La profundidad nace primero de la diferencia entre crema, papel y albaricoque, más bordes claros. Los paneles y tablas descansan sin sombra. La sombra aparece en elementos que flotan o reaccionan: botón principal, menú, diálogo y opción de registro al pasar el cursor.

### Shadow Vocabulary
- **Ambient:** `0 12px 34px rgba(65, 38, 28, .08)` está definido como `--shadow` en el rediseño.
- **Acción:** `0 5px 12px rgba(85, 48, 35, .15)` da relieve al botón principal.
- **Menú:** `0 18px 42px rgba(49, 31, 24, .16)` separa el desplegable del encabezado.
- **Diálogo:** `0 25px 65px rgba(44, 27, 20, .26)` expresa la capa modal.

**The Flat Surface Rule.** Paneles y tablas permanecen planos en reposo; reservar el relieve para interacción y superposición.

## Shapes

El lenguaje es suavemente curvo y estable: campos de 9px, botones de 10px, paneles comunes de 14px, opciones de 15px y superficies protagonistas de 20px. Los pasos numerados y las marcas de estado son circulares. Bordes de crema tostada separan contenido sin endurecerlo.

## Components

### Buttons
- **Primary:** cacao oscuro, texto claro, radio de 10px, altura mínima de 43px; oscurece al pasar el cursor.
- **Outline:** papel crema, borde tostado y texto cacao; hover con crema más intensa.
- **Focus:** contorno visible de 3px con separación de 3px; el estado desactivado reduce opacidad a .5.

### Cards / Containers
- **Mesa de acción:** fondo albaricoque y radio de 20px; contiene rutas de registro y pasos.
- **Opciones manual/foto:** radio de 15px, interior de 23px y altura mínima de 202px; la opción manual es cacao oscuro, la foto usa papel claro. En hover ascienden 3px durante .18s.
- **Resumen:** papel claro, borde tostado, radio de 20px e interior de 29px. Mantiene juntas cifra, desglose y alerta.
- **Tabla:** panel claro de 14px; encabezado de crema tostada y filas con hover tenue.

### Inputs / Fields
- **Field:** altura mínima de 44px, borde tostado y radio de 9px.
- **Focus:** borde cacao cálido y halo de 3px; conservar un contorno `:focus-visible` claro para navegación por teclado.

### Navigation
- **Header:** barra clara y horizontal con enlaces de 14px, peso 650. La página activa se reconoce por texto cacao y línea inferior cálida; hover usa crema tostada.
- **Menus:** desplegables de papel claro, radio de 15px y sombra propia. En pantallas estrechas, los enlaces principales admiten desplazamiento horizontal.

### Review steps and status
- **Review steps:** números circulares y tres verbos claros: elegir, revisar y confirmar. Se repiten como guía de la operación, sin simular progreso que aún no ocurrió.
- **Status alert:** salvia cuando no hay alerta y ámbar cuando sí; cada estado incluye texto y enlace, no depende solo del color.

## Do's and Don'ts

### Do:
- **Do** mantener cacao y crema como base de cada pantalla nueva.
- **Do** hacer visible la revisión antes de la confirmación de cualquier movimiento.
- **Do** usar Fraunces en títulos y Segoe UI en los elementos operativos.
- **Do** mostrar alertas y estados reales con texto además de color.

### Don't:
- **Don't** usar salvia o ámbar como adornos que puedan confundirse con un estado.
- **Don't** convertir todos los paneles en tarjetas elevadas; la profundidad tiene una función.
- **Don't** presentar una propuesta de foto o IA como cambio de existencias confirmado.
