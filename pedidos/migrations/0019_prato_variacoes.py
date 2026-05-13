from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0018_align_existing_model_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="prato",
            name="variacoes",
            field=models.TextField(
                blank=True,
                help_text="Uma variacao por linha. Ex.: Fraldinha, Frango.",
            ),
        ),
    ]
