from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0017_cupom_pedido_cupom"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="configuracaoentrega",
            options={"verbose_name": "Configuração de entrega", "verbose_name_plural": "Configuracoes de entrega"},
        ),
        migrations.AlterField(
            model_name="faixafrete",
            name="tipo",
            field=models.CharField(choices=[("ate", "Até"), ("acima", "Acima de")], default="ate", max_length=10),
        ),
        migrations.AlterField(
            model_name="pedido",
            name="public_token",
            field=models.CharField(blank=True, editable=False, max_length=64, unique=True),
        ),
        migrations.AlterField(
            model_name="pedido",
            name="status",
            field=models.CharField(
                choices=[
                    ("aguardando_aprovacao", "Aguardando aprovação"),
                    ("novo", "Novo"),
                    ("em_preparo", "Em preparo"),
                    ("saiu_entrega", "Saiu para entrega"),
                    ("finalizado", "Finalizado"),
                    ("cancelado", "Cancelado"),
                ],
                default="novo",
                max_length=20,
            ),
        ),
    ]
