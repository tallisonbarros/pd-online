from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0026_pedido_icone_pedido"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pedido",
            name="status",
            field=models.CharField(
                choices=[
                    ("rascunho", "Rascunho"),
                    ("aguardando_aprovacao", "Aguardando aprovação"),
                    ("novo", "Novo"),
                    ("em_preparo", "Em preparo"),
                    ("aguardando_entregador", "Aguardando entregador"),
                    ("saiu_entrega", "Saiu para entrega"),
                    ("finalizado", "Finalizado"),
                    ("cancelado", "Cancelado"),
                ],
                default="novo",
                max_length=24,
            ),
        ),
    ]
