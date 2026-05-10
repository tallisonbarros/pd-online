from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pedidos", "0008_configuracaoentrega_google_maps_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracaoentrega",
            name="whatsapp_numero",
            field=models.CharField(blank=True, max_length=24),
        ),
        migrations.AlterField(
            model_name="pedido",
            name="status",
            field=models.CharField(
                choices=[
                    ("aguardando_aprovacao", "Aguardando aprovacao"),
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
