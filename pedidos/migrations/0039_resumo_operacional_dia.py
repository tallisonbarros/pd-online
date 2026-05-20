from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0038_canais_e_precos_por_canal"),
    ]

    operations = [
        migrations.CreateModel(
            name="ResumoOperacionalDia",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data", models.DateField(unique=True)),
                ("marmitas_produzidas", models.PositiveIntegerField(default=0)),
                ("observacao", models.TextField(blank=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Resumo operacional do dia",
                "verbose_name_plural": "Resumos operacionais do dia",
                "ordering": ["-data"],
            },
        ),
    ]
