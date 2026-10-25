from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("inventory", "0003_userprofile_alias")]

    operations = [
        migrations.CreateModel(
            name="SensorReading",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reading_id", models.UUIDField(unique=True)),
                ("temperature_c", models.DecimalField(decimal_places=2, max_digits=4)),
                ("humidity_percent", models.DecimalField(decimal_places=2, max_digits=5)),
                ("sample_count", models.PositiveSmallIntegerField()),
                ("received_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={"ordering": ["-received_at", "-pk"]},
        ),
        migrations.AddConstraint(model_name="sensorreading", constraint=models.CheckConstraint(condition=Q(temperature_c__gte=0, temperature_c__lte=50), name="dht_temperature_range")),
        migrations.AddConstraint(model_name="sensorreading", constraint=models.CheckConstraint(condition=Q(humidity_percent__gte=20, humidity_percent__lte=90), name="dht_humidity_range")),
        migrations.AddConstraint(model_name="sensorreading", constraint=models.CheckConstraint(condition=Q(sample_count__gte=1, sample_count__lte=4), name="dht_sample_count_range")),
    ]
