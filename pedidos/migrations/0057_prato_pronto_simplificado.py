from django.db import migrations, models


def migrar_configuracao_existente(apps, schema_editor):
    TurnoAtendimento = apps.get_model("pedidos", "TurnoAtendimento")
    TurnoPratoPadrao = apps.get_model("pedidos", "TurnoPratoPadrao")
    DisponibilidadeTurnoItem = apps.get_model("pedidos", "DisponibilidadeTurnoItem")

    turno = TurnoAtendimento.objects.filter(codigo="prato_pronto").first()
    if not turno:
        return

    if not TurnoPratoPadrao.objects.filter(turno=turno).exists():
        itens = (
            DisponibilidadeTurnoItem.objects.filter(
                disponibilidade__turno=turno,
                ativo=True,
            )
            .order_by("-disponibilidade__data", "ordem", "prato_id")
        )
        vistos = set()
        ordem = 10
        for item in itens:
            if item.prato_id in vistos:
                continue
            vistos.add(item.prato_id)
            TurnoPratoPadrao.objects.create(
                turno=turno,
                prato_id=item.prato_id,
                preco=item.preco,
                dias_semana=turno.dias_semana,
                ativo=True,
                ordem=ordem,
            )
            ordem += 10

    turno.modo_cardapio = "fixo"
    turno.preco_padrao = None
    turno.desconto_padrao = 0
    turno.permite_entrega = True
    turno.permite_retirada = True
    turno.horario_limite_entrega = turno.horario_fim
    turno.permite_promocao = False
    turno.permite_cupom = False
    turno.save(
        update_fields=[
            "modo_cardapio",
            "preco_padrao",
            "desconto_padrao",
            "permite_entrega",
            "permite_retirada",
            "horario_limite_entrega",
            "permite_promocao",
            "permite_cupom",
        ]
    )


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0056_pedido_orientacao_turno_snapshot_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="prato",
            name="exclusivo_prato_pronto",
            field=models.BooleanField(
                default=False,
                help_text="Quando marcado, o prato aparece apenas no atendimento Prato Pronto.",
            ),
        ),
        migrations.AddField(
            model_name="turnopratopadrao",
            name="dias_semana",
            field=models.CharField(
                blank=True,
                help_text="Ex.: seg,ter,qua,qui,sex,sab. Vazio segue todos os dias do turno.",
                max_length=40,
            ),
        ),
        migrations.RunPython(migrar_configuracao_existente, migrations.RunPython.noop),
    ]
