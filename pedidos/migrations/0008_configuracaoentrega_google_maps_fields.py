from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pedidos", "0007_pedido_lote_quadra_ponto_referencia"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracaoentrega",
            name="google_maps_api_key",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="configuracaoentrega",
            name="google_maps_language",
            field=models.CharField(blank=True, default="pt-BR", max_length=20),
        ),
        migrations.AddField(
            model_name="configuracaoentrega",
            name="google_maps_region",
            field=models.CharField(blank=True, default="BR", max_length=10),
        ),
    ]
