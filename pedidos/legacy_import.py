import csv
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import StringIO

from django.db import transaction
from django.utils import timezone

from .models import Cupom, ItemPedido, Pedido


EXPECTED_FIELDS = {
    "legacy_id",
    "legacy_order_number",
    "customer_name",
    "created_at",
    "delivered_at",
    "status",
    "fulfillment_type",
    "payment_method",
    "total_charged",
    "items_subtotal",
    "delivery_fee",
    "coupon_code",
    "coupon_discount_applied",
    "motoboy_requested",
    "delivery_street",
    "delivery_number",
    "delivery_neighborhood",
    "delivery_complement",
    "delivery_address_formatted",
    "item_count",
    "items_json",
    "status_timeline_json",
    "kitchen_icon",
    "notes",
}


@dataclass
class LegacyImportResult:
    imported: int = 0
    skipped: int = 0
    errors: int = 0


def safe_text(value):
    return str(value or "").strip()


def money_decimal(value):
    try:
        return Decimal(safe_text(value).replace(",", ".") or "0").quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def parse_legacy_datetime(value):
    value = safe_text(value)
    if not value:
        return None
    parsed = None
    for date_format in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            parsed = datetime.strptime(value, date_format)
            break
        except ValueError:
            continue
    if parsed is None:
        raise ValueError(f"Data invalida: {value}")
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def map_legacy_status(value):
    normalized = safe_text(value).lower()
    if normalized in {"entregue", "finalizado"}:
        return Pedido.Status.FINALIZADO
    if normalized == "cancelado":
        return Pedido.Status.CANCELADO
    if normalized == "em_producao":
        return Pedido.Status.EM_PREPARO
    if normalized == "aguardando_entregador":
        return Pedido.Status.AGUARDANDO_ENTREGADOR
    if normalized == "saiu_para_entrega":
        return Pedido.Status.SAIU_ENTREGA
    return Pedido.Status.NOVO


def map_legacy_payment(value):
    normalized = safe_text(value).lower()
    if normalized == "dinheiro":
        return Pedido.FormaPagamento.DINHEIRO
    if normalized in {"credito", "debito", "cartao", "cartao_entrega"}:
        return Pedido.FormaPagamento.CARTAO
    return Pedido.FormaPagamento.PIX


def parse_clean_legacy_orders(content):
    reader = csv.DictReader(StringIO(content), delimiter=";", quotechar='"')
    fieldnames = set(reader.fieldnames or [])
    missing = sorted(EXPECTED_FIELDS - fieldnames)
    if missing:
        raise ValueError(f"CSV limpo sem colunas obrigatorias: {', '.join(missing)}")

    rows = []
    for line_number, row in enumerate(reader, start=2):
        try:
            items = json.loads(row["items_json"])
            timeline = json.loads(row["status_timeline_json"])
        except json.JSONDecodeError as exc:
            raise ValueError(f"Linha {line_number}: JSON invalido ({exc}).") from exc

        if not safe_text(row["legacy_order_number"]).isdigit():
            raise ValueError(f"Linha {line_number}: numero legado invalido.")

        rows.append(
            {
                "line_number": line_number,
                "legacy_id": safe_text(row["legacy_id"]),
                "numero": int(row["legacy_order_number"]),
                "nome_cliente": safe_text(row["customer_name"]) or f"Pedido legado {row['legacy_order_number']}",
                "created_at": parse_legacy_datetime(row["created_at"]),
                "delivered_at": parse_legacy_datetime(row["delivered_at"]),
                "status": map_legacy_status(row["status"]),
                "tipo_coleta": (
                    Pedido.TipoColeta.RETIRADA
                    if safe_text(row["fulfillment_type"]).lower() == "retirada"
                    else Pedido.TipoColeta.ENTREGA
                ),
                "payment_method_raw": safe_text(row["payment_method"]).lower(),
                "forma_pagamento": map_legacy_payment(row["payment_method"]),
                "total_charged": money_decimal(row["total_charged"]),
                "items_subtotal": money_decimal(row["items_subtotal"]),
                "delivery_fee": money_decimal(row["delivery_fee"]),
                "coupon_code": safe_text(row["coupon_code"]).upper(),
                "coupon_discount": money_decimal(row["coupon_discount_applied"]),
                "motoboy_requested": safe_text(row["motoboy_requested"]).lower() == "true",
                "rua": safe_text(row["delivery_street"]),
                "numero_endereco": safe_text(row["delivery_number"]),
                "bairro": safe_text(row["delivery_neighborhood"]),
                "complemento": safe_text(row["delivery_complement"]),
                "endereco_formatado": safe_text(row["delivery_address_formatted"]),
                "item_count": int(safe_text(row["item_count"]) or "0"),
                "items": items,
                "timeline": timeline,
                "icone_pedido": safe_text(row["kitchen_icon"]),
                "notes": safe_text(row["notes"]),
            }
        )
    return rows


def infer_delivery_fee(row, default_delivery_fee):
    if row["tipo_coleta"] == Pedido.TipoColeta.RETIRADA:
        return Decimal("0.00"), "retirada"
    if row["delivery_fee"] > Decimal("0.00"):
        return row["delivery_fee"], "original"
    return money_decimal(default_delivery_fee), "inferred_default"


def build_legacy_import_preview(content, default_delivery_fee=Decimal("10.00")):
    rows = parse_clean_legacy_orders(content)
    existing_numbers = set(Pedido.objects.filter(numero__in=[row["numero"] for row in rows]).values_list("numero", flat=True))
    preview_rows = []
    summary = {
        "total_rows": len(rows),
        "will_import": 0,
        "duplicates": 0,
        "delivery_fee_inferred": 0,
        "payment_unknown": 0,
        "coupon_rows": 0,
    }

    for row in rows:
        valor_frete, frete_source = infer_delivery_fee(row, default_delivery_fee)
        total_importado = row["items_subtotal"] + valor_frete - row["coupon_discount"]
        duplicate = row["numero"] in existing_numbers
        summary["duplicates" if duplicate else "will_import"] += 1
        if frete_source == "inferred_default" and valor_frete > Decimal("0.00"):
            summary["delivery_fee_inferred"] += 1
        if row["payment_method_raw"] == "desconhecido":
            summary["payment_unknown"] += 1
        if row["coupon_code"]:
            summary["coupon_rows"] += 1
        preview_rows.append(
            {
                "numero": row["numero"],
                "cliente": row["nome_cliente"],
                "criado_em": row["created_at"],
                "tipo_coleta": row["tipo_coleta"],
                "pagamento": row["payment_method_raw"] or "desconhecido",
                "itens": row["item_count"],
                "subtotal": row["items_subtotal"],
                "frete": valor_frete,
                "frete_source": frete_source,
                "cupom": row["coupon_code"],
                "desconto": row["coupon_discount"],
                "total_original": row["total_charged"],
                "total_importado": total_importado,
                "status": "duplicado" if duplicate else "novo",
            }
        )

    return {"summary": summary, "rows": preview_rows}


def _legacy_observation(row, valor_frete, frete_source):
    timeline_lines = [
        f"{key}: {value}"
        for key, value in row["timeline"].items()
        if safe_text(value)
    ]
    notes = [
        "[IMPORTADO DO SISTEMA ANTIGO]",
        f"ID antigo: {row['legacy_id']}",
        f"Pagamento antigo: {row['payment_method_raw'] or 'desconhecido'}",
        f"Subtotal antigo dos itens: R$ {row['items_subtotal']:.2f}",
        f"Total final antigo: R$ {row['total_charged']:.2f}",
        f"Frete importado: R$ {valor_frete:.2f} ({frete_source})",
        "Total antigo usado para inferir desconto; total importado recalculado com frete no modelo atual.",
    ]
    if row["coupon_code"]:
        notes.append(f"Cupom antigo: {row['coupon_code']} (-R$ {row['coupon_discount']:.2f})")
    if row["notes"]:
        notes.append(f"Notas da limpeza: {row['notes']}")
    if timeline_lines:
        notes.append("Timeline antiga:")
        notes.extend(f"- {line}" for line in timeline_lines)
    return "\n".join(notes)


def import_clean_legacy_orders(content, default_delivery_fee=Decimal("10.00")):
    rows = parse_clean_legacy_orders(content)
    result = LegacyImportResult()

    with transaction.atomic():
        for row in rows:
            if Pedido.objects.filter(numero=row["numero"]).exists():
                result.skipped += 1
                continue

            valor_frete, frete_source = infer_delivery_fee(row, default_delivery_fee)
            total_importado = row["items_subtotal"] + valor_frete - row["coupon_discount"]
            endereco = row["endereco_formatado"]
            if not endereco and row["tipo_coleta"] == Pedido.TipoColeta.RETIRADA:
                endereco = "Retirada no local"
            elif not endereco:
                endereco = ", ".join(part for part in [row["rua"], row["numero_endereco"], row["bairro"]] if part)
            cupom = Cupom.objects.filter(codigo__iexact=row["coupon_code"]).first() if row["coupon_code"] else None

            pedido = Pedido.objects.create(
                numero=row["numero"],
                nome_cliente=row["nome_cliente"][:120],
                telefone="",
                rua=row["rua"][:180],
                numero_endereco=row["numero_endereco"][:20],
                bairro=row["bairro"][:120],
                cidade="Rio Verde",
                estado="GO",
                endereco_formatado=endereco[:255],
                endereco=endereco[:255],
                complemento=row["complemento"][:255],
                tipo_coleta=row["tipo_coleta"],
                icone_pedido=f"img/Icones_pedidos/{row['icone_pedido']}" if row["icone_pedido"] else "",
                forma_pagamento=row["forma_pagamento"],
                enviar_talheres=False,
                canal=Pedido.Canal.BALCAO,
                observacao_geral=_legacy_observation(row, valor_frete, frete_source)[:5000],
                status=row["status"],
                valor_frete=valor_frete,
                total_sem_desconto=row["items_subtotal"] + valor_frete,
                cupom=cupom,
                cupom_codigo=row["coupon_code"],
                cupom_desconto=row["coupon_discount"],
                total=total_importado,
                distancia_km=Decimal("0.00"),
                entregador_solicitado=row["motoboy_requested"],
            )

            update_fields = {"criado_em"}
            update_values = {"criado_em": row["created_at"]}
            producao_inicio = row["timeline"].get("em_producao")
            if producao_inicio:
                update_fields.add("producao_iniciada_em")
                update_values["producao_iniciada_em"] = parse_legacy_datetime(producao_inicio)
            Pedido.objects.filter(pk=pedido.pk).update(**update_values)

            for item in row["items"]:
                unit_price = money_decimal(item.get("unit_price"))
                quantity = max(int(item.get("quantity") or 1), 1)
                item_type = safe_text(item.get("type"))
                observation_parts = []
                if item_type:
                    observation_parts.append(f"Tipo legado: {item_type}")
                if safe_text(item.get("notes")):
                    observation_parts.append(safe_text(item.get("notes")))
                ItemPedido.objects.create(
                    pedido=pedido,
                    prato=None,
                    bebida=None,
                    adicional=None,
                    nome_prato_snapshot=safe_text(item.get("name"))[:120],
                    preco_snapshot=unit_price,
                    quantidade=quantity,
                    observacao=" | ".join(observation_parts)[:255],
                )

            result.imported += 1

    return result
