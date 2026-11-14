from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import views

router = DefaultRouter()
router.register(r"stock", views.StockViewSet, basename="stock")
router.register(r"movements", views.MovementViewSet, basename="movement")
router.register(r"sensor-readings", views.SensorReadingViewSet, basename="sensorreading")
router.register(r"alerts", views.AlertEpisodeViewSet, basename="alertepisode")

urlpatterns = [
    # JWT authentication
    path("token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # Dashboard summary
    path("dashboard/", views.dashboard_summary, name="api_dashboard_summary"),
    # Monitoring API (device selector + readings)
    path("monitoring/", views.monitoring_data, name="api_monitoring"),
    # Catalog data (presentations, locations, equivalences, movement types)
    path("catalog/", views.catalog_data, name="api_catalog"),
    # Drafts (list, create)
    path("drafts/", views.drafts_view, name="api_drafts"),
    path("drafts/<uuid:draft_id>/confirm/", views.draft_confirm, name="api_draft_confirm"),
    path("drafts/<uuid:draft_id>/cancel/", views.draft_cancel, name="api_draft_cancel"),
    # Photo group confirmation with rows
    path("photo-confirm/", views.photo_confirm, name="api_photo_confirm"),
    # Photo upload (with Gemini vision)
    path("photos/", views.upload_photo, name="api_upload_photo"),
    # Chat with AI assistant
    path("chat/", views.chat, name="api_chat"),
    # Expo push-notification token
    path("expo-token/", views.register_expo_token, name="api_expo_token"),
    # DRF router
    path("", include(router.urls)),
]

