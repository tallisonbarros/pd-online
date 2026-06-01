from django.db import migrations, models
import django.db.models.deletion


def preencher_bancos_padrao(apps, schema_editor):
    BancoConta = apps.get_model("pedidos", "BancoConta")
    ConfiguracaoEntrega = apps.get_model("pedidos", "ConfiguracaoEntrega")
    banco = BancoConta.objects.filter(ativo=True).order_by("ordem", "id").first()
    if not banco:
        banco = BancoConta.objects.create(nome="Banco 01", codigo="banco-01", ordem=10, ativo=True)
    ConfiguracaoEntrega.objects.update(banco_pix=banco, banco_cartao=banco)


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0049_contabil_conta"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracaoentrega",
            name="banco_cartao",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="configuracoes_cartao",
                to="pedidos.bancoconta",
            ),
        ),
        migrations.AddField(
            model_name="configuracaoentrega",
            name="banco_pix",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="configuracoes_pix",
                to="pedidos.bancoconta",
            ),
        ),
        migrations.RunPython(preencher_bancos_padrao, migrations.RunPython.noop),
    ]
