from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0041_resumooperacionaldia_custo_insumos"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pedido",
            name="enviar_talheres",
            field=models.BooleanField(default=False),
        ),
    ]
