from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0031_pedido_lista_impressao"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccessEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("menu_view", "Acesso ao cardapio"),
                            ("cart_view", "Acesso ao carrinho"),
                            ("checkout_view", "Acesso ao checkout"),
                            ("add_to_cart", "Item adicionado ao carrinho"),
                            ("remove_from_cart", "Item removido do carrinho"),
                            ("go_to_checkout", "Avanco para checkout"),
                            ("checkout_submit", "Envio do checkout"),
                            ("pickup_submit", "Envio de retirada"),
                            ("order_created", "Pedido criado"),
                        ],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                ("path", models.CharField(blank=True, max_length=160)),
                ("session_key", models.CharField(db_index=True, max_length=40)),
                ("item_type", models.CharField(blank=True, max_length=20)),
                ("item_id", models.PositiveIntegerField(blank=True, null=True)),
                ("cart_items_count", models.PositiveIntegerField(default=0)),
                ("cart_total", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "verbose_name": "Evento de acesso",
                "verbose_name_plural": "Eventos de acesso",
                "ordering": ["-created_at", "-id"],
            },
        ),
    ]
