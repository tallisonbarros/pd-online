from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0042_alter_pedido_enviar_talheres_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="pedido",
            name="pagamento_recebido_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="pedido",
            name="status",
            field=models.CharField(
                choices=[
                    ("rascunho", "Rascunho"),
                    ("aguardando_aprovacao", "Aguardando aprovação"),
                    ("novo", "Novo"),
                    ("em_preparo", "Em preparo"),
                    ("pagamento_recebido", "Pagamento recebido"),
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
