import uuid

from django.db import migrations, models
from django.db.models import Q


def assign_existing_groups(apps, schema_editor):
    PhotoDocument = apps.get_model("inventory", "PhotoDocument")
    for document in PhotoDocument.objects.all().iterator():
        document.group_id = uuid.uuid4()
        document.save(update_fields=["group_id"])


class Migration(migrations.Migration):
    dependencies = [("inventory", "0008_photo_document")]

    operations = [
        migrations.AddField(model_name="photodocument", name="extracted_at",
                            field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="photodocument", name="extraction_error",
                            field=models.CharField(blank=True, max_length=200)),
        migrations.AddField(model_name="photodocument", name="extraction_items",
                            field=models.JSONField(default=list)),
        migrations.AddField(model_name="photodocument", name="extraction_provider",
                            field=models.CharField(blank=True, max_length=40)),
        migrations.AddField(model_name="photodocument", name="extraction_status",
                            field=models.CharField(default="PENDIENTE", max_length=12)),
        migrations.AddField(model_name="photodocument", name="group_id",
                            field=models.UUIDField(db_index=True, null=True)),
        migrations.RunPython(assign_existing_groups, migrations.RunPython.noop),
        migrations.AlterField(model_name="photodocument", name="group_id",
                              field=models.UUIDField(db_index=True, default=uuid.uuid4)),
        migrations.AddConstraint(model_name="photodocument",
                                 constraint=models.UniqueConstraint(
                                     fields=("sha256",), condition=Q(movement__isnull=False),
                                     name="unique_confirmed_photo_hash")),
    ]
