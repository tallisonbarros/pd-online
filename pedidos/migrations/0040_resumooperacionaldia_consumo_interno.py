from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0039_resumo_operacional_dia"),
    ]

    operations = [
        migrations.AddField(
            model_name="resumooperacionaldia",
            name="consumo_interno",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
