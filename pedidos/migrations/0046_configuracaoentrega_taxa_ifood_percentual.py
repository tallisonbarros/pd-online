from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0045_itempedido_classificacao_saida"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracaoentrega",
            name="taxa_ifood_percentual",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=5),
        ),
    ]
