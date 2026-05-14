from django.db import migrations


GERENTE_GROUP_NAME = "Gerente"


def create_gerente_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=GERENTE_GROUP_NAME)


def remove_gerente_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=GERENTE_GROUP_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0021_pedido_promocao"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_gerente_group, remove_gerente_group),
    ]
