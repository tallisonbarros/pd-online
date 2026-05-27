from django.db import migrations


DIRETOR_GROUP_NAME = "Diretor"


def create_diretor_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=DIRETOR_GROUP_NAME)


def remove_diretor_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=DIRETOR_GROUP_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0043_pedido_pagamento_recebido"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_diretor_group, remove_diretor_group),
    ]
