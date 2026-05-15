from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0029_cliente_token_conflito"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PedidoApiKey",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=120)),
                ("prefixo", models.CharField(db_index=True, max_length=12)),
                ("chave_hash", models.CharField(max_length=64, unique=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("ultimo_uso_em", models.DateTimeField(blank=True, null=True)),
                (
                    "criado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="pedido_api_keys",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Chave da API de pedidos",
                "verbose_name_plural": "Chaves da API de pedidos",
                "ordering": ["-criado_em"],
            },
        ),
    ]
