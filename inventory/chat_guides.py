"""Small, reviewed help index for app navigation; no generated instructions or URLs."""

from django.urls import reverse

from .models import UserProfile


GUIDES = {
    "remove": {
        "owner": False,
        "answer": "Si quieres retirar unidades, abre Registrar movimiento y elige la presentación correspondiente (por ejemplo, BARRA-100), la ubicación y la cantidad. Usa Venta si se vendió, Consumo si se usó o Merma si se perdió; en Consumo y Merma indica el motivo. Revisa y confirma. Si quieres quitar el producto del catálogo, el dueño debe dejar su stock en cero y luego desactivarlo desde Administrar → Catálogo → Editar producto. El historial se conserva. ¿Quieres retirar unidades o desactivar el producto?",
        "links": (("Registrar movimiento", "movement_new"), ("Administrar catálogo", "catalog_admin")),
    },
    "presentation": {
        "owner": True,
        "answer": "Para agregar una presentación, abre Administrar → Crear presentación. Elige el producto, indica el código, el contenido y qué representa una unidad. Guardarla no añade existencias; para eso registra un movimiento de entrada.",
        "links": (("Crear presentación", "presentation_new"), ("Registrar movimiento", "movement_new")),
    },
    "location": {
        "owner": True,
        "answer": "Para crear una zona de almacenamiento, abre Administrar → Crear ubicación. Dale un código y un nombre. Después podrás seleccionarla al registrar movimientos.",
        "links": (("Crear ubicación", "location_new"), ("Registrar movimiento", "movement_new")),
    },
    "product": {
        "owner": True,
        "answer": "El formulario específico es Administrar → Crear producto. Allí escribe el código y nombre del producto y también los datos de su primera presentación: código, nombre, contenido y qué representa una unidad. Guardar no añade stock. Para cargar existencias, registra después una compra.",
        "links": (("Crear producto", "product_new"), ("Crear presentación", "presentation_new"),
                  ("Registrar movimiento", "movement_new")),
    },
    "photo": {
        "owner": False,
        "answer": "Abre Herramientas → Registrar con fotos. Sube una boleta o etiqueta, revisa los datos propuestos y confirma el movimiento solo cuando estén correctos.",
        "links": (("Registrar con fotos", "document_new"),),
    },
    "movement": {
        "owner": False,
        "answer": "Para hacer un movimiento: 1. Abre Registrar movimiento. 2. Elige Compra para sumar unidades, Venta para descontar una venta, Consumo para uso interno, Merma para pérdida o Traslado para mover entre zonas. 3. Selecciona presentación, cantidad y ubicación; Consumo y Merma requieren motivo, y Traslado requiere destino. 4. Pulsa Revisar operación y confirma si todo está correcto. Una salida no puede superar el stock disponible.",
        "links": (("Registrar movimiento", "movement_new"), ("Ver inventario", "inventory")),
    },
    "conversion": {
        "owner": False,
        "answer": "Para convertir presentaciones, abre Herramientas → Convertir presentaciones. Selecciona origen, destino y cantidad; revisa la equivalencia y confirma. Si falta una equivalencia, el dueño debe configurarla en el catálogo.",
        "links": (("Convertir presentaciones", "conversion_new"),),
    },
    "sensor": {
        "owner": True,
        "answer": "Para registrar un ESP32, abre Administrar → Dispositivos y elige Registrar dispositivo. Allí se genera un token que se muestra una sola vez. Para ver mediciones, entra en Monitoreo.",
        "links": (("Dispositivos", "device_list"), ("Monitoreo", "monitoring")),
    },
    "alert": {
        "owner": True,
        "answer": "Para cambiar un umbral, abre Administrar → Umbrales y elige el dispositivo. Para configurar quién recibe correos, usa Administrar → Destinatarios.",
        "links": (("Umbrales", "alert_rules"), ("Destinatarios", "alert_recipients")),
    },
}


def guide_response(user, topic):
    guide = GUIDES[topic]
    owner = UserProfile.objects.filter(user=user, role=UserProfile.Role.OWNER).exists()
    if topic == "remove" and not owner:
        return {"answer": "Para retirar unidades del stock: abre Registrar movimiento, elige la presentación correspondiente (por ejemplo, BARRA-100), la ubicación y la cantidad. Usa Venta si se vendió, Consumo si se usó o Merma si se perdió; Consumo y Merma piden motivo. Revisa y confirma. Si quieres desactivar el producto del catálogo, pídeselo al dueño: primero debe quedar sin stock. ¿Quieres retirar unidades o desactivar el producto?",
                "sources": [("Registrar movimiento", reverse("movement_new"))]}
    if guide["owner"] and not owner:
        if topic == "sensor":
            return {"answer": "Puedes consultar las mediciones en Monitoreo. Registrar o configurar un ESP32 corresponde al dueño.",
                    "sources": [("Monitoreo", reverse("monitoring"))]}
        if topic == "alert":
            return {"answer": "Puedes consultar los episodios en Alertas. Cambiar umbrales o destinatarios corresponde al dueño.",
                    "sources": [("Alertas", reverse("alert_list"))]}
        return {
            "answer": "Esa configuración corresponde al dueño de la tienda. Pídele que la haga desde Administrar. Puedes consultar tus movimientos e inventario con tu cuenta.",
            "sources": [("Inventario", reverse("inventory"))],
        }
    return {"answer": guide["answer"],
            "sources": [(label, reverse(route)) for label, route in guide["links"]]}
