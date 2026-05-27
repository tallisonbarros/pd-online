from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0044_create_diretor_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="itempedido",
            name="classificacao_saida",
            field=models.CharField(
                choices=[
                    ("vendida", "Vendida"),
                    ("cortesia", "Cortesia"),
                    ("promocao", "Promoção"),
                ],
                default="vendida",
                max_length=20,
            ),
        ),
    ]
