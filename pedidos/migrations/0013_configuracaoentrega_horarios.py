from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0012_alter_pedido_forma_pagamento"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracaoentrega",
            name="horario_abertura",
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="configuracaoentrega",
            name="horario_fechamento",
            field=models.TimeField(blank=True, null=True),
        ),
    ]
