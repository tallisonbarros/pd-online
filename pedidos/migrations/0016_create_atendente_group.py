from django.db import migrations


ATENDENTE_GROUP_NAME = "Atendente"


def create_atendente_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=ATENDENTE_GROUP_NAME)


def remove_atendente_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=ATENDENTE_GROUP_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0015_pedido_public_token"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_atendente_group, remove_atendente_group),
    ]
