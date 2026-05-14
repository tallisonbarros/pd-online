import re

from django.db import migrations, models
import django.db.models.deletion


def normalize_phone(value):
    digits = re.sub(r"\D+", "", str(value or ""))
    if len(digits) > 11 and digits.startswith("55"):
        digits = digits[2:]
    return digits


def sync_existing_customers(apps, schema_editor):
    Cliente = apps.get_model("pedidos", "Cliente")
    EnderecoCliente = apps.get_model("pedidos", "EnderecoCliente")
    Pedido = apps.get_model("pedidos", "Pedido")

    for pedido in Pedido.objects.exclude(telefone="").exclude(status="rascunho").order_by("criado_em", "id"):
        telefone_normalizado = normalize_phone(pedido.telefone)
        if not telefone_normalizado:
            continue
        cliente, created = Cliente.objects.get_or_create(
            telefone_normalizado=telefone_normalizado,
            defaults={
                "telefone": pedido.telefone,
                "nome": pedido.nome_cliente or "Cliente",
                "primeiro_pedido_em": pedido.criado_em,
                "ultimo_pedido_em": pedido.criado_em,
            },
        )
        update_fields = []
        if pedido.criado_em and (not cliente.primeiro_pedido_em or pedido.criado_em < cliente.primeiro_pedido_em):
            cliente.primeiro_pedido_em = pedido.criado_em
            update_fields.append("primeiro_pedido_em")
        if pedido.criado_em and (not cliente.ultimo_pedido_em or pedido.criado_em > cliente.ultimo_pedido_em):
            cliente.ultimo_pedido_em = pedido.criado_em
            update_fields.append("ultimo_pedido_em")
        if not created and not cliente.nome_editado_manualmente and pedido.nome_cliente and cliente.nome == "Cliente":
            cliente.nome = pedido.nome_cliente
            update_fields.append("nome")
        if update_fields:
            cliente.save(update_fields=list(set(update_fields)))

        pedido.cliente_id = cliente.id
        pedido.save(update_fields=["cliente"])

        if pedido.endereco:
            endereco, _created = EnderecoCliente.objects.get_or_create(
                cliente=cliente,
                endereco=pedido.endereco,
                complemento=pedido.complemento or "",
                lote_quadra=pedido.lote_quadra or "",
                ponto_referencia=pedido.ponto_referencia or "",
                defaults={
                    "endereco_formatado": pedido.endereco_formatado or "",
                    "rua": pedido.rua or "",
                    "numero_endereco": pedido.numero_endereco or "",
                    "bairro": pedido.bairro or "",
                    "cidade": pedido.cidade or "Rio Verde",
                    "estado": pedido.estado or "GO",
                    "latitude": pedido.latitude,
                    "longitude": pedido.longitude,
                    "primeiro_uso_em": pedido.criado_em,
                    "ultimo_uso_em": pedido.criado_em,
                    "ultimo_pedido_id": pedido.id,
                },
            )
            if pedido.criado_em and (not endereco.ultimo_uso_em or pedido.criado_em > endereco.ultimo_uso_em):
                endereco.ultimo_uso_em = pedido.criado_em
                endereco.ultimo_pedido_id = pedido.id
                endereco.save(update_fields=["ultimo_uso_em", "ultimo_pedido"])


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0027_pedido_status_rascunho"),
    ]

    operations = [
        migrations.CreateModel(
            name="Cliente",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("telefone_normalizado", models.CharField(max_length=20, unique=True)),
                ("telefone", models.CharField(max_length=30)),
                ("nome", models.CharField(max_length=120)),
                ("nome_editado_manualmente", models.BooleanField(default=False)),
                ("primeiro_pedido_em", models.DateTimeField(blank=True, null=True)),
                ("ultimo_pedido_em", models.DateTimeField(blank=True, null=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Cliente",
                "verbose_name_plural": "Clientes",
                "ordering": ["-ultimo_pedido_em", "nome"],
            },
        ),
        migrations.AddField(
            model_name="pedido",
            name="cliente",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pedidos", to="pedidos.cliente"),
        ),
        migrations.CreateModel(
            name="EnderecoCliente",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("endereco", models.CharField(max_length=255)),
                ("endereco_formatado", models.CharField(blank=True, max_length=255)),
                ("rua", models.CharField(blank=True, max_length=180)),
                ("numero_endereco", models.CharField(blank=True, max_length=20)),
                ("bairro", models.CharField(blank=True, max_length=120)),
                ("cidade", models.CharField(blank=True, default="Rio Verde", max_length=120)),
                ("estado", models.CharField(blank=True, default="GO", max_length=60)),
                ("complemento", models.CharField(blank=True, max_length=255)),
                ("lote_quadra", models.CharField(blank=True, max_length=120)),
                ("ponto_referencia", models.CharField(blank=True, max_length=255)),
                ("latitude", models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True)),
                ("longitude", models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True)),
                ("primeiro_uso_em", models.DateTimeField(blank=True, null=True)),
                ("ultimo_uso_em", models.DateTimeField(blank=True, null=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("cliente", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="enderecos", to="pedidos.cliente")),
                ("ultimo_pedido", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="pedidos.pedido")),
            ],
            options={
                "verbose_name": "Endereço do cliente",
                "verbose_name_plural": "Endereços do cliente",
                "ordering": ["-ultimo_uso_em", "endereco"],
            },
        ),
        migrations.AddConstraint(
            model_name="enderecocliente",
            constraint=models.UniqueConstraint(fields=("cliente", "endereco", "complemento", "lote_quadra", "ponto_referencia"), name="unique_cliente_endereco_usado"),
        ),
        migrations.RunPython(sync_existing_customers, migrations.RunPython.noop),
    ]
