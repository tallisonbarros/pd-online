from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Prato",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=120)),
                ("descricao", models.CharField(blank=True, max_length=255)),
                ("imagem", models.ImageField(blank=True, null=True, upload_to="pratos/")),
                ("preco", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ("ativo", models.BooleanField(default=True)),
                (
                    "dias_disponiveis",
                    models.CharField(
                        blank=True,
                        help_text="Ex.: seg,ter,qua ou deixe vazio para todos os dias.",
                        max_length=120,
                    ),
                ),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["nome"]},
        ),
        migrations.CreateModel(
            name="Pedido",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("numero", models.PositiveIntegerField(blank=True, null=True, unique=True)),
                ("nome_cliente", models.CharField(max_length=120)),
                ("telefone", models.CharField(max_length=30)),
                ("endereco", models.CharField(max_length=255)),
                ("complemento", models.CharField(blank=True, max_length=255)),
                (
                    "forma_pagamento",
                    models.CharField(
                        choices=[("pix", "Pix"), ("dinheiro", "Dinheiro"), ("cartao_entrega", "Cartao na entrega")],
                        max_length=20,
                    ),
                ),
                ("observacao_geral", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("novo", "Novo"),
                            ("em_preparo", "Em preparo"),
                            ("saiu_entrega", "Saiu para entrega"),
                            ("finalizado", "Finalizado"),
                            ("cancelado", "Cancelado"),
                        ],
                        default="novo",
                        max_length=20,
                    ),
                ),
                ("total", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-criado_em"]},
        ),
        migrations.CreateModel(
            name="ItemPedido",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome_prato_snapshot", models.CharField(max_length=120)),
                ("preco_snapshot", models.DecimalField(decimal_places=2, max_digits=8)),
                ("quantidade", models.PositiveIntegerField(default=1)),
                ("observacao", models.CharField(blank=True, max_length=255)),
                ("subtotal", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                (
                    "pedido",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="itens", to="pedidos.pedido"),
                ),
                (
                    "prato",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="itens_pedido",
                        to="pedidos.prato",
                    ),
                ),
            ],
            options={"verbose_name": "Item do pedido", "verbose_name_plural": "Itens do pedido"},
        ),
    ]
