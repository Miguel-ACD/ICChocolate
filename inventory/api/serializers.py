from rest_framework import serializers
from inventory.models import (
    AlertEpisode, ExpoPushToken, Location, Movement, MovementLine,
    PhotoDocument, Presentation, Product, SensorReading, Stock,
)


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ["id", "code", "name", "description", "active"]


class PresentationSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = Presentation
        fields = ["id", "code", "name", "unit_description", "content_value",
                  "content_unit", "active", "product", "product_name"]


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ["id", "code", "name", "active"]


class StockSerializer(serializers.ModelSerializer):
    presentation_code = serializers.CharField(source="presentation.code", read_only=True)
    presentation_name = serializers.CharField(source="presentation.name", read_only=True)
    product_name = serializers.CharField(source="presentation.product.name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)
    location_code = serializers.CharField(source="location.code", read_only=True)

    class Meta:
        model = Stock
        fields = ["id", "presentation_code", "presentation_name", "product_name",
                  "location_code", "location_name", "quantity"]


class MovementLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = MovementLine
        fields = ["presentation_snapshot", "location_snapshot", "delta"]


class MovementSerializer(serializers.ModelSerializer):
    lines = MovementLineSerializer(many=True, read_only=True)
    created_by_alias = serializers.CharField(source="created_by.profile.alias", read_only=True)
    confirmed_by_alias = serializers.CharField(source="confirmed_by.profile.alias", read_only=True)
    type_label = serializers.CharField(source="get_type_display", read_only=True)

    class Meta:
        model = Movement
        fields = ["id", "type", "type_label", "reason", "created_at",
                  "created_by_alias", "confirmed_by_alias", "lines"]


class SensorReadingSerializer(serializers.ModelSerializer):
    device_code = serializers.CharField(source="device.code", read_only=True)

    class Meta:
        model = SensorReading
        fields = ["id", "device_code", "status", "temperature_c",
                  "humidity_percent", "received_at"]


class AlertEpisodeSerializer(serializers.ModelSerializer):
    device_code = serializers.CharField(source="device.code", read_only=True)

    class Meta:
        model = AlertEpisode
        fields = ["id", "device_code", "status", "location_snapshot",
                  "threshold_snapshot", "started_at", "closed_at"]


class PhotoDocumentUploadSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=PhotoDocument.Kind.choices)
    image = serializers.ImageField()


class ExpoPushTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpoPushToken
        fields = ["id", "token"]
