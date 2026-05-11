from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0013_configuracaoentrega_horarios"),
    ]

    operations = [
        migrations.CreateModel(
            name="Adicional",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=120)),
                ("descricao", models.CharField(blank=True, max_length=255)),
                ("imagem", models.ImageField(blank=True, null=True, upload_to="adicionais/")),
                ("preco", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ("ativo", models.BooleanField(default=True)),
                ("ordem", models.PositiveSmallIntegerField(default=0)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["ordem", "nome"],
            },
        ),
        migrations.AddField(
            model_name="itempedido",
            name="adicional",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="itens_pedido",
                to="pedidos.adicional",
            ),
        ),
    ]
