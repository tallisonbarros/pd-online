from decimal import Decimal
from pathlib import PurePosixPath


def _decimal_payload(value, places="0.01"):
    if value is None:
        return None
    return str(Decimal(value).quantize(Decimal(places)))


def serialize_item_pedido_api(item):
    return {
        "id": item.id,
        "prato_id": item.prato_id,
        "bebida_id": item.bebida_id,
        "adicional_id": item.adicional_id,
        "nome_prato_snapshot": item.nome_prato_snapshot,
        "variacao_nome_snapshot": item.variacao_nome_snapshot,
        "preco_snapshot": _decimal_payload(item.preco_snapshot),
        "quantidade": item.quantidade,
        "observacao": item.observacao,
        "subtotal": _decimal_payload(item.subtotal),
    }


def serialize_cupom_pedido_api(cupom):
    if not cupom:
        return None
    return {
        "id": cupom.id,
        "codigo": cupom.codigo,
        "descricao": cupom.descricao,
        "tipo_desconto": cupom.tipo_desconto,
        "valor": _decimal_payload(cupom.valor),
        "valor_minimo_pedido": _decimal_payload(cupom.valor_minimo_pedido),
        "ativo": cupom.ativo,
    }


def _icone_pedido_numero(pedido):
    icon_path = pedido.icone_pedido or pedido.icon_path_for_number(pedido.numero or pedido.pk or 1)
    stem = PurePosixPath(str(icon_path).replace("\\", "/")).stem
    try:
        return int(stem)
    except (TypeError, ValueError):
        return None


def serialize_pedido_api(pedido):
    return {
        "id": pedido.id,
        "numero": pedido.numero,
        "nome_cliente": pedido.nome_cliente,
        "telefone": pedido.telefone,
        "cliente_id": pedido.cliente_id,
        "rua": pedido.rua,
        "numero_endereco": pedido.numero_endereco,
        "bairro": pedido.bairro,
        "cidade": pedido.cidade,
        "estado": pedido.estado,
        "endereco_formatado": pedido.endereco_formatado,
        "latitude": _decimal_payload(pedido.latitude, "0.0000001"),
        "longitude": _decimal_payload(pedido.longitude, "0.0000001"),
        "endereco": pedido.endereco,
        "complemento": pedido.complemento,
        "lote_quadra": pedido.lote_quadra,
        "ponto_referencia": pedido.ponto_referencia,
        "tipo_coleta": pedido.tipo_coleta,
        "tipo_coleta_label": pedido.get_tipo_coleta_display(),
        "icone_pedido": pedido.icone_pedido,
        "icone_pedido_numero": _icone_pedido_numero(pedido),
        "forma_pagamento": pedido.forma_pagamento,
        "forma_pagamento_label": pedido.get_forma_pagamento_display(),
        "enviar_talheres": pedido.enviar_talheres,
        "observacao_geral": pedido.observacao_geral,
        "status": pedido.status,
        "status_label": pedido.get_status_display(),
        "distancia_km": _decimal_payload(pedido.distancia_km),
        "valor_frete": _decimal_payload(pedido.valor_frete),
        "total_sem_desconto": _decimal_payload(pedido.total_sem_desconto),
        "promocao_descricao": pedido.promocao_descricao,
        "promocao_desconto": _decimal_payload(pedido.promocao_desconto),
        "cupom_id": pedido.cupom_id,
        "cupom_codigo": pedido.cupom_codigo,
        "cupom_desconto": _decimal_payload(pedido.cupom_desconto),
        "total": _decimal_payload(pedido.total),
        "public_token": pedido.public_token,
        "criado_em": pedido.criado_em,
        "atualizado_em": pedido.atualizado_em,
        "producao_iniciada_em": pedido.producao_iniciada_em,
        "entregador_solicitado": pedido.entregador_solicitado,
        "status_label_contextual": pedido.status_label_contextual,
        "has_coordinates": pedido.has_coordinates,
        "google_maps_route_url": pedido.google_maps_route_url,
        "icone_pedido_url": pedido.icone_pedido_url,
        "is_retirada": pedido.is_retirada,
        "stage_labels": pedido.stage_labels,
        "cupom": serialize_cupom_pedido_api(pedido.cupom),
        "itens": [serialize_item_pedido_api(item) for item in pedido.itens.all()],
    }


def serialize_pedido_summary_api(pedido):
    return {
        "id": pedido.id,
        "numero": pedido.numero,
        "nome_cliente": pedido.nome_cliente,
        "telefone": pedido.telefone,
        "tipo_coleta": pedido.tipo_coleta,
        "forma_pagamento": pedido.forma_pagamento,
        "status": pedido.status,
        "status_label": pedido.get_status_display(),
        "status_label_contextual": pedido.status_label_contextual,
        "total": _decimal_payload(pedido.total),
        "public_token": pedido.public_token,
        "criado_em": pedido.criado_em,
        "atualizado_em": pedido.atualizado_em,
    }
