from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0030_pedido_api_key"),
    ]

    operations = [
        migrations.CreateModel(
            name="PedidoListaImpressao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("numero", models.PositiveIntegerField(blank=True, null=True)),
                ("nome_cliente", models.CharField(max_length=120)),
                ("public_token", models.CharField(db_index=True, max_length=64)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                (
                    "pedido",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lista_impressao",
                        to="pedidos.pedido",
                    ),
                ),
            ],
            options={
                "verbose_name": "Item da lista de impressao",
                "verbose_name_plural": "Lista de impressao",
                "ordering": ["criado_em", "id"],
            },
        ),
    ]
