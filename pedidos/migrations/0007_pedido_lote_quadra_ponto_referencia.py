from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0006_configuracaoentrega_alter_faixafrete_tipo"),
    ]

    operations = [
        migrations.AddField(
            model_name="pedido",
            name="lote_quadra",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="pedido",
            name="ponto_referencia",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
