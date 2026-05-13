from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0016_create_atendente_group"),
    ]

    operations = [
        migrations.CreateModel(
            name="Cupom",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codigo", models.CharField(max_length=40, unique=True)),
                ("descricao", models.CharField(blank=True, max_length=160)),
                ("ativo", models.BooleanField(default=True)),
                (
                    "tipo_desconto",
                    models.CharField(
                        choices=[("percentual", "Percentual"), ("valor_fixo", "Valor fixo")],
                        default="valor_fixo",
                        max_length=20,
                    ),
                ),
                ("valor", models.DecimalField(decimal_places=2, max_digits=8)),
                ("valor_minimo_pedido", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=8)),
                ("uso_maximo_total", models.PositiveIntegerField(blank=True, null=True)),
                ("data_inicio", models.DateTimeField(blank=True, null=True)),
                ("data_fim", models.DateTimeField(blank=True, null=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-ativo", "codigo"],
            },
        ),
        migrations.AddField(
            model_name="pedido",
            name="cupom",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pedidos", to="pedidos.cupom"),
        ),
        migrations.AddField(
            model_name="pedido",
            name="cupom_codigo",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="pedido",
            name="cupom_desconto",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=8),
        ),
        migrations.AddField(
            model_name="pedido",
            name="total_sem_desconto",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10),
        ),
    ]
