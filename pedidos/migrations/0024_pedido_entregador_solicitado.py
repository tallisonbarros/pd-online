from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0023_pedido_aguardando_entregador_producao_inicio"),
    ]

    operations = [
        migrations.AddField(
            model_name="pedido",
            name="entregador_solicitado",
            field=models.BooleanField(default=False),
        ),
    ]
