from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0022_create_gerente_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="pedido",
            name="producao_iniciada_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="pedido",
            name="status",
            field=models.CharField(
                choices=[
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
