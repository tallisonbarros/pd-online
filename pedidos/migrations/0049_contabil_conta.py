from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def criar_banco_padrao(apps, schema_editor):
    BancoConta = apps.get_model("pedidos", "BancoConta")
    BancoConta.objects.get_or_create(
        codigo="banco-01",
        defaults={"nome": "Banco 01", "ordem": 10, "ativo": True},
    )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("pedidos", "0048_pedido_terminal_movimentacao_link"),
    ]

    operations = [
        migrations.CreateModel(
            name="BancoConta",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=80)),
                ("codigo", models.CharField(max_length=30, unique=True)),
                ("ativo", models.BooleanField(default=True)),
                ("ordem", models.PositiveSmallIntegerField(default=0)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Banco da conta",
                "verbose_name_plural": "Bancos da conta",
                "ordering": ["ordem", "nome"],
            },
        ),
        migrations.CreateModel(
            name="CategoriaMovimentacaoConta",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=80, unique=True)),
                (
                    "tipo_padrao",
                    models.CharField(
                        choices=[("entrada", "Entrada"), ("saida", "Saida"), ("ambos", "Ambos")],
                        default="ambos",
                        max_length=8,
                    ),
                ),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Categoria de movimentacao de conta",
                "verbose_name_plural": "Categorias de movimentacao de conta",
                "ordering": ["nome"],
            },
        ),
        migrations.CreateModel(
            name="MovimentacaoConta",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data_movimento", models.DateField(db_index=True)),
                ("tipo", models.CharField(choices=[("entrada", "Entrada"), ("saida", "Saida")], max_length=8)),
                ("nome", models.CharField(max_length=120)),
                ("descricao", models.TextField(blank=True)),
                ("valor", models.DecimalField(decimal_places=2, max_digits=10)),
                (
                    "origem",
                    models.CharField(choices=[("manual", "Manual"), ("sistema", "Sistema")], default="manual", max_length=10),
                ),
                ("excluido_em", models.DateTimeField(blank=True, null=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                (
                    "atualizado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="movimentacoes_conta_atualizadas",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "banco",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="movimentacoes",
                        to="pedidos.bancoconta",
                    ),
                ),
                (
                    "categoria",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="movimentacoes",
                        to="pedidos.categoriamovimentacaoconta",
                    ),
                ),
                (
                    "criado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="movimentacoes_conta_criadas",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "excluido_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="movimentacoes_conta_excluidas",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "pedido",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="movimentacao_conta",
                        to="pedidos.pedido",
                    ),
                ),
            ],
            options={
                "verbose_name": "Movimentacao de conta",
                "verbose_name_plural": "Movimentacoes de conta",
                "ordering": ["data_movimento", "criado_em", "id"],
            },
        ),
        migrations.RunPython(criar_banco_padrao, migrations.RunPython.noop),
    ]
