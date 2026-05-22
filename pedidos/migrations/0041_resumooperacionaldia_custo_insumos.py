from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0040_resumooperacionaldia_consumo_interno"),
    ]

    operations = [
        migrations.AddField(
            model_name="resumooperacionaldia",
            name="custo_insumos",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10),
        ),
    ]
