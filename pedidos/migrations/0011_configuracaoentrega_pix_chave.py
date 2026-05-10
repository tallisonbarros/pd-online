from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pedidos", "0010_bebida_itempedido_bebida"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracaoentrega",
            name="pix_chave",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
