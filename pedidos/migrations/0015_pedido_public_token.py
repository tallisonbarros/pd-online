import secrets

from django.db import migrations, models


def fill_public_tokens(apps, schema_editor):
    Pedido = apps.get_model("pedidos", "Pedido")
    used_tokens = set(
        Pedido.objects.exclude(public_token__isnull=True)
        .exclude(public_token="")
        .values_list("public_token", flat=True)
    )
    for pedido in Pedido.objects.filter(public_token__isnull=True):
        token = secrets.token_urlsafe(24)
        while token in used_tokens:
            token = secrets.token_urlsafe(24)
        used_tokens.add(token)
        pedido.public_token = token
        pedido.save(update_fields=["public_token"])


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0014_adicional_itempedido_adicional"),
    ]

    operations = [
        migrations.AddField(
            model_name="pedido",
            name="public_token",
            field=models.CharField(blank=True, db_index=True, editable=False, max_length=64, null=True),
        ),
        migrations.RunPython(fill_public_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="pedido",
            name="public_token",
            field=models.CharField(blank=True, db_index=True, editable=False, max_length=64, unique=True),
        ),
    ]
