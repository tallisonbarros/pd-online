from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0028_clientes"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClienteTokenConflito",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tokens", models.JSONField(blank=True, default=list)),
                ("status", models.CharField(choices=[("aberto", "Aberto"), ("resolvido", "Resolvido")], default="aberto", max_length=16)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("pedido", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="conflitos_cliente", to="pedidos.pedido")),
                ("clientes", models.ManyToManyField(related_name="conflitos_token", to="pedidos.cliente")),
            ],
            options={
                "verbose_name": "Conflito de cliente por token",
                "verbose_name_plural": "Conflitos de clientes por token",
                "ordering": ["-criado_em"],
            },
        ),
    ]
