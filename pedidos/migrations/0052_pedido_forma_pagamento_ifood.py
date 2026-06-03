from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0051_pedido_frete_gratis"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pedido",
            name="forma_pagamento",
            field=models.CharField(
                choices=[
                    ("pix", "Online Pix"),
                    ("dinheiro", "Dinheiro"),
                    ("cartao_entrega", "Cartao na entrega"),
                    ("ifood", "Pago no iFood"),
                ],
                max_length=20,
            ),
        ),
    ]
