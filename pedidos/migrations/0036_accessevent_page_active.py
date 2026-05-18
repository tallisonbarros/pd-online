from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0035_ifood_prices"),
    ]

    operations = [
        migrations.AlterField(
            model_name="accessevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("menu_view", "Acesso ao cardapio"),
                    ("cart_view", "Acesso ao carrinho"),
                    ("checkout_view", "Acesso ao caixa"),
                    ("page_active", "Usuario ativo"),
                    ("add_to_cart", "Item adicionado ao carrinho"),
                    ("remove_from_cart", "Item removido do carrinho"),
                    ("go_to_checkout", "Avanco para caixa"),
                    ("checkout_submit", "Envio do caixa"),
                    ("pickup_submit", "Envio de retirada"),
                    ("order_created", "Pedido criado"),
                ],
                db_index=True,
                max_length=32,
            ),
        ),
    ]
