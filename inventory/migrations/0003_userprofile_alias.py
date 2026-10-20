from django.db import migrations, models


def set_initial_aliases(apps, schema_editor):
    UserProfile = apps.get_model("inventory", "UserProfile")
    for profile in UserProfile.objects.select_related("user").iterator():
        local_name = profile.user.username.split("@", 1)[0].replace(".", " ").replace("_", " ").strip()
        if local_name.lower() == "dueno":
            alias = "Dueño"
        elif local_name.lower() == "empleado":
            alias = "Empleado"
        else:
            alias = local_name.title()[:40] or "Usuario"
        UserProfile.objects.filter(pk=profile.pk).update(alias=alias)


class Migration(migrations.Migration):
    dependencies = [("inventory", "0002_location_location_code_ci_unique_and_more")]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="alias",
            field=models.CharField(default="Usuario", max_length=40),
        ),
        migrations.RunPython(set_initial_aliases, migrations.RunPython.noop),
    ]
