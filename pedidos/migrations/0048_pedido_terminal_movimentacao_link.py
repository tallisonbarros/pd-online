import django.db.models.deletion
from django.db import migrations, models


def preencher_terminal_pedidos(apps, schema_editor):
    Pedido = apps.get_model("pedidos", "Pedido")
    TerminalCaixa = apps.get_model("pedidos", "TerminalCaixa")
    terminal = TerminalCaixa.objects.filter(ativo=True).order_by("ordem", "id").first()
    if terminal:
        Pedido.objects.filter(terminal__isnull=True).update(terminal=terminal)


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0047_contabil_caixa"),
    ]

    operations = [
        migrations.AddField(
            model_name="pedido",
            name="terminal",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="pedidos",
                to="pedidos.terminalcaixa",
            ),
        ),
        migrations.AddField(
            model_name="movimentacaocaixa",
            name="pedido",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="movimentacao_caixa",
                to="pedidos.pedido",
            ),
        ),
        migrations.RunPython(preencher_terminal_pedidos, migrations.RunPython.noop),
    ]
