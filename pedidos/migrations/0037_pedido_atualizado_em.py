from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0036_accessevent_page_active"),
    ]

    operations = [
        migrations.AddField(
            model_name="pedido",
            name="atualizado_em",
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
    ]
