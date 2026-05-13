from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0019_prato_variacoes"),
    ]

    operations = [
        migrations.AddField(
            model_name="itempedido",
            name="variacao_nome_snapshot",
            field=models.CharField(blank=True, max_length=120),
        ),
    ]
