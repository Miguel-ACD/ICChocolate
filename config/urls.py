from django.urls import include, path
from inventory import views
from inventory import sensors

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("accounts/login/", views.login_view, name="login"),
    path("accounts/logout/", views.logout_view, name="logout"),
    path("accounts/alias/", views.alias_settings, name="alias_settings"),
    path("inventario/", views.inventory_list, name="inventory"),
    path("api/sensor/lecturas/", sensors.sensor_ingest, name="sensor_ingest"),
    path("api/sensor/ultima/", sensors.sensor_latest, name="sensor_latest"),
    path("movimientos/nuevo/", views.movement_new, name="movement_new"),
    path("movimientos/confirmar/", views.movement_confirm, name="movement_confirm"),
    path("movimientos/", views.movement_history, name="movement_history"),
    path("catalogo/productos/nuevo/", views.product_new, name="product_new"),
    path("catalogo/ubicaciones/nueva/", views.location_new, name="location_new"),
    path("salud/", views.health, name="health"),
]
