from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0020_itempedido_variacao_nome_snapshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="pedido",
            name="promocao_descricao",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="pedido",
            name="promocao_desconto",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=8),
        ),
    ]
