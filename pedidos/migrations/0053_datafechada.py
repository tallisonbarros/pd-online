from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0052_pedido_forma_pagamento_ifood"),
    ]

    operations = [
        migrations.CreateModel(
            name="DataFechada",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data", models.DateField(unique=True)),
                ("motivo", models.CharField(blank=True, max_length=120)),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Data fechada",
                "verbose_name_plural": "Datas fechadas",
                "ordering": ["-data"],
            },
        ),
    ]
