import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from pedidos.models import ItemPedido, Pedido


BLOCK_SEPARATOR_RE = re.compile(r"\n=+\n?", re.MULTILINE)
ITEM_RE = re.compile(r"^-\s*(?P<qty>\d+)x\s+(?P<name>.+?)(?:\s+\|\s+(?P<meta>.+))?$")


def parse_decimal(value):
    if value is None:
        return None
    cleaned = str(value).strip()
    cleaned = cleaned.replace("R$", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_datetime(value):
    return timezone.make_aware(datetime.strptime(value.strip(), "%m/%d/%Y %H:%M:%S"))


def split_address(raw_address):
    parts = [part.strip() for part in raw_address.split(",")]
    rua = parts[0] if parts else ""
    numero = parts[1] if len(parts) > 1 else ""
    bairro = parts[2] if len(parts) > 2 else ""
    complemento = ", ".join(parts[3:]) if len(parts) > 3 else ""
    return rua, numero, bairro, complemento


def map_payment(value):
    normalized = (value or "").strip().lower()
    if normalized == "pix":
        return Pedido.FormaPagamento.PIX
    if normalized == "dinheiro":
        return Pedido.FormaPagamento.DINHEIRO
    if normalized in {"credito", "debito", "boleto"}:
        return Pedido.FormaPagamento.CARTAO
    return Pedido.FormaPagamento.PIX


def map_status(value):
    normalized = (value or "").strip().lower()
    if normalized == "entregue":
        return Pedido.Status.FINALIZADO
    if normalized == "cancelado":
        return Pedido.Status.CANCELADO
    if normalized == "em_producao":
        return Pedido.Status.EM_PREPARO
    if normalized in {"aguardando_entregador", "saiu_para_entrega"}:
        return Pedido.Status.SAIU_ENTREGA
    return Pedido.Status.NOVO


def parse_blocks(text):
    return [block.strip() for block in BLOCK_SEPARATOR_RE.split(text) if block.strip()]


def parse_order_block(block):
    lines = [line.rstrip() for line in block.splitlines() if line.strip()]
    data = {
        "numero": None,
        "legacy_id": "",
        "titulo": "",
        "criado_em": None,
        "status": Pedido.Status.NOVO,
        "pagamento": Pedido.FormaPagamento.PIX,
        "endereco": "",
        "total": Decimal("0.00"),
        "timeline": [],
        "itens": [],
    }

    mode = None
    for raw_line in lines:
        line = raw_line.strip()

        if line.startswith("Pedido #"):
            data["numero"] = int(line.split("#", 1)[1].strip())
            mode = None
            continue
        if line.startswith("ID:"):
            data["legacy_id"] = line.split(":", 1)[1].strip()
            mode = None
            continue
        if line.startswith("Titulo:"):
            data["titulo"] = line.split(":", 1)[1].strip()
            mode = None
            continue
        if line.startswith("Criado em:"):
            data["criado_em"] = parse_datetime(line.split(":", 1)[1].strip())
            mode = None
            continue
        if line.startswith("Status atual:"):
            data["status"] = map_status(line.split(":", 1)[1].strip())
            mode = None
            continue
        if line.startswith("Pagamento:"):
            data["pagamento"] = map_payment(line.split(":", 1)[1].strip())
            mode = None
            continue
        if line.startswith("Endereco:"):
            data["endereco"] = line.split(":", 1)[1].strip()
            mode = None
            continue
        if line.startswith("Total:"):
            data["total"] = parse_decimal(line.split(":", 1)[1].strip()) or Decimal("0.00")
            mode = None
            continue
        if line == "Timeline:":
            mode = "timeline"
            continue
        if line == "Itens:":
            mode = "itens"
            continue

        if mode == "timeline" and line.startswith("- "):
            status_name, _, timestamp = line[2:].partition(":")
            if timestamp.strip():
                data["timeline"].append((status_name.strip(), parse_datetime(timestamp.strip())))
            continue

        if mode == "itens" and line.startswith("- "):
            match = ITEM_RE.match(line)
            if not match:
                continue
            metadata = {}
            for chunk in (match.group("meta") or "").split("|"):
                chunk = chunk.strip()
                if ": " not in chunk:
                    continue
                key, value = chunk.split(": ", 1)
                metadata[key.strip().lower()] = value.strip()
            data["itens"].append(
                {
                    "quantidade": int(match.group("qty")),
                    "nome": match.group("name").strip(),
                    "unitario": parse_decimal(metadata.get("unit")),
                    "subtotal": parse_decimal(metadata.get("total")),
                    "tipo": metadata.get("tipo", ""),
                }
            )

    if data["numero"] is None or data["criado_em"] is None:
        raise ValueError("Bloco sem numero ou criado_em.")

    return data


def resolve_item_prices(items, order_total):
    if len(items) == 1 and items[0]["unitario"] is None:
        qty = max(1, items[0]["quantidade"])
        items[0]["unitario"] = (order_total / qty).quantize(Decimal("0.01"))

    for item in items:
        if item["unitario"] is None:
            if item["subtotal"] is not None and item["quantidade"] > 0:
                item["unitario"] = (item["subtotal"] / item["quantidade"]).quantize(Decimal("0.01"))
            else:
                item["unitario"] = Decimal("0.00")


class Command(BaseCommand):
    help = "Importa pedidos legados exportados em texto para o historico do site."

    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        source_path = Path(options["file_path"])
        if not source_path.exists():
            raise CommandError(f"Arquivo nao encontrado: {source_path}")

        text = source_path.read_text(encoding="utf-8", errors="replace")
        blocks = parse_blocks(text)

        imported = 0
        skipped = 0
        errors = 0

        for block in blocks:
            try:
                parsed = parse_order_block(block)
            except Exception as exc:
                errors += 1
                self.stderr.write(f"Erro ao ler bloco: {exc}")
                continue

            if Pedido.objects.filter(numero=parsed["numero"]).exists():
                skipped += 1
                continue

            resolve_item_prices(parsed["itens"], parsed["total"])
            rua, numero_endereco, bairro, complemento = split_address(parsed["endereco"])
            timeline_lines = [
                f"{status_key}: {timezone.localtime(timestamp).strftime('%d/%m/%Y %H:%M:%S')}"
                for status_key, timestamp in parsed["timeline"]
            ]
            observacao = (
                "[IMPORTADO DO SISTEMA ANTIGO]\n"
                f"ID antigo: {parsed['legacy_id']}\n"
                f"Titulo antigo: {parsed['titulo']}\n"
                "Timeline antiga:\n- " + "\n- ".join(timeline_lines)
            )

            if options["dry_run"]:
                imported += 1
                continue

            with transaction.atomic():
                pedido = Pedido.objects.create(
                    numero=parsed["numero"],
                    nome_cliente=parsed["titulo"][:120] or f"Pedido legado {parsed['numero']}",
                    telefone="",
                    rua=rua[:180],
                    numero_endereco=numero_endereco[:20],
                    bairro=bairro[:120],
                    cidade="Rio Verde",
                    estado="GO",
                    endereco_formatado=parsed["endereco"][:255],
                    endereco=parsed["endereco"][:255],
                    complemento=complemento[:255],
                    forma_pagamento=parsed["pagamento"],
                    enviar_talheres=False,
                    observacao_geral=observacao[:5000],
                    status=parsed["status"],
                    total=parsed["total"],
                    valor_frete=Decimal("0.00"),
                    distancia_km=Decimal("0.00"),
                )
                Pedido.objects.filter(pk=pedido.pk).update(criado_em=parsed["criado_em"])

                for item in parsed["itens"]:
                    ItemPedido.objects.create(
                        pedido=pedido,
                        prato=None,
                        nome_prato_snapshot=item["nome"][:120],
                        preco_snapshot=item["unitario"] or Decimal("0.00"),
                        quantidade=item["quantidade"],
                        observacao=f"Tipo legado: {item['tipo']}"[:255] if item["tipo"] else "",
                    )

            imported += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Importacao concluida. Importados: {imported} | Pulados: {skipped} | Erros: {errors}"
            )
        )
