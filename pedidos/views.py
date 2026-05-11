import json
import math
import unicodedata
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from django.contrib.admin.views.decorators import staff_member_required
from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import ExtractHour, TruncDate
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_time
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .forms import AdicionalForm, BebidaForm, PratoForm
from .models import Adicional, Bebida, ConfiguracaoEntrega, FaixaFrete, ItemPedido, Pedido, Prato

WEEKDAYS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
WEEKDAY_LABELS = {
    "seg": "SEGUNDA",
    "ter": "TERCA",
    "qua": "QUARTA",
    "qui": "QUINTA",
    "sex": "SEXTA",
    "sab": "SABADO",
    "dom": "DOMINGO",
}
PHOTON_BASE_URL = "https://photon.komoot.io/api/"
PHOTON_REVERSE_URL = "https://photon.komoot.io/reverse"
OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"
RIO_VERDE_CENTER = {"lat": -17.7923, "lon": -50.9192}
RIO_VERDE_BBOX = "-51.0500,-17.9500,-50.7500,-17.6500"  # minLon,minLat,maxLon,maxLat
OSRM_ROUTE_BASE_URL = "https://router.project-osrm.org/route/v1/driving/"

RIO_VERDE_BAIRROS_OFICIAIS = [
    "Anhanguera", "Área Rural de Rio Verde", "César Bastos", "Céu Azul", "Cidade Empresarial Nova Aliança",
    "Conjunto Maurício Arantes", "Conjunto Morada do Sol", "Conjunto Vila Verde", "Distrito Agroindustrial (DARV)",
    "Eldorado", "Eldorado Prolongamento", "Jardim Adriana", "Jardim América", "Jardim Bela Vista", "Jardim Brasília",
    "Jardim Cruvinel", "Jardim das Margaridas", "Jardim Diniz", "Jardim Eleonora", "Jardim Floresta", "Jardim Goiás",
    "Jardim Marconal", "Jardim Mondale", "Jardim Neves", "Jardim Presidente", "Jardim São Tomaz", "Liberdade",
    "Lindolfina", "Loteamento Gameleira", "Maristela", "Martins", "Medeiros", "Nova Vila Maria", "Odília",
    "Paraguassu", "Parque Bandeirante", "Parque Betel", "Parque das Acácias", "Parque das Laranjeiras",
    "Parque das Paineiras", "Parque Dom Miguel", "Parque dos Buritis", "Parque dos Girassóis", "Parque dos Jatobás",
    "Popular", "Presidente Nasser", "Primavera", "Residencial Água Santa", "Residencial Araguaia",
    "Residencial Arco Iris", "Residencial Atalaia", "Residencial Canaã", "Residencial Dona Iza",
    "Residencial dos Buritis", "Residencial Gameleira", "Residencial Green Park", "Residencial Interlagos",
    "Residencial Jardim Campestre", "Residencial Jardim Helena", "Residencial Maranata",
    "Residencial Nilson Veloso", "Residencial Parque dos Ipês", "Residencial Recanto do Bosque",
    "Residencial Solar dos Ataídes", "Residencial Tocantins", "Residencial Veneza",
    "Residencial Villagio Terra Cota", "Santo Agostinho", "Santo Antônio de Lisboa", "São Felipe", "São João",
    "São Joaquim", "Serra Dourada", "Setor Alvorada", "Setor Central", "Setor Dona Gercina",
    "Setor dos Funcionários", "Setor Industrial", "Setor Morada do Sol", "Setor Oeste", "Setor Pauzanes",
    "Setor Santa Luzia", "Setor Universitário", "Solar Campestre", "Solar Monte Sião", "Vila Amália",
    "Vila André Luiz", "Vila Baylão", "Vila Borges", "Vila Carolina", "Vila Dinara", "Vila Dona Auta",
    "Vila Gomes", "Vila Maria", "Vila Mariana", "Vila Meneses", "Vila Miafiori", "Vila Modelo", "Vila Morais",
    "Vila Mutirão", "Vila Olinda", "Vila Promissão", "Vila Renovação", "Vila Rocha", "Vila Rosalina",
    "Vila Santa Bárbara", "Vila Santa Cruz", "Vila Santo André", "Vila Santo Antônio", "Vila Serpro",
    "Vitória Régia",
]


def _prato_dias_disponiveis(prato):
    if not prato.dias_disponiveis.strip():
        return set(WEEKDAYS)
    return {dia.strip().lower() for dia in prato.dias_disponiveis.split(",") if dia.strip()}


def prato_disponivel_no_dia(prato, weekday_key):
    return weekday_key in _prato_dias_disponiveis(prato)


def prato_disponivel_hoje(prato):
    hoje = WEEKDAYS[timezone.localtime().weekday()]
    return prato_disponivel_no_dia(prato, hoje)


def _resolve_cardapio_pratos(config=None, now=None):
    config = config or ConfiguracaoEntrega.get_solo()
    current = now or timezone.localtime()
    fechamento = getattr(config, "horario_fechamento", None)
    start_offset = 1 if fechamento and current.time() >= fechamento else 0
    active_pratos = list(Prato.objects.filter(ativo=True))

    for offset in range(start_offset, start_offset + 7):
        weekday_index = (current.weekday() + offset) % 7
        weekday_key = WEEKDAYS[weekday_index]
        pratos = [prato for prato in active_pratos if prato_disponivel_no_dia(prato, weekday_key)]
        if pratos:
            is_today = offset == 0
            return {
                "pratos": pratos,
                "weekday_key": weekday_key,
                "is_today": is_today,
                "title_line_1": "PRATO" if is_today else "PRATO DE",
                "title_line_2": "DO DIA" if is_today else WEEKDAY_LABELS[weekday_key],
                "empty_label": "hoje" if is_today else f"para {WEEKDAY_LABELS[weekday_key].lower()}",
            }

    weekday_key = WEEKDAYS[(current.weekday() + start_offset) % 7]
    return {
        "pratos": [],
        "weekday_key": weekday_key,
        "is_today": start_offset == 0,
        "title_line_1": "PRATO" if start_offset == 0 else "PRATO DE",
        "title_line_2": "DO DIA" if start_offset == 0 else WEEKDAY_LABELS[weekday_key],
        "empty_label": "hoje" if start_offset == 0 else f"para {WEEKDAY_LABELS[weekday_key].lower()}",
    }


def serializar_prato(prato):
    return {
        "id": prato.id,
        "nome": prato.nome,
        "descricao": prato.descricao,
        "preco": f"{prato.preco:.2f}" if prato.preco is not None else "",
        "preco_formatado": f"R$ {prato.preco:.2f}".replace(".", ",") if prato.preco is not None else "",
        "imagem": prato.imagem.url if prato.imagem else settings.STATIC_URL + "img/placeholder-prato.svg",
    }


def serializar_bebida(bebida):
    return {
        "id": bebida.id,
        "nome": bebida.nome,
        "descricao": bebida.descricao,
        "preco": f"{bebida.preco:.2f}" if bebida.preco is not None else "",
        "preco_formatado": f"R$ {bebida.preco:.2f}".replace(".", ",") if bebida.preco is not None else "",
        "imagem": bebida.imagem.url if bebida.imagem else settings.STATIC_URL + "img/placeholder-prato.svg",
    }


def serializar_adicional(adicional):
    return {
        "id": adicional.id,
        "nome": adicional.nome,
        "descricao": adicional.descricao,
        "preco": f"{adicional.preco:.2f}" if adicional.preco is not None else "",
        "preco_formatado": f"R$ {adicional.preco:.2f}".replace(".", ",") if adicional.preco is not None else "",
        "imagem": adicional.imagem.url if adicional.imagem else settings.STATIC_URL + "img/placeholder-prato.svg",
    }


def montar_mensagem_whatsapp(pedido):
    linhas = [
        f"*PRATO-DELIVERY*",
        f"Pedido #{pedido.numero}",
        f"*Status:* {pedido.get_status_display()}",
        "",
        f"*Cliente:* {pedido.nome_cliente}",
        f"*Endereco:* {pedido.endereco}",
    ]
    if pedido.telefone:
        linhas.insert(5, f"*Telefone:* {pedido.telefone}")
    if pedido.lote_quadra:
        linhas.append(f"*Lote/Quadra:* {pedido.lote_quadra}")
    if pedido.complemento:
        linhas.append(f"*Complemento:* {pedido.complemento}")
    if pedido.ponto_referencia:
        linhas.append(f"*Ponto de referencia:* {pedido.ponto_referencia}")
    linhas.extend(
        [
            f"*Talheres:* {'Sim' if pedido.enviar_talheres else 'Nao'}",
            "",
            "*Itens:*",
        ]
    )
    for item in pedido.itens.all():
        linhas.append(
            f"- {item.quantidade}x {item.nome_prato_snapshot} | R$ {item.subtotal:.2f}".replace(".", ",")
        )
        if item.observacao:
            linhas.append(f"  Obs: {item.observacao}")
    if pedido.observacao_geral:
        linhas.extend(["", f"*Observacao geral:* {pedido.observacao_geral}"])
    linhas.extend(["", f"*Pagamento:* {pedido.get_forma_pagamento_display()}"])
    if pedido.forma_pagamento == Pedido.FormaPagamento.PIX:
        pix_chave = _safe_text(getattr(ConfiguracaoEntrega.get_solo(), "pix_chave", ""))
        if pix_chave:
            linhas.append(f"*Chave Pix:* {pix_chave}")
    linhas.extend(
        [
            "",
            f"*Frete:* R$ {pedido.valor_frete:.2f}".replace(".", ","),
            f"*Total:* R$ {pedido.total:.2f}".replace(".", ","),
        ]
    )
    return "\n".join(linhas)


def _normalize_whatsapp_number(value):
    return "".join(char for char in _safe_text(value) if char.isdigit())


def _configured_whatsapp_number(config=None):
    config = config or ConfiguracaoEntrega.objects.order_by("pk").first()
    numero = _normalize_whatsapp_number(getattr(config, "whatsapp_numero", ""))
    return numero or _normalize_whatsapp_number(getattr(settings, "RESTAURANT_WHATSAPP", ""))


def _build_whatsapp_order_url(pedido, config=None):
    numero = _configured_whatsapp_number(config)
    if not numero:
        return ""
    return f"https://wa.me/{numero}?text={quote(montar_mensagem_whatsapp(pedido))}"


@never_cache
def cardapio(request):
    cardapio_context = _resolve_cardapio_pratos()
    pratos = cardapio_context["pratos"]
    adicionais = Adicional.objects.filter(ativo=True)
    bebidas = Bebida.objects.filter(ativo=True)
    pratos_serializados = [serializar_prato(prato) for prato in pratos]
    adicionais_serializados = [serializar_adicional(adicional) for adicional in adicionais]
    bebidas_serializadas = [serializar_bebida(bebida) for bebida in bebidas]
    return render(
        request,
        "pedidos/cardapio.html",
        {
            "pratos": pratos,
            "adicionais": adicionais,
            "bebidas": bebidas,
            "pratos_json": json.dumps(pratos_serializados, ensure_ascii=False),
            "adicionais_json": json.dumps(adicionais_serializados, ensure_ascii=False),
            "bebidas_json": json.dumps(bebidas_serializadas, ensure_ascii=False),
            "cardapio_title_line_1": cardapio_context["title_line_1"],
            "cardapio_title_line_2": cardapio_context["title_line_2"],
            "cardapio_empty_label": cardapio_context["empty_label"],
        },
    )


@never_cache
def checkout(request):
    config = ConfiguracaoEntrega.get_solo()
    pratos_lookup = {f"prato:{prato.id}": {**serializar_prato(prato), "tipo": "prato"} for prato in Prato.objects.all()}
    adicionais_lookup = {
        f"adicional:{adicional.id}": {**serializar_adicional(adicional), "tipo": "adicional"}
        for adicional in Adicional.objects.all()
    }
    bebidas_lookup = {
        f"bebida:{bebida.id}": {**serializar_bebida(bebida), "tipo": "bebida"} for bebida in Bebida.objects.all()
    }
    itens_lookup = {**pratos_lookup, **adicionais_lookup, **bebidas_lookup}
    return render(
        request,
        "pedidos/checkout.html",
        {
            "pratos_lookup_json": itens_lookup,
            "pix_chave": config.pix_chave,
        },
    )


@never_cache
def carrinho(request):
    pratos_lookup = {f"prato:{prato.id}": {**serializar_prato(prato), "tipo": "prato"} for prato in Prato.objects.all()}
    adicionais_lookup = {
        f"adicional:{adicional.id}": {**serializar_adicional(adicional), "tipo": "adicional"}
        for adicional in Adicional.objects.all()
    }
    bebidas_lookup = {
        f"bebida:{bebida.id}": {**serializar_bebida(bebida), "tipo": "bebida"} for bebida in Bebida.objects.all()
    }
    itens_lookup = {**pratos_lookup, **adicionais_lookup, **bebidas_lookup}
    return render(
        request,
        "pedidos/carrinho.html",
        {
            "pratos_lookup_json": itens_lookup,
        },
    )


def _safe_text(value):
    return str(value or "").strip()


def _safe_float(value):
    try:
        normalized = str(value or "").strip().replace(",", ".")
        if not normalized:
            return None
        return float(normalized)
    except (TypeError, ValueError):
        return None


def _parse_optional_time(value):
    raw = _safe_text(value)
    if not raw:
        return None
    parsed = parse_time(raw)
    if parsed is None:
        raise ValueError("Informe um horario valido no formato HH:MM.")
    return parsed


def _setting_float(name, default):
    try:
        value = float(getattr(settings, name, default))
        return value if value > 0 else float(default)
    except (TypeError, ValueError):
        return float(default)


def _setting_int(name, default):
    try:
        value = int(getattr(settings, name, default))
        return value if value >= 0 else int(default)
    except (TypeError, ValueError):
        return int(default)


DELIVERY_ETA_MULTIPLIER = _setting_float("DELIVERY_ETA_MULTIPLIER", 2.2)
DELIVERY_ETA_BUFFER_MINUTES = _setting_int("DELIVERY_ETA_BUFFER_MINUTES", 3)
DELIVERY_ETA_SHORT_TRIP_KM = _setting_float("DELIVERY_ETA_SHORT_TRIP_KM", 6.0)
DELIVERY_ETA_SHORT_TRIP_PENALTY_MINUTES = _setting_int("DELIVERY_ETA_SHORT_TRIP_PENALTY_MINUTES", 1)
DELIVERY_FRETE_PADRAO = Decimal("0.00")


def _photon_attempts(query, limit="8"):
    base_params = {
        "q": query,
        "countrycode": "BR",
        "limit": str(limit),
        "lat": str(RIO_VERDE_CENTER["lat"]),
        "lon": str(RIO_VERDE_CENTER["lon"]),
        "zoom": "12",
        "location_bias_scale": "0.2",
        "bbox": RIO_VERDE_BBOX,
    }
    return [
        {**base_params, "lang": "pt"},
        base_params,
        {"q": query, "countrycode": "BR", "limit": str(limit), "lat": str(RIO_VERDE_CENTER["lat"]), "lon": str(RIO_VERDE_CENTER["lon"])},
        {"q": query, "limit": str(limit), "lat": str(RIO_VERDE_CENTER["lat"]), "lon": str(RIO_VERDE_CENTER["lon"])},
    ]


def _fetch_photon_features(query, limit="8"):
    if not query:
        return []

    payload = None
    for params in _photon_attempts(query, limit=limit):
        request_url = f"{PHOTON_BASE_URL}?{urlencode(params)}"
        external_request = Request(request_url, headers={"User-Agent": "PRATO-DELIVERY/1.0"})
        try:
            with urlopen(external_request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
            continue

    if not payload:
        return []
    return payload.get("features", [])


_RIO_VERDE_BAIRROS_CACHE = {"updated_at": None, "data": []}
_RIO_VERDE_BAIRROS_POLYGONS_CACHE = {"updated_at": None, "data": {}}


def _normalize_key(text):
    value = _safe_text(text).lower()
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in value if not unicodedata.combining(ch))


def _load_bairros_coords_manual():
    path = Path(__file__).resolve().parent / "data" / "bairros_coords_manual.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    if not isinstance(payload, dict):
        return {}
    data = {}
    for name, coords in payload.items():
        if not isinstance(coords, dict):
            continue
        lat = _safe_float(coords.get("lat"))
        lng = _safe_float(coords.get("lng"))
        if lat is None or lng is None:
            continue
        data[_normalize_key(name)] = {"bairro": _safe_text(name), "lat": lat, "lng": lng}
    return data


def _fetch_rio_verde_bairros():
    now = timezone.now()
    cache_updated_at = _RIO_VERDE_BAIRROS_CACHE.get("updated_at")
    if cache_updated_at and (now - cache_updated_at).total_seconds() < 21600:
        return _RIO_VERDE_BAIRROS_CACHE.get("data", [])

    min_lon, min_lat, max_lon, max_lat = [part.strip() for part in RIO_VERDE_BBOX.split(",")]
    query = f"""
[out:json][timeout:25];
(
  node["place"~"neighbourhood|suburb|quarter"]({min_lat},{min_lon},{max_lat},{max_lon});
  way["place"~"neighbourhood|suburb|quarter"]({min_lat},{min_lon},{max_lat},{max_lon});
  relation["place"~"neighbourhood|suburb|quarter"]({min_lat},{min_lon},{max_lat},{max_lon});
  relation["boundary"="administrative"]["admin_level"~"9|10"]({min_lat},{min_lon},{max_lat},{max_lon});
  way["boundary"="administrative"]["admin_level"~"9|10"]({min_lat},{min_lon},{max_lat},{max_lon});
);
out center;
"""
    payload = urlencode({"data": query})
    request = Request(
        f"{OVERPASS_API_URL}?{payload}",
        headers={"User-Agent": "PRATO-DELIVERY/1.0"},
    )
    bairros = []
    seen = set()
    try:
        with urlopen(request, timeout=12) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return _RIO_VERDE_BAIRROS_CACHE.get("data", [])

    for item in result.get("elements", []):
        tags = item.get("tags") or {}
        nome = _safe_text(tags.get("name"))
        if not nome:
            continue
        # Ignore clearly non-neighborhood labels that may appear in admin boundaries.
        low = nome.lower()
        if low in {"rio verde", "goias", "goiás", "brasil", "brazil"}:
            continue
        if len(nome) < 2:
            continue
        lat = item.get("lat")
        lng = item.get("lon")
        if lat is None or lng is None:
            center = item.get("center") or {}
            lat = center.get("lat")
            lng = center.get("lon")
        latf = _safe_float(lat)
        lngf = _safe_float(lng)
        if latf is None or lngf is None:
            continue
        key = nome.lower()
        if key in seen:
            continue
        seen.add(key)
        bairros.append({"bairro": nome, "lat": latf, "lng": lngf})

    bairros.sort(key=lambda row: row["bairro"].lower())
    by_norm = {_normalize_key(row["bairro"]): row for row in bairros if row.get("bairro")}
    manual = _load_bairros_coords_manual()

    final = []
    for bairro_nome in RIO_VERDE_BAIRROS_OFICIAIS:
        key = _normalize_key(bairro_nome)
        found = by_norm.get(key)
        if not found:
            found = manual.get(key)
        if found:
            final.append({"bairro": bairro_nome, "lat": found["lat"], "lng": found["lng"]})

    _RIO_VERDE_BAIRROS_CACHE["updated_at"] = now
    _RIO_VERDE_BAIRROS_CACHE["data"] = final
    return final


def _fetch_rio_verde_bairros_polygons():
    now = timezone.now()
    cache_updated_at = _RIO_VERDE_BAIRROS_POLYGONS_CACHE.get("updated_at")
    if cache_updated_at and (now - cache_updated_at).total_seconds() < 21600:
        return _RIO_VERDE_BAIRROS_POLYGONS_CACHE.get("data", {})

    min_lon, min_lat, max_lon, max_lat = [part.strip() for part in RIO_VERDE_BBOX.split(",")]
    # Fetch administrative/neighborhood boundaries from OSM (relations + ways).
    joined = "|".join(name.replace('"', '\\"') for name in RIO_VERDE_BAIRROS_OFICIAIS)
    query = f"""
[out:json][timeout:60];
(
  relation["name"~"^({joined})$",i]["boundary"="administrative"]({min_lat},{min_lon},{max_lat},{max_lon});
  relation["name"~"^({joined})$",i]["place"~"neighbourhood|suburb|quarter"]({min_lat},{min_lon},{max_lat},{max_lon});
  way["name"~"^({joined})$",i]["boundary"="administrative"]({min_lat},{min_lon},{max_lat},{max_lon});
  way["name"~"^({joined})$",i]["place"~"neighbourhood|suburb|quarter"]({min_lat},{min_lon},{max_lat},{max_lon});
  way["name"~"^({joined})$",i]["landuse"="residential"]({min_lat},{min_lon},{max_lat},{max_lon});
);
out geom;
"""
    body = f"data={query}".encode("utf-8")
    request = Request(
        OVERPASS_API_URL,
        data=body,
        headers={"User-Agent": "PRATO-DELIVERY/1.0", "Content-Type": "application/x-www-form-urlencoded"},
    )

    polygons = {}
    try:
        with urlopen(request, timeout=70) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return _RIO_VERDE_BAIRROS_POLYGONS_CACHE.get("data", {})

    official_by_norm = {_normalize_key(name): name for name in RIO_VERDE_BAIRROS_OFICIAIS}

    def _ring_from_geom(geom):
        ring = []
        for point in geom or []:
            lat = _safe_float(point.get("lat"))
            lng = _safe_float(point.get("lon"))
            if lat is None or lng is None:
                continue
            ring.append([lng, lat])
        if len(ring) < 4:
            return None
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        return ring

    def _feature_from_way(item, official_name):
        ring = _ring_from_geom(item.get("geometry") or [])
        if not ring:
            return None
        return {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"bairro": official_name},
        }

    def _feature_from_relation(item, official_name):
        members = item.get("members") or []
        outers = []
        inners = []
        for member in members:
            geom = member.get("geometry") or []
            ring = _ring_from_geom(geom)
            if not ring:
                continue
            role = (member.get("role") or "").lower()
            if role == "inner":
                inners.append(ring)
            else:
                outers.append(ring)
        if not outers:
            return None
        polygons_coords = []
        for outer in outers:
            coords = [outer]
            coords.extend(inners)
            polygons_coords.append(coords)
        if len(polygons_coords) == 1:
            return {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": polygons_coords[0]},
                "properties": {"bairro": official_name},
            }
        return {
            "type": "Feature",
            "geometry": {"type": "MultiPolygon", "coordinates": polygons_coords},
            "properties": {"bairro": official_name},
        }

    for item in payload.get("elements", []):
        tags = item.get("tags") or {}
        name = _safe_text(tags.get("name"))
        if not name:
            continue
        official_name = official_by_norm.get(_normalize_key(name))
        if not official_name:
            continue
        if official_name in polygons:
            continue
        f = None
        if item.get("type") == "relation":
            f = _feature_from_relation(item, official_name)
        elif item.get("type") == "way":
            f = _feature_from_way(item, official_name)
        if f:
            polygons[official_name] = f

    _RIO_VERDE_BAIRROS_POLYGONS_CACHE["updated_at"] = now
    _RIO_VERDE_BAIRROS_POLYGONS_CACHE["data"] = polygons
    return polygons


def _load_generated_bairros_polygons_geojson():
    path = Path(__file__).resolve().parent / "data" / "bairros_polygons_generated.geojson"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        return None
    features = payload.get("features")
    if not isinstance(features, list):
        return None
    return payload


def _resolve_address_result(address_text):
    features = _fetch_photon_features(address_text, limit="1")
    if not features:
        return None
    normalized = _normalize_autocomplete_item(features[0])
    lat = _safe_float(normalized.get("lat"))
    lng = _safe_float(normalized.get("lng"))
    if lat is None or lng is None:
        return None
    normalized["lat"] = lat
    normalized["lng"] = lng
    return normalized


def _reverse_geocode_result(latitude, longitude):
    lat = _safe_float(latitude)
    lng = _safe_float(longitude)
    if lat is None or lng is None:
        return None

    reverse_url = f"{PHOTON_REVERSE_URL}?{urlencode({'lat': lat, 'lon': lng, 'lang': 'pt'})}"
    external_request = Request(reverse_url, headers={"User-Agent": "PRATO-DELIVERY/1.0"})
    try:
        with urlopen(external_request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None

    features = payload.get("features") or []
    if not features:
        return None

    normalized = _normalize_autocomplete_item(features[0])
    normalized["lat"] = lat
    normalized["lng"] = lng
    return normalized


def _resolve_address_coordinates(address_text):
    resolved = _resolve_address_result(address_text)
    if not resolved:
        return None, None
    return resolved["lat"], resolved["lng"]


def _saved_origin_snapshot(config=None):
    config = config or ConfiguracaoEntrega.objects.order_by("pk").first()
    return {
        "endereco": _safe_text(getattr(config, "origem_endereco", "")),
        "latitude": _safe_float(getattr(config, "origem_latitude", None)),
        "longitude": _safe_float(getattr(config, "origem_longitude", None)),
    }


def _resolve_saved_origin_result(config=None):
    origin = _saved_origin_snapshot(config)
    if origin["latitude"] is None or origin["longitude"] is None:
        return None
    return _origin_result_from_coordinates(
        origin["endereco"],
        origin["latitude"],
        origin["longitude"],
    )


def _blank_origin_result():
    return {
        "label": "",
        "street": "",
        "number": "",
        "district": "",
        "city": "Rio Verde",
        "state": "GO",
        "country": "Brasil",
        "countrycode": "BR",
        "lat": None,
        "lng": None,
        "type": "pending",
        "precision": "pending",
        "precision_label": _address_precision_label("pending"),
        "mode": "pending",
        "source": "pending",
    }


def _same_coordinate(left, right):
    left_float = _safe_float(left)
    right_float = _safe_float(right)
    if left_float is None or right_float is None:
        return left_float is None and right_float is None
    return abs(left_float - right_float) <= 0.0000001


def _origin_matches_saved_config(origin, config=None):
    saved_origin = _saved_origin_snapshot(config)
    return (
        _safe_text(origin.get("endereco")) == _safe_text(saved_origin["endereco"])
        and _same_coordinate(origin.get("latitude"), saved_origin["latitude"])
        and _same_coordinate(origin.get("longitude"), saved_origin["longitude"])
    )


def _origin_result_from_coordinates(address_text=None, latitude=None, longitude=None):
    lat = _safe_float(latitude)
    lng = _safe_float(longitude)
    if lat is None or lng is None:
        return None
    endereco = _safe_text(address_text) or "Ponto confirmado no mapa"
    return {
        "label": endereco,
        "street": endereco,
        "number": "",
        "district": "",
        "city": "Rio Verde",
        "state": "GO",
        "country": "Brasil",
        "countrycode": "BR",
        "lat": lat,
        "lng": lng,
        "type": "manual",
        "precision": "manual",
        "precision_label": _address_precision_label("manual"),
        "mode": "manual",
        "source": "manual",
    }


def _get_origin_coordinates():
    origin_result = _resolve_saved_origin_result()
    if not origin_result:
        return None, None
    return origin_result["lat"], origin_result["lng"]


def _fetch_route_summary(origin_lat, origin_lng, destination_lat, destination_lng):
    origin = f"{origin_lng:.7f},{origin_lat:.7f}"
    destination = f"{destination_lng:.7f},{destination_lat:.7f}"
    query = urlencode({"overview": "false", "alternatives": "false", "steps": "false"})
    request_url = f"{OSRM_ROUTE_BASE_URL}{origin};{destination}?{query}"
    external_request = Request(request_url, headers={"User-Agent": "PRATO-DELIVERY/1.0"})
    try:
        with urlopen(external_request, timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None, None

    if payload.get("code") != "Ok":
        return None, None

    routes = payload.get("routes") or []
    if not routes:
        return None, None

    route = routes[0]
    duration = _safe_float(route.get("duration"))
    distance = _safe_float(route.get("distance"))
    if duration is None or duration <= 0 or distance is None or distance <= 0:
        return None, None
    return duration, distance


def _to_decimal(value):
    try:
        if value is None:
            return None
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _calcular_frete_por_distancia(distance_km, faixas=None):
    distance_decimal = _to_decimal(distance_km)
    if distance_decimal is None or distance_decimal < 0:
        return DELIVERY_FRETE_PADRAO, None

    if faixas is None:
        faixas = list(FaixaFrete.objects.filter(ativo=True).order_by("ordem", "km_limite", "id"))
    else:
        normalized_faixas = []
        for faixa in faixas:
            if not getattr(faixa, "ativo", True):
                continue
            tipo = _safe_text(getattr(faixa, "tipo", FaixaFrete.Tipo.ATE)) or FaixaFrete.Tipo.ATE
            km_limite = _to_decimal(getattr(faixa, "km_limite", None))
            valor = _to_decimal(getattr(faixa, "valor", None))
            if km_limite is None or valor is None:
                continue
            ordem = getattr(faixa, "ordem", 0) or 0
            normalized_faixas.append(
                SimpleNamespace(
                    id=getattr(faixa, "id", None),
                    tipo=tipo,
                    km_limite=km_limite,
                    valor=valor,
                    ordem=int(ordem),
                    ativo=True,
                )
            )
        faixas = sorted(normalized_faixas, key=lambda faixa: (faixa.ordem, faixa.km_limite, faixa.id or 0))

    if not faixas:
        return DELIVERY_FRETE_PADRAO, None

    faixas_ate = [faixa for faixa in faixas if faixa.tipo == FaixaFrete.Tipo.ATE]
    faixas_acima = [faixa for faixa in faixas if faixa.tipo == FaixaFrete.Tipo.ACIMA]

    for faixa in faixas_ate:
        if distance_decimal <= faixa.km_limite:
            return faixa.valor, faixa

    if faixas_acima:
        candidatas = [faixa for faixa in faixas_acima if distance_decimal >= faixa.km_limite]
        if candidatas:
            candidatas.sort(key=lambda faixa: (faixa.km_limite, faixa.ordem, faixa.id), reverse=True)
            return candidatas[0].valor, candidatas[0]
        return faixas_acima[0].valor, faixas_acima[0]

    return faixas_ate[-1].valor, faixas_ate[-1]


def _format_faixa_label(faixa):
    if not faixa:
        return "Nenhuma faixa encontrada"
    prefixo = "Ate" if faixa.tipo == FaixaFrete.Tipo.ATE else "Acima de"
    return f"{prefixo} {faixa.km_limite} km -> R$ {faixa.valor:.2f}".replace(".", ",")


def _masked_api_key(value):
    key = _safe_text(value)
    if len(key) <= 10:
        return key
    return f"{key[:6]}...{key[-4:]}"


def _google_maps_status():
    config = ConfiguracaoEntrega.objects.order_by("pk").first()
    api_key = config.google_maps_api_key_effective if config else getattr(settings, "GOOGLE_MAPS_API_KEY", "")
    enabled = bool(api_key)
    return {
        "enabled": enabled,
        "provider_label": "Google Maps" if enabled else "OpenStreetMap / Photon",
        "api_key_masked": _masked_api_key(api_key),
        "api_key_value": getattr(config, "google_maps_api_key", "") if config else "",
        "language": config.google_maps_language_effective if config else getattr(settings, "GOOGLE_MAPS_LANGUAGE", "pt-BR"),
        "region": config.google_maps_region_effective if config else getattr(settings, "GOOGLE_MAPS_REGION", "BR"),
        "language_value": getattr(config, "google_maps_language", "") if config else "",
        "region_value": getattr(config, "google_maps_region", "") if config else "",
        "required_apis": ["Maps JavaScript API", "Geocoding API"],
        "env_var_names": ["GOOGLE_MAPS_API_KEY", "GOOGLE_MAPS_LANGUAGE", "GOOGLE_MAPS_REGION"],
    }


def _next_faixa_ordem(faixas):
    if not faixas:
        return 10
    return max(int(getattr(faixa, "ordem", 0) or 0) for faixa in faixas) + 10


def _serialize_faixas_for_form(faixas=None, extra_rows=2):
    faixas = list(faixas if faixas is not None else FaixaFrete.objects.order_by("ordem", "km_limite", "id"))
    rows = []
    for faixa in faixas:
        rows.append(
            {
                "row_key": f"existing-{faixa.id}",
                "id": faixa.id,
                "tipo": faixa.tipo,
                "km_limite": f"{faixa.km_limite}",
                "valor": f"{faixa.valor}",
                "ativo": faixa.ativo,
                "ordem": faixa.ordem,
                "is_new": False,
            }
        )

    next_ordem = _next_faixa_ordem(faixas)
    for index in range(extra_rows):
        rows.append(
            {
                "row_key": f"new-{index + 1}",
                "id": "",
                "tipo": FaixaFrete.Tipo.ATE,
                "km_limite": "",
                "valor": "",
                "ativo": True,
                "ordem": next_ordem + (index * 10),
                "is_new": True,
            }
        )
    return rows


def _parse_faixa_rows(post_data):
    row_keys = post_data.getlist("faixa_row_key")
    faixa_ids = post_data.getlist("faixa_id")
    tipos = post_data.getlist("faixa_tipo")
    km_limites = post_data.getlist("faixa_km_limite")
    valores = post_data.getlist("faixa_valor")
    ordens = post_data.getlist("faixa_ordem")
    ativos = set(post_data.getlist("faixa_ativo"))
    deletes = set(post_data.getlist("faixa_delete"))

    rows = []
    total_rows = max(len(row_keys), len(tipos), len(km_limites), len(valores), len(ordens))
    for index in range(total_rows):
        row_key = _safe_text(row_keys[index] if index < len(row_keys) else f"row-{index}")
        faixa_id = _safe_text(faixa_ids[index] if index < len(faixa_ids) else "")
        tipo = _safe_text(tipos[index] if index < len(tipos) else FaixaFrete.Tipo.ATE) or FaixaFrete.Tipo.ATE
        km_limite = _safe_text(km_limites[index] if index < len(km_limites) else "")
        valor = _safe_text(valores[index] if index < len(valores) else "")
        ordem_raw = _safe_text(ordens[index] if index < len(ordens) else "0")
        try:
            ordem = int(ordem_raw or "0")
        except ValueError:
            ordem = 0

        rows.append(
            {
                "row_key": row_key,
                "id": faixa_id,
                "tipo": tipo if tipo in dict(FaixaFrete.Tipo.choices) else FaixaFrete.Tipo.ATE,
                "km_limite": km_limite,
                "valor": valor,
                "ativo": row_key in ativos,
                "delete": row_key in deletes,
                "ordem": ordem,
                "is_new": not faixa_id,
            }
        )
    return rows


def _preview_faixas_from_rows(rows):
    preview_rows = []
    for row in rows:
        if row.get("delete"):
            continue
        km_limite = _to_decimal(row.get("km_limite"))
        valor = _to_decimal(row.get("valor"))
        if km_limite is None or valor is None:
            continue
        preview_rows.append(
            SimpleNamespace(
                id=int(row["id"]) if _safe_text(row.get("id")).isdigit() else None,
                tipo=row.get("tipo") or FaixaFrete.Tipo.ATE,
                km_limite=km_limite,
                valor=valor,
                ordem=int(row.get("ordem") or 0),
                ativo=bool(row.get("ativo")),
            )
        )
    return preview_rows


def _save_faixa_rows(rows):
    existing_ids = set()
    for row in rows:
        faixa_id = _safe_text(row.get("id"))
        if faixa_id.isdigit():
            existing_ids.add(int(faixa_id))

    for faixa in FaixaFrete.objects.exclude(id__in=existing_ids):
        if any(row.get("delete") and _safe_text(row.get("id")) == str(faixa.id) for row in rows):
            faixa.delete()

    for row in rows:
        faixa_id = _safe_text(row.get("id"))
        km_limite = _to_decimal(row.get("km_limite"))
        valor = _to_decimal(row.get("valor"))
        should_delete = row.get("delete")

        if not faixa_id and km_limite is None and valor is None:
            continue

        if km_limite is None or valor is None:
            raise ValueError("Toda faixa precisa de km limite e valor para ser salva.")

        defaults = {
            "tipo": row.get("tipo") or FaixaFrete.Tipo.ATE,
            "km_limite": km_limite,
            "valor": valor,
            "ativo": bool(row.get("ativo")),
            "ordem": int(row.get("ordem") or 0),
        }

        if faixa_id.isdigit():
            faixa = FaixaFrete.objects.get(id=int(faixa_id))
            if should_delete:
                faixa.delete()
                continue
            for field, value in defaults.items():
                setattr(faixa, field, value)
            faixa.save()
            continue

        if should_delete:
            continue
        FaixaFrete.objects.create(**defaults)


def _build_destination_query_from_values(values):
    address = _safe_text(values.get("address") or values.get("destino_teste"))
    if address:
        return address

    parts = [
        _safe_text(values.get("bairro")),
        _safe_text(values.get("rua")),
        _safe_text(values.get("numero")),
        _safe_text(values.get("cidade")) or "Rio Verde",
        _safe_text(values.get("estado")) or "GO",
    ]
    return ", ".join([part for part in parts if part])


def _build_destination_query(request):
    return _build_destination_query_from_values(request.GET)


def _destination_result_from_values(values):
    destination_lat = _safe_float(values.get("lat") or values.get("latitude") or values.get("destino_teste_lat"))
    destination_lng = _safe_float(values.get("lng") or values.get("longitude") or values.get("destino_teste_lng"))
    resolved_label = _safe_text(values.get("resolved_label") or values.get("endereco_formatado") or values.get("destino_teste_label"))
    resolved_type = _safe_text(values.get("resolved_type") or values.get("geocode_tipo") or values.get("destino_teste_tipo"))
    resolved_precision = _safe_text(
        values.get("resolved_precision") or values.get("geocode_precision") or values.get("destino_teste_precision")
    )

    if destination_lat is not None and destination_lng is not None:
        precision = resolved_precision or _address_precision({"type": resolved_type, "number": ""})
        return {
            "label": resolved_label or _build_destination_query_from_values(values),
            "street": _safe_text(values.get("rua")) or resolved_label,
            "number": _safe_text(values.get("numero")),
            "district": _safe_text(values.get("bairro")),
            "city": _safe_text(values.get("cidade")) or "Rio Verde",
            "state": _safe_text(values.get("estado")) or "GO",
            "country": "Brasil",
            "countrycode": "BR",
            "lat": destination_lat,
            "lng": destination_lng,
            "type": resolved_type or "manual",
            "precision": precision or "manual",
            "precision_label": _address_precision_label(precision or "manual"),
            "source": "request",
        }

    destination_query = _build_destination_query_from_values(values)
    if len(destination_query) < 5:
        return None
    return _resolve_address_result(destination_query)


def _destination_result_from_request(request):
    return _destination_result_from_values(request.GET)


def _address_precision(item):
    if not item:
        return "pending"
    kind = _safe_text(item.get("type")).lower()
    number = _safe_text(item.get("number"))
    if kind == "manual":
        return "manual"
    if number:
        return "exact"
    if kind in {"house", "housenumber", "building", "entrance"}:
        return "exact"
    if kind in {"street", "road", "residential", "suburb", "district", "neighbourhood", "locality"}:
        return "approximate"
    return "approximate"


def _address_precision_label(precision):
    mapping = {
        "exact": "Endereco confirmado",
        "approximate": "Endereco aproximado",
        "manual": "Coordenadas manuais",
        "fallback": "Origem padrao",
        "pending": "A confirmar",
    }
    return mapping.get(precision, "A confirmar")


def _normalize_autocomplete_item(feature):
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") or []

    lng = coordinates[0] if len(coordinates) > 1 else None
    lat = coordinates[1] if len(coordinates) > 1 else None

    street = _safe_text(properties.get("street") or properties.get("name"))
    number = _safe_text(properties.get("housenumber"))
    district = _safe_text(
        properties.get("district")
        or properties.get("suburb")
        or properties.get("neighbourhood")
        or properties.get("locality")
    )
    city = _safe_text(properties.get("city") or properties.get("town") or properties.get("village") or properties.get("county"))
    state = _safe_text(properties.get("state"))
    country = _safe_text(properties.get("country"))
    countrycode = _safe_text(properties.get("countrycode")).upper()
    name = _safe_text(properties.get("name"))

    street_label = ", ".join([part for part in [street or name, number] if part])
    place_bits = [bit for bit in [district, city] if bit]
    place_label = ", ".join(place_bits)
    if state:
        place_label = f"{place_label} - {state}" if place_label else state
    label = ", ".join([part for part in [street_label, place_label] if part]) or name
    precision = _address_precision({"type": _safe_text(properties.get("type")), "number": number})

    return {
        "label": label,
        "name": name,
        "type": _safe_text(properties.get("type")),
        "street": street,
        "number": number,
        "district": district,
        "city": city,
        "state": state,
        "country": country,
        "countrycode": countrycode,
        "lat": lat,
        "lng": lng,
        "source": "photon",
        "precision": precision,
        "precision_label": _address_precision_label(precision),
    }


def _autocomplete_priority(item):
    country_ok = item["countrycode"] == "BR" or item["country"].lower() == "brasil"
    state_norm = item["state"].lower()
    state_ok = "goias" in state_norm or "goiás" in state_norm or state_norm == "go"
    city_ok = item["city"].lower() == "rio verde"
    if country_ok and state_ok and city_ok:
        return 0
    if country_ok and state_ok:
        return 1
    if country_ok:
        return 2
    return 3


def _autocomplete_priority_with_hints(item, bairro_hint="", city_hint="", state_hint=""):
    country_ok = item["countrycode"] == "BR" or item["country"].lower() == "brasil"
    state_norm = item["state"].lower()
    city_norm = item["city"].lower()
    district_norm = _normalize_key(item.get("district"))
    bairro_norm = _normalize_key(bairro_hint)
    city_target = _normalize_key(city_hint or "Rio Verde")
    state_target = _normalize_key(state_hint or "GO")
    state_ok = "goias" in state_norm or "goiÃ¡s" in state_norm or state_norm == "go"
    city_ok = city_norm == "rio verde"
    state_match = _normalize_key(item.get("state")) in {state_target, "goias", "go"}
    city_match = _normalize_key(item.get("city")) == city_target
    bairro_match = bool(bairro_norm) and bairro_norm in district_norm
    exact_number = bool(_safe_text(item.get("number")))
    return (
        0 if country_ok else 1,
        0 if state_match or state_ok else 1,
        0 if city_match or city_ok else 1,
        0 if bairro_match else 1,
        0 if exact_number else 1,
    )


@require_GET
def api_address_autocomplete(request):
    query = _safe_text(request.GET.get("q"))
    if len(query) < 3:
        return JsonResponse([], safe=False)
    bairro_hint = _safe_text(request.GET.get("bairro"))
    city_hint = _safe_text(request.GET.get("cidade")) or "Rio Verde"
    state_hint = _safe_text(request.GET.get("estado")) or "GO"

    features = _fetch_photon_features(query, limit="8")
    normalized = [_normalize_autocomplete_item(feature) for feature in features]

    results = []
    seen = set()
    for item in sorted(normalized, key=lambda item: _autocomplete_priority_with_hints(item, bairro_hint, city_hint, state_hint)):
        if not item["label"]:
            continue
        signature = (item["label"].lower(), item["lat"], item["lng"])
        if signature in seen:
            continue
        seen.add(signature)
        if item["countrycode"] not in {"BR", ""}:
            continue
        results.append(
            {
                "label": item["label"],
                "street": item["street"],
                "number": item["number"],
                "district": item["district"],
                "city": item["city"],
                "state": item["state"],
                "country": item["country"] or "Brasil",
                "lat": item["lat"],
                "lng": item["lng"],
                "type": item["type"],
                "precision": item["precision"],
                "precision_label": item["precision_label"],
                "source": item["source"],
            }
        )
        if len(results) >= 8:
            break

    return JsonResponse(results, safe=False)


@require_GET
def api_address_reverse_geocode(request):
    latitude = _safe_float(request.GET.get("lat"))
    longitude = _safe_float(request.GET.get("lng"))
    if latitude is None or longitude is None:
        return JsonResponse({"ok": False}, status=400)

    result = _reverse_geocode_result(latitude, longitude)
    if not result:
        return JsonResponse({"ok": False, "label": "", "lat": latitude, "lng": longitude})

    return JsonResponse(
        {
            "ok": True,
            "label": result["label"],
            "street": result["street"],
            "number": result["number"],
            "district": result["district"],
            "city": result["city"],
            "state": result["state"],
            "country": result["country"] or "Brasil",
            "lat": result["lat"],
            "lng": result["lng"],
            "type": result["type"],
            "precision": result["precision"],
            "precision_label": result["precision_label"],
            "source": "reverse",
        }
    )


@require_GET
def api_address_delivery_time(request):
    destination_result = _destination_result_from_request(request)
    if not destination_result:
        return JsonResponse({"ok": False, "eta_minutes": None})

    origin_config = _saved_origin_snapshot()
    origin_result = _resolve_saved_origin_result()
    if not origin_result:
        return JsonResponse(
            {
                "ok": False,
                "eta_minutes": None,
                "error": "origin_not_configured",
            }
        )
    origin_lat = origin_result["lat"]
    origin_lng = origin_result["lng"]
    duration_seconds, distance_meters = _fetch_route_summary(
        origin_lat,
        origin_lng,
        destination_result["lat"],
        destination_result["lng"],
    )
    if duration_seconds is None or distance_meters is None:
        return JsonResponse({"ok": False, "eta_minutes": None})

    raw_minutes = duration_seconds / 60.0
    distance_km = max(distance_meters / 1000.0, 0.0)
    adjusted_minutes = (raw_minutes * DELIVERY_ETA_MULTIPLIER) + DELIVERY_ETA_BUFFER_MINUTES
    if distance_km <= DELIVERY_ETA_SHORT_TRIP_KM:
        adjusted_minutes += DELIVERY_ETA_SHORT_TRIP_PENALTY_MINUTES
    eta_minutes = max(1, int(math.ceil(adjusted_minutes)))
    frete_valor, faixa = _calcular_frete_por_distancia(distance_km)
    return JsonResponse(
        {
            "ok": True,
            "eta_minutes": eta_minutes,
            "distance_km": round(distance_km, 2),
            "shipping_fee": float(frete_valor),
            "shipping_fee_formatted": f"R$ {frete_valor:.2f}".replace(".", ","),
            "shipping_rule": {
                "id": faixa.id if faixa else None,
                "tipo": faixa.tipo if faixa else None,
                "km_limite": float(faixa.km_limite) if faixa else None,
                "valor": float(faixa.valor) if faixa else None,
            },
            "origin": origin_config["endereco"],
            "origin_lat": origin_lat,
            "origin_lng": origin_lng,
            "origin_mode": origin_result["mode"],
            "origin_label": origin_result["label"],
            "origin_type": origin_result["type"],
            "origin_precision": origin_result["precision"],
            "origin_precision_label": origin_result["precision_label"],
            "destination_lat": destination_result["lat"],
            "destination_lng": destination_result["lng"],
            "destination_label": destination_result["label"],
            "destination_type": destination_result["type"],
            "destination_precision": destination_result["precision"],
            "destination_precision_label": destination_result["precision_label"],
        }
    )


def _create_order_items_from_payload(pedido, itens_payload):
    total = Decimal("0.00")
    prato_ids = []
    adicional_ids = []
    bebida_ids = []
    for item in itens_payload:
        tipo = _safe_text(item.get("tipo") or ("prato" if item.get("prato_id") else ""))
        try:
            item_id = int(item.get("item_id") or item.get("adicional_id") or item.get("bebida_id") or item.get("prato_id"))
        except (TypeError, ValueError):
            raise ValueError("Um dos itens do carrinho e invalido.")
        if tipo == "adicional":
            adicional_ids.append(item_id)
        elif tipo == "bebida":
            bebida_ids.append(item_id)
        else:
            prato_ids.append(item_id)
    pratos = {prato.id: prato for prato in Prato.objects.filter(id__in=prato_ids, ativo=True)}
    adicionais = {adicional.id: adicional for adicional in Adicional.objects.filter(id__in=adicional_ids, ativo=True)}
    bebidas = {bebida.id: bebida for bebida in Bebida.objects.filter(id__in=bebida_ids, ativo=True)}

    for item in itens_payload:
        tipo = _safe_text(item.get("tipo") or ("prato" if item.get("prato_id") else ""))
        try:
            item_id = int(item.get("item_id") or item.get("adicional_id") or item.get("bebida_id") or item.get("prato_id"))
            quantidade = max(int(item.get("quantidade", 1)), 1)
        except (TypeError, ValueError):
            raise ValueError("Um dos itens do carrinho e invalido.")
        observacao = (item.get("observacao") or "").strip()
        prato = None
        adicional = None
        bebida = None
        if tipo == "adicional":
            adicional = adicionais.get(item_id)
            catalog_item = adicional
        elif tipo == "bebida":
            bebida = bebidas.get(item_id)
            catalog_item = bebida
        else:
            prato = pratos.get(item_id)
            catalog_item = prato
        if not catalog_item:
            raise ValueError("Um dos itens nao esta mais disponivel.")
        try:
            preco_bruto = str(item.get("preco", catalog_item.preco or "0.00")).replace("R$", "").replace(" ", "")
            if "," in preco_bruto:
                preco_bruto = preco_bruto.replace(".", "").replace(",", ".")
            preco = Decimal(preco_bruto)
        except (InvalidOperation, TypeError):
            preco = catalog_item.preco or Decimal("0.00")
        item_pedido = ItemPedido.objects.create(
            pedido=pedido,
            prato=prato,
            adicional=adicional,
            bebida=bebida,
            nome_prato_snapshot=catalog_item.nome,
            preco_snapshot=preco,
            quantidade=quantidade,
            observacao=observacao,
        )
        total += item_pedido.subtotal
    return total


@require_POST
@transaction.atomic
def criar_pedido(request):
    payload = request.POST.get("carrinho_payload")
    if not payload:
        return HttpResponseBadRequest("Carrinho vazio.")

    try:
        itens_payload = json.loads(payload)
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Carrinho invalido.")

    if not itens_payload:
        return HttpResponseBadRequest("Carrinho vazio.")

    nome_cliente = request.POST.get("nome_cliente", "").strip() or "Cliente"
    telefone = request.POST.get("telefone", "").strip()
    rua = request.POST.get("rua", "").strip()
    numero = request.POST.get("numero", "").strip()
    bairro = request.POST.get("bairro", "").strip()
    cidade = request.POST.get("cidade", "").strip()
    estado = request.POST.get("estado", "").strip()
    endereco_formatado = request.POST.get("endereco_formatado", "").strip()
    latitude_raw = request.POST.get("latitude", "").strip()
    longitude_raw = request.POST.get("longitude", "").strip()
    endereco_antigo = request.POST.get("endereco", "").strip()
    lote_quadra = request.POST.get("lote_quadra", "").strip()
    complemento = request.POST.get("complemento", "").strip()
    ponto_referencia = request.POST.get("ponto_referencia", "").strip()
    enviar_talheres_raw = request.POST.get("enviar_talheres", "sim").strip().lower()
    observacao_geral = request.POST.get("observacao_geral", "").strip()
    valor_frete_raw = request.POST.get("valor_frete", "").strip()
    distancia_km_raw = request.POST.get("distancia_km", "").strip()
    forma_pagamento = _safe_text(request.POST.get("forma_pagamento"))
    config_entrega = ConfiguracaoEntrega.get_solo()
    if not _configured_whatsapp_number(config_entrega):
        return HttpResponseBadRequest("Configure o numero do WhatsApp antes de finalizar pedidos.")

    endereco_base = f"{rua}, {numero} - {bairro}".strip(" -") if all([rua, numero, bairro]) else (rua or endereco_formatado)
    endereco = endereco_base or endereco_formatado or endereco_antigo
    if cidade and estado and endereco:
        endereco = f"{endereco}, {cidade} - {estado}"

    if not all([numero, cidade, estado, endereco]) or not (rua or endereco_formatado):
        return HttpResponseBadRequest("Preencha os campos obrigatorios.")
    if forma_pagamento not in dict(Pedido.FormaPagamento.choices):
        return HttpResponseBadRequest("Selecione uma forma de pagamento.")
    if forma_pagamento == Pedido.FormaPagamento.PIX and not _safe_text(config_entrega.pix_chave):
        return HttpResponseBadRequest("Configure a chave Pix antes de aceitar pagamento online.")
    enviar_talheres = enviar_talheres_raw != "nao"

    latitude = None
    longitude = None
    valor_frete = Decimal("0.00")
    distancia_km = Decimal("0.00")
    destination_result = _destination_result_from_values(request.POST)
    if not destination_result:
        return HttpResponseBadRequest("Confirme o ponto de entrega no mapa.")

    origin_result = _resolve_saved_origin_result()
    if not origin_result:
        return HttpResponseBadRequest("Configure e salve a origem de entrega antes de receber pedidos.")

    try:
        if latitude_raw:
            latitude = Decimal(latitude_raw)
        if longitude_raw:
            longitude = Decimal(longitude_raw)
    except (InvalidOperation, TypeError):
        latitude = None
        longitude = None
    try:
        if valor_frete_raw:
            valor_frete = Decimal(valor_frete_raw)
        if distancia_km_raw:
            distancia_km = Decimal(distancia_km_raw)
    except (InvalidOperation, TypeError):
        valor_frete = Decimal("0.00")
        distancia_km = Decimal("0.00")

    if destination_result.get("label"):
        endereco_formatado = destination_result["label"]
    latitude = _to_decimal(destination_result.get("lat"))
    longitude = _to_decimal(destination_result.get("lng"))
    duration_seconds, distance_meters = _fetch_route_summary(
        origin_result["lat"],
        origin_result["lng"],
        destination_result["lat"],
        destination_result["lng"],
    )
    if duration_seconds is None or distance_meters is None:
        return HttpResponseBadRequest("Nao foi possivel calcular a rota para o ponto de entrega.")
    distancia_km = Decimal(str(round(max(distance_meters / 1000.0, 0.0), 2)))
    valor_frete, _ = _calcular_frete_por_distancia(distancia_km)

    if distancia_km > 0 and valor_frete == Decimal("0.00"):
        valor_frete, _ = _calcular_frete_por_distancia(distancia_km)
    if valor_frete < 0:
        valor_frete = Decimal("0.00")

    pedido = Pedido.objects.create(
        nome_cliente=nome_cliente,
        telefone=telefone,
        rua=rua,
        numero_endereco=numero,
        bairro=bairro,
        cidade=cidade,
        estado=estado,
        endereco_formatado=endereco_formatado,
        latitude=latitude,
        longitude=longitude,
          endereco=endereco,
          lote_quadra=lote_quadra,
          complemento=complemento,
          ponto_referencia=ponto_referencia,
          forma_pagamento=forma_pagamento,
          enviar_talheres=enviar_talheres,
        observacao_geral=observacao_geral,
        status=Pedido.Status.AGUARDANDO_APROVACAO,
        valor_frete=valor_frete,
        distancia_km=distancia_km,
    )

    try:
        total = _create_order_items_from_payload(pedido, itens_payload)
    except ValueError as exc:
        transaction.set_rollback(True)
        return HttpResponseBadRequest(str(exc))

    pedido.total = total + valor_frete
    pedido.save(update_fields=["total"])
    return redirect("pedidos:sucesso", numero=pedido.numero)


@require_POST
@transaction.atomic
def criar_retirada(request):
    payload = request.POST.get("carrinho_payload")
    if not payload:
        return HttpResponseBadRequest("Carrinho vazio.")

    try:
        itens_payload = json.loads(payload)
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Carrinho invalido.")

    if not itens_payload:
        return HttpResponseBadRequest("Carrinho vazio.")

    config_entrega = ConfiguracaoEntrega.get_solo()
    if not _configured_whatsapp_number(config_entrega):
        return HttpResponseBadRequest("Configure o numero do WhatsApp antes de finalizar pedidos.")

    nome_cliente = request.POST.get("nome_cliente", "").strip() or "Cliente"
    observacao_geral = request.POST.get("observacao_geral", "").strip()
    enviar_talheres_raw = request.POST.get("enviar_talheres", "sim").strip().lower()
    pedido = Pedido.objects.create(
        nome_cliente=nome_cliente,
        telefone="",
        rua="",
        numero_endereco="",
        bairro="",
        cidade="Rio Verde",
        estado="GO",
        endereco_formatado="Retirada no local",
        endereco="Retirada no local",
        forma_pagamento=Pedido.FormaPagamento.DINHEIRO,
        enviar_talheres=enviar_talheres_raw != "nao",
        observacao_geral=observacao_geral,
        status=Pedido.Status.AGUARDANDO_APROVACAO,
        valor_frete=Decimal("0.00"),
        distancia_km=Decimal("0.00"),
    )
    try:
        total = _create_order_items_from_payload(pedido, itens_payload)
    except ValueError as exc:
        transaction.set_rollback(True)
        return HttpResponseBadRequest(str(exc))

    pedido.total = total
    pedido.save(update_fields=["total"])
    return redirect("pedidos:sucesso", numero=pedido.numero)


@never_cache
def sucesso(request, numero):
    pedido = get_object_or_404(Pedido.objects.prefetch_related("itens"), numero=numero)
    mensagem = montar_mensagem_whatsapp(pedido)
    whatsapp_url = _build_whatsapp_order_url(pedido)
    return render(
        request,
        "pedidos/sucesso.html",
        {
            "pedido": pedido,
            "whatsapp_url": whatsapp_url,
        },
    )


def _dashboard_periodo(period):
    hoje = timezone.localdate()
    if period == "month":
        inicio = hoje.replace(day=1)
        return {
            "key": "month",
            "label": "Este mes",
            "inicio": inicio,
            "fim": hoje,
        }
    inicio = hoje - timedelta(days=6)
    return {
        "key": "7d",
        "label": "Ultimos 7 dias",
        "inicio": inicio,
        "fim": hoje,
    }


def _dashboard_days(inicio, fim):
    days = []
    cursor = inicio
    while cursor <= fim:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _dashboard_percentual_vs_ontem(vendas_hoje, vendas_ontem):
    if vendas_ontem <= 0:
        if vendas_hoje <= 0:
            return 0
        return 100
    variacao = ((vendas_hoje - vendas_ontem) / vendas_ontem) * 100
    return int(round(variacao))


def _dashboard_insight(percentual):
    if percentual <= -1:
        return f"As vendas cairam {abs(percentual)}% em relacao a ontem."
    if percentual >= 1:
        return f"As vendas cresceram {percentual}% em relacao a ontem."
    return "As vendas ficaram estaveis em relacao a ontem."


def _heatmap_period_window(period_key):
    hoje = timezone.localdate()
    normalized = (period_key or "7d").strip().lower()

    if normalized == "today":
        return hoje, hoje
    if normalized == "30d":
        return hoje - timedelta(days=29), hoje
    if normalized == "all":
        return None, None
    return hoje - timedelta(days=6), hoje


def _line_path(points):
    if not points:
        return ""
    first = points[0]
    return " ".join(
        [f"M {first['x']:.2f} {first['y']:.2f}"]
        + [f"L {point['x']:.2f} {point['y']:.2f}" for point in points[1:]]
    )


def _build_sales_chart_context(labels, values, average):
    width = 960
    height = 320
    pad = {"top": 28, "right": 26, "bottom": 42, "left": 52}
    chart_w = width - pad["left"] - pad["right"]
    chart_h = height - pad["top"] - pad["bottom"]
    max_y = max([1, *values, average])
    step_x = chart_w / (len(values) - 1) if len(values) > 1 else chart_w

    points = []
    for idx, value in enumerate(values):
        x = pad["left"] + step_x * idx
        y = pad["top"] + chart_h - ((value / max_y) * chart_h)
        points.append({"x": x, "y": y, "v": value})

    line_d = _line_path(points)
    area_d = ""
    if points:
        area_d = (
            f"{line_d} L {points[-1]['x']:.2f} {pad['top'] + chart_h:.2f} "
            f"L {points[0]['x']:.2f} {pad['top'] + chart_h:.2f} Z"
        )
    avg_y = pad["top"] + chart_h - ((average / max_y) * chart_h)
    label_points = []
    for idx, label in enumerate(labels):
        label_points.append(
            {
                "x": pad["left"] + step_x * idx,
                "label": label,
            }
        )

    grid_lines = [pad["top"] + (chart_h / 4) * i for i in range(5)]
    return {
        "width": width,
        "height": height,
        "left": pad["left"],
        "right": width - pad["right"],
        "avg_y": avg_y,
        "line_d": line_d,
        "area_d": area_d,
        "points": points,
        "labels": label_points,
        "grid_lines": grid_lines,
    }


def _build_hour_chart_context(labels, values):
    width = 960
    height = 260
    pad = {"top": 20, "right": 20, "bottom": 34, "left": 40}
    chart_w = width - pad["left"] - pad["right"]
    chart_h = height - pad["top"] - pad["bottom"]
    max_y = max([1, *values])
    step_x = chart_w / (len(values) - 1) if len(values) > 1 else chart_w

    points = []
    for idx, value in enumerate(values):
        x = pad["left"] + step_x * idx
        y = pad["top"] + chart_h - ((value / max_y) * chart_h)
        points.append({"x": x, "y": y, "v": value})

    line_d = _line_path(points)
    label_points = []
    for idx, label in enumerate(labels):
        if idx % 2 == 0 or idx == len(labels) - 1:
            label_points.append({"x": pad["left"] + step_x * idx, "label": label})

    grid_lines = [pad["top"] + (chart_h / 4) * i for i in range(5)]
    return {
        "width": width,
        "height": height,
        "left": pad["left"],
        "right": width - pad["right"],
        "baseline": pad["top"] + chart_h,
        "line_d": line_d,
        "labels": label_points,
        "grid_lines": grid_lines,
    }


@staff_member_required(login_url="/admin/login/")
def cozinha(request):
    periodo = _dashboard_periodo(request.GET.get("period", "7d"))
    inicio = periodo["inicio"]
    fim = periodo["fim"]
    days = _dashboard_days(inicio, fim)

    itens_periodo = ItemPedido.objects.filter(
        pedido__criado_em__date__gte=inicio,
        pedido__criado_em__date__lte=fim,
    )
    pedidos_periodo = Pedido.objects.filter(
        criado_em__date__gte=inicio,
        criado_em__date__lte=fim,
    )

    vendas_por_dia_raw = (
        itens_periodo.annotate(day=TruncDate("pedido__criado_em"))
        .values("day")
        .annotate(total=Sum("quantidade"))
        .order_by("day")
    )
    vendas_por_dia_map = {row["day"]: int(row["total"] or 0) for row in vendas_por_dia_raw}
    vendas_diarias = [vendas_por_dia_map.get(day, 0) for day in days]
    labels_diarias = [day.strftime("%d/%m") for day in days]

    total_vendido_periodo = int(sum(vendas_diarias))
    media_diaria = round(total_vendido_periodo / len(days), 1) if days else 0

    hoje = timezone.localdate()
    ontem = hoje - timedelta(days=1)
    vendidos_hoje = int(
        ItemPedido.objects.filter(pedido__criado_em__date=hoje).aggregate(total=Sum("quantidade")).get("total") or 0
    )
    vendidos_ontem = int(
        ItemPedido.objects.filter(pedido__criado_em__date=ontem).aggregate(total=Sum("quantidade")).get("total") or 0
    )
    variacao_percentual = _dashboard_percentual_vs_ontem(vendidos_hoje, vendidos_ontem)

    faturamento_hoje = Pedido.objects.filter(criado_em__date=hoje).aggregate(total=Sum("total")).get("total") or Decimal("0.00")
    faturamento_periodo = pedidos_periodo.aggregate(total=Sum("total")).get("total") or Decimal("0.00")
    total_pedidos_periodo = pedidos_periodo.count()
    ticket_medio = (
        (faturamento_periodo / total_pedidos_periodo).quantize(Decimal("0.01"))
        if total_pedidos_periodo
        else Decimal("0.00")
    )

    meta_diaria = 20
    percentual_meta = min(100, int(round((vendidos_hoje / meta_diaria) * 100))) if meta_diaria else 0

    ranking_pratos = list(
        itens_periodo.values("nome_prato_snapshot")
        .annotate(total=Sum("quantidade"))
        .order_by("-total", "nome_prato_snapshot")[:5]
    )
    ranking_pratos_top3 = ranking_pratos[:3]

    bairros_top = list(
        pedidos_periodo.exclude(bairro__isnull=True)
        .exclude(bairro__exact="")
        .values("bairro")
        .annotate(total=Sum("total"))
        .order_by("-total", "bairro")
    )
    bairros_periodo_set = {row["bairro"].strip().lower() for row in bairros_top if row.get("bairro")}
    bairros_historico = (
        Pedido.objects.exclude(bairro__isnull=True)
        .exclude(bairro__exact="")
        .values_list("bairro", flat=True)
        .distinct()
    )
    bairros_mapa = sorted(
        {(bairro or "").strip() for bairro in bairros_historico if (bairro or "").strip()},
        key=lambda item: item.lower(),
    )
    bairros_sem_compra = []
    for bairro in bairros_historico:
        nome = (bairro or "").strip()
        if not nome:
            continue
        if nome.lower() in bairros_periodo_set:
            continue
        bairros_sem_compra.append(nome)
    bairros_sem_compra = sorted(set(bairros_sem_compra), key=lambda item: item.lower())

    vendas_por_hora_raw = (
        itens_periodo.annotate(hour=ExtractHour("pedido__criado_em"))
        .values("hour")
        .annotate(total=Sum("quantidade"))
        .order_by("hour")
    )
    vendas_por_hora_map = {int(row["hour"] or 0): int(row["total"] or 0) for row in vendas_por_hora_raw}
    horas_labels = [f"{hour:02d}h" for hour in range(24)]
    vendas_por_hora = [vendas_por_hora_map.get(hour, 0) for hour in range(24)]

    pico_periodo = max(vendas_diarias) if vendas_diarias else 0
    pico_hora_valor = max(vendas_por_hora) if vendas_por_hora else 0
    pico_hora_indice = vendas_por_hora.index(pico_hora_valor) if pico_hora_valor > 0 else 0

    pedidos_novos = Pedido.objects.filter(status=Pedido.Status.NOVO).count()
    pratos_ativos = Prato.objects.filter(ativo=True).count()
    itens_cozinha = itens_periodo.count()
    adicionais_count = 1
    outros_count = max(0, FaixaFrete.objects.filter(ativo=True).count() - 1)

    mais_vendidos_footer = ranking_pratos_top3 if ranking_pratos_top3 else []
    mais_utilizados_footer = ranking_pratos_top3 if ranking_pratos_top3 else []
    outros_footer_nome = ranking_pratos[0]["nome_prato_snapshot"] if ranking_pratos else "Sem dados"
    outros_footer_total = ranking_pratos[0]["total"] if ranking_pratos else 0
    dashboard_payload = {
        "labels": labels_diarias,
        "series": vendas_diarias,
        "average": media_diaria,
        "hour_labels": horas_labels,
        "hour_series": vendas_por_hora,
    }
    sales_chart = _build_sales_chart_context(labels_diarias, vendas_diarias, media_diaria)
    hour_chart = _build_hour_chart_context(horas_labels, vendas_por_hora)

    return render(
        request,
        "pedidos/cozinha_dashboard.html",
        {
            "periodo_key": periodo["key"],
            "periodo_label": periodo["label"],
            "vendas_hoje": vendidos_hoje,
            "media_diaria": media_diaria,
            "variacao_percentual": variacao_percentual,
            "faturamento_hoje": faturamento_hoje,
            "faturamento_hoje_fmt": f"R$ {faturamento_hoje:.2f}".replace(".", ","),
            "ticket_medio": ticket_medio,
            "ticket_medio_fmt": f"R$ {ticket_medio:.2f}".replace(".", ","),
            "meta_diaria": meta_diaria,
            "percentual_meta": percentual_meta,
            "total_vendido_periodo": total_vendido_periodo,
            "total_pedidos_periodo": total_pedidos_periodo,
            "insight_texto": _dashboard_insight(variacao_percentual),
            "ranking_pratos": ranking_pratos,
            "ranking_pratos_top3": ranking_pratos_top3,
            "pico_periodo": pico_periodo,
            "pico_hora_indice": pico_hora_indice,
            "pico_hora_valor": pico_hora_valor,
            "pedidos_novos": pedidos_novos,
            "pratos_ativos": pratos_ativos,
            "itens_cozinha": itens_cozinha,
            "adicionais_count": adicionais_count,
            "outros_count": outros_count,
            "mais_vendidos_footer": mais_vendidos_footer,
            "mais_utilizados_footer": mais_utilizados_footer,
            "outros_footer_nome": outros_footer_nome,
            "outros_footer_total": outros_footer_total,
            "sales_chart": sales_chart,
            "hour_chart": hour_chart,
            "dashboard_payload": dashboard_payload,
            "bairros_top": bairros_top,
            "bairros_sem_compra": bairros_sem_compra,
            "bairros_mapa": bairros_mapa,
        },
    )


@staff_member_required(login_url="/admin/login/")
@require_GET
def api_order_heatmap(request):
    period = request.GET.get("period", "7d")
    start_date, end_date = _heatmap_period_window(period)

    queryset = Pedido.objects.exclude(status=Pedido.Status.CANCELADO).filter(
        latitude__isnull=False,
        longitude__isnull=False,
    )

    if start_date and end_date:
        queryset = queryset.filter(criado_em__date__gte=start_date, criado_em__date__lte=end_date)

    points_raw = queryset.order_by("-criado_em").values("latitude", "longitude", "bairro")[:5000]

    points = []
    for row in points_raw:
        latf = _safe_float(row.get("latitude"))
        lngf = _safe_float(row.get("longitude"))
        if latf is None or lngf is None:
            continue
        if not (-90 <= latf <= 90 and -180 <= lngf <= 180):
            continue
        points.append(
            {
                "lat": latf,
                "lng": lngf,
                "weight": 1,
                "bairro": (row.get("bairro") or "").strip(),
            }
        )

    return JsonResponse(points, safe=False)


@require_GET
def api_bairros_rio_verde(request):
    if request.GET.get("refresh") == "1":
        _RIO_VERDE_BAIRROS_CACHE["updated_at"] = None
        _RIO_VERDE_BAIRROS_CACHE["data"] = []
    bairros = _fetch_rio_verde_bairros()
    return JsonResponse(bairros, safe=False)


@require_GET
def api_bairros_polygons(request):
    if request.GET.get("refresh") == "1":
        _RIO_VERDE_BAIRROS_POLYGONS_CACHE["updated_at"] = None
        _RIO_VERDE_BAIRROS_POLYGONS_CACHE["data"] = {}
    polygons = _fetch_rio_verde_bairros_polygons()
    features = list(polygons.values())
    if len(features) >= 20:
        return JsonResponse({"type": "FeatureCollection", "features": features})

    # Fallback 1: generated local GeoJSON (street-based approximation).
    generated = _load_generated_bairros_polygons_geojson()
    if generated and isinstance(generated.get("features"), list) and generated.get("features"):
        return JsonResponse(generated)

    # Fallback 2: no polygons available.
    return JsonResponse({"type": "FeatureCollection", "features": []})


def _weekday_label_pt(date_value):
    names = [
        "SEGUNDA-FEIRA",
        "TERÇA-FEIRA",
        "QUARTA-FEIRA",
        "QUINTA-FEIRA",
        "SEXTA-FEIRA",
        "SÁBADO",
        "DOMINGO",
    ]
    return names[date_value.weekday()]


def _cozinha_operacao_payload():
    today = timezone.localdate()
    now = timezone.localtime()
    entregues_hoje = Pedido.objects.filter(status=Pedido.Status.FINALIZADO, criado_em__date=today).count()

    pedidos_em_producao = Pedido.objects.filter(status=Pedido.Status.EM_PREPARO).prefetch_related("itens")
    pratos_em_producao = (
        ItemPedido.objects.filter(pedido__status=Pedido.Status.EM_PREPARO)
        .values("nome_prato_snapshot")
        .annotate(total=Sum("quantidade"))
        .order_by("-total", "nome_prato_snapshot")
    )
    total_para_producao = sum(int(row["total"] or 0) for row in pratos_em_producao)

    pratos = []
    for row in pratos_em_producao:
        pratos.append(
            {
                "nome": row["nome_prato_snapshot"],
                "quantidade": int(row["total"] or 0),
            }
        )

    pedidos_cards = []
    for pedido in pedidos_em_producao:
        pratos_total = sum(int(item.quantidade or 0) for item in pedido.itens.all())
        elapsed_min = max(0, int((now - timezone.localtime(pedido.criado_em)).total_seconds() // 60))
        pedidos_cards.append(
            {
                "pedido_numero": pedido.numero,
                "cliente": pedido.nome_cliente,
                "pratos_total": pratos_total,
                "elapsed_min": elapsed_min,
            }
        )

    return {
        "entregues_hoje": entregues_hoje,
        "total_para_producao": total_para_producao,
        "pratos_em_producao": pratos,
        "pedidos_cards": pedidos_cards,
        "pedidos_em_producao": pedidos_em_producao.count(),
        "weekday_label": _weekday_label_pt(today),
        "date_label": today.strftime("%d/%m"),
    }


@staff_member_required(login_url="/admin/login/")
def cozinha_pedidos(request):
    payload = _cozinha_operacao_payload()
    return render(
        request,
        "pedidos/cozinha_operacao.html",
        {
            **payload,
        },
    )


@staff_member_required(login_url="/admin/login/")
@require_GET
def api_cozinha_operacao(request):
    return JsonResponse(_cozinha_operacao_payload())


@staff_member_required(login_url="/admin/login/")
def pedidos_admin(request):
    base = Pedido.objects.prefetch_related("itens")
    aguardando_aprovacao = base.filter(status=Pedido.Status.AGUARDANDO_APROVACAO)[:20]
    pedidos_ativos = base.exclude(
        status__in=[Pedido.Status.AGUARDANDO_APROVACAO, Pedido.Status.FINALIZADO, Pedido.Status.CANCELADO]
    )[:20]
    concluidos = base.filter(status=Pedido.Status.FINALIZADO)[:20]
    cancelados = base.filter(status=Pedido.Status.CANCELADO)[:20]
    return render(
        request,
        "pedidos/pedidos_admin.html",
        {
            "pedidos_aprovacao": aguardando_aprovacao,
            "pedidos_ativos": pedidos_ativos,
            "pedidos_concluidos": concluidos,
            "pedidos_cancelados": cancelados,
            "aprovacao_count": base.filter(status=Pedido.Status.AGUARDANDO_APROVACAO).count(),
            "concluidos_count": base.filter(status=Pedido.Status.FINALIZADO).count(),
            "cancelados_count": base.filter(status=Pedido.Status.CANCELADO).count(),
        },
    )


@staff_member_required(login_url="/admin/login/")
def pedido_detalhe_admin(request, pedido_id):
    pedido = get_object_or_404(Pedido.objects.prefetch_related("itens"), id=pedido_id)
    itens_subtotal = pedido.itens.aggregate(total=Sum("subtotal")).get("total") or Decimal("0.00")
    frete_esperado, faixa_frete_atual = _calcular_frete_por_distancia(pedido.distancia_km)
    total_recalculado = itens_subtotal + pedido.valor_frete
    diferenca_frete = pedido.valor_frete - frete_esperado

    return render(
        request,
        "pedidos/pedido_detalhe_admin.html",
        {
            "active": "pedidos",
            "pedidos_badge": Pedido.objects.exclude(
                status__in=[Pedido.Status.FINALIZADO, Pedido.Status.CANCELADO]
            ).count(),
            "pedido": pedido,
            "itens_subtotal": itens_subtotal,
            "frete_esperado": frete_esperado,
            "faixa_frete_atual": faixa_frete_atual,
            "diferenca_frete": diferenca_frete,
            "frete_confere": diferenca_frete == Decimal("0.00"),
            "total_recalculado": total_recalculado,
            "total_confere": total_recalculado == pedido.total,
        },
    )


@staff_member_required(login_url="/admin/login/")
def ajustes_admin(request):
    ajustes_aba = (_safe_text(request.GET.get("aba")) or "geral").lower()
    if ajustes_aba not in {"geral", "frete", "google", "whatsapp", "pagamento"}:
        ajustes_aba = "geral"

    config = ConfiguracaoEntrega.get_solo()
    origem = _saved_origin_snapshot(config)
    origem_resolution = _resolve_saved_origin_result(config) or _blank_origin_result()
    faixa_rows = _serialize_faixas_for_form()
    feedback = None
    feedback_kind = "success"
    preview = None
    google_maps_status = _google_maps_status()

    if request.GET.get("saved") == "1":
        feedback = "Ajustes atualizados."

    if request.method == "POST":
        action = _safe_text(request.POST.get("action"))
        action_tabs = {
            "save_geral": "geral",
            "save_frete": "frete",
            "test_frete": "frete",
            "save_google": "google",
            "save_whatsapp": "whatsapp",
            "save_pagamento": "pagamento",
        }
        ajustes_aba = action_tabs.get(action, ajustes_aba)
        origem = {
            "endereco": _safe_text(request.POST.get("origem_endereco")) or origem["endereco"],
            "latitude": _safe_text(request.POST.get("origem_latitude")) or (_safe_text(origem["latitude"]) if origem["latitude"] is not None else ""),
            "longitude": _safe_text(request.POST.get("origem_longitude")) or (_safe_text(origem["longitude"]) if origem["longitude"] is not None else ""),
        }
        origem_resolution = (
            _origin_result_from_coordinates(origem["endereco"], origem["latitude"], origem["longitude"])
            if _safe_float(origem["latitude"]) is not None and _safe_float(origem["longitude"]) is not None
            else _blank_origin_result()
        )
        faixa_rows = _parse_faixa_rows(request.POST)

        if action == "save_geral":
            try:
                config.horario_abertura = _parse_optional_time(request.POST.get("horario_abertura"))
                config.horario_fechamento = _parse_optional_time(request.POST.get("horario_fechamento"))
                config.save()
                return redirect(f"{request.path}?saved=1&aba=geral")
            except ValueError as exc:
                feedback = str(exc)
                feedback_kind = "error"

        if action == "save_frete":
            try:
                if _to_decimal(origem["latitude"]) is None or _to_decimal(origem["longitude"]) is None:
                    raise ValueError("Confirme a origem no mapa antes de salvar os ajustes.")
                config.origem_endereco = origem["endereco"]
                config.origem_latitude = _to_decimal(origem["latitude"])
                config.origem_longitude = _to_decimal(origem["longitude"])
                config.save()
                _save_faixa_rows(faixa_rows)
                return redirect(f"{request.path}?saved=1&aba=frete")
            except ValueError as exc:
                feedback = str(exc)
                feedback_kind = "error"

        if action == "save_google":
            config.google_maps_api_key = _safe_text(request.POST.get("google_maps_api_key"))
            config.google_maps_language = _safe_text(request.POST.get("google_maps_language")) or "pt-BR"
            config.google_maps_region = _safe_text(request.POST.get("google_maps_region")) or "BR"
            config.save()
            return redirect(f"{request.path}?saved=1&aba=google")

        if action == "save_whatsapp":
            numero = _normalize_whatsapp_number(request.POST.get("whatsapp_numero"))
            if numero and len(numero) < 12:
                feedback = "Informe o WhatsApp com DDI e DDD. Exemplo: 5564999999999."
                feedback_kind = "error"
            else:
                config.whatsapp_numero = numero
                config.save()
                return redirect(f"{request.path}?saved=1&aba=whatsapp")

        if action == "save_pagamento":
            config.pix_chave = _safe_text(request.POST.get("pix_chave"))
            config.save()
            return redirect(f"{request.path}?saved=1&aba=pagamento")

        if action == "test_frete":
            destino_teste = _safe_text(request.POST.get("destino_teste"))
            if _safe_float(origem["latitude"]) is None or _safe_float(origem["longitude"]) is None:
                feedback = "Confirme a origem no mapa antes de calcular o teste."
                feedback_kind = "error"
            elif len(destino_teste) < 5 and not (_safe_text(request.POST.get("destino_teste_lat")) and _safe_text(request.POST.get("destino_teste_lng"))):
                feedback = "Confirme um destino de teste no mapa antes de calcular."
                feedback_kind = "error"
            else:
                origem_lat = origem_resolution["lat"]
                origem_lng = origem_resolution["lng"]
                destino_resolvido = _destination_result_from_values(request.POST)
                if not destino_resolvido:
                    feedback = "Nao foi possivel localizar o destino de teste informado."
                    feedback_kind = "error"
                else:
                    duration_seconds, distance_meters = _fetch_route_summary(
                        origem_lat,
                        origem_lng,
                        destino_resolvido["lat"],
                        destino_resolvido["lng"],
                    )
                    if duration_seconds is None or distance_meters is None:
                        feedback = "Nao foi possivel calcular a rota viaria para esse destino."
                        feedback_kind = "error"
                    else:
                        distance_km = round(max(distance_meters / 1000.0, 0.0), 2)
                        frete_valor, faixa_aplicada = _calcular_frete_por_distancia(
                            distance_km,
                            faixas=_preview_faixas_from_rows(faixa_rows),
                        )
                        preview = {
                            "destino_digitado": destino_teste,
                            "origem_endereco": origem_resolution["label"],
                            "origem_lat": origem_lat,
                            "origem_lng": origem_lng,
                            "origem_mode": origem_resolution["mode"],
                            "origem_precision": origem_resolution["precision"],
                            "origem_precision_label": origem_resolution["precision_label"],
                            "origem_tipo": origem_resolution["type"],
                            "destino_label": destino_resolvido.get("label") or destino_teste,
                            "destino_lat": destino_resolvido["lat"],
                            "destino_lng": destino_resolvido["lng"],
                            "destino_tipo": destino_resolvido.get("type") or "desconhecido",
                            "destino_precision": destino_resolvido.get("precision") or "pending",
                            "destino_precision_label": destino_resolvido.get("precision_label") or _address_precision_label("pending"),
                            "distance_km": distance_km,
                            "duration_minutes": int(math.ceil(duration_seconds / 60.0)),
                            "frete_valor": frete_valor,
                            "faixa_label": _format_faixa_label(faixa_aplicada),
                            "origem_nao_salva": not _origin_matches_saved_config(origem, config),
                        }

    ultimo_pedido = Pedido.objects.prefetch_related("itens").first()
    ultimo_pedido_auditoria = None
    if ultimo_pedido:
        subtotal_itens = ultimo_pedido.itens.aggregate(total=Sum("subtotal")).get("total") or Decimal("0.00")
        frete_esperado, faixa_atual = _calcular_frete_por_distancia(ultimo_pedido.distancia_km)
        ultimo_pedido_auditoria = {
            "pedido": ultimo_pedido,
            "subtotal_itens": subtotal_itens,
            "frete_esperado": frete_esperado,
            "faixa_label": _format_faixa_label(faixa_atual),
            "diferenca_frete": ultimo_pedido.valor_frete - frete_esperado,
            "total_recalculado": subtotal_itens + ultimo_pedido.valor_frete,
        }

    return render(
        request,
        "pedidos/ajustes_admin.html",
        {
            "active": "ajustes",
            "ajustes_aba": ajustes_aba,
            "pedidos_badge": Pedido.objects.exclude(
                status__in=[Pedido.Status.FINALIZADO, Pedido.Status.CANCELADO]
            ).count(),
            "origem": origem,
            "origem_resolution": origem_resolution,
            "faixa_rows": faixa_rows,
            "feedback": feedback,
            "feedback_kind": feedback_kind,
            "preview": preview,
            "google_maps_status": google_maps_status,
            "whatsapp_numero": config.whatsapp_numero,
            "pix_chave": config.pix_chave,
            "horario_abertura": config.horario_abertura.strftime("%H:%M") if config.horario_abertura else "",
            "horario_fechamento": config.horario_fechamento.strftime("%H:%M") if config.horario_fechamento else "",
            "ultimo_pedido_auditoria": ultimo_pedido_auditoria,
        },
    )


@staff_member_required(login_url="/admin/login/")
def adicionais_admin(request):
    adicionais = Adicional.objects.all()
    adicional_edicao = None
    form = AdicionalForm()

    edit_id = request.GET.get("edit")
    if edit_id:
        adicional_edicao = get_object_or_404(Adicional, id=edit_id)
        form = AdicionalForm(instance=adicional_edicao)

    return render(
        request,
        "pedidos/adicionais_gestao.html",
        {
            "adicionais": adicionais,
            "form": form,
            "adicional_edicao": adicional_edicao,
            "form_modal_open": bool(adicional_edicao),
        },
    )


@staff_member_required(login_url="/admin/login/")
def outros_admin(request):
    return render(
        request,
        "pedidos/modulo_admin_placeholder.html",
        {
            "active": "outros",
            "titulo": "Outros",
            "descricao": "Área dedicada para itens e configurações complementares da operação.",
        },
    )


@staff_member_required(login_url="/admin/login/")
def cupons_admin(request):
    return render(
        request,
        "pedidos/modulo_admin_placeholder.html",
        {
            "active": "cupons",
            "titulo": "Cupons",
            "descricao": "Área dedicada para criação e gestão de cupons promocionais.",
        },
    )


@staff_member_required(login_url="/admin/login/")
def gestao_pratos(request):
    pratos = Prato.objects.all()
    prato_edicao = None
    form = PratoForm()

    edit_id = request.GET.get("edit")
    if edit_id:
        prato_edicao = get_object_or_404(Prato, id=edit_id)
        form = PratoForm(instance=prato_edicao)

    return render(
        request,
        "pedidos/pratos_gestao.html",
        {
            "pratos": pratos,
            "form": form,
            "prato_edicao": prato_edicao,
            "form_modal_open": bool(prato_edicao),
        },
    )


@staff_member_required(login_url="/admin/login/")
@require_POST
def salvar_prato(request):
    prato_id = request.POST.get("prato_id")
    prato = get_object_or_404(Prato, id=prato_id) if prato_id else None
    form = PratoForm(request.POST, request.FILES, instance=prato)
    if form.is_valid():
        form.save()
        return redirect("pedidos:gestao_pratos")

    pratos = Prato.objects.all()
    return render(
        request,
        "pedidos/pratos_gestao.html",
        {
            "pratos": pratos,
            "form": form,
            "prato_edicao": prato,
            "form_modal_open": True,
        },
        status=400,
    )


@staff_member_required(login_url="/admin/login/")
@require_POST
def alternar_prato(request, prato_id):
    prato = get_object_or_404(Prato, id=prato_id)
    prato.ativo = not prato.ativo
    prato.save(update_fields=["ativo"])
    return redirect("pedidos:gestao_pratos")


def _delete_catalog_image(model, object_id):
    item = get_object_or_404(model, id=object_id)
    if not item.imagem:
        return JsonResponse(
            {
                "ok": True,
                "message": "Item sem imagem.",
                "placeholder": settings.STATIC_URL + "img/placeholder-prato.svg",
            }
        )

    item.imagem.delete(save=False)
    item.imagem = None
    item.save(update_fields=["imagem"])
    return JsonResponse(
        {
            "ok": True,
            "message": "Imagem excluida.",
            "placeholder": settings.STATIC_URL + "img/placeholder-prato.svg",
        }
    )


@staff_member_required(login_url="/admin/login/")
@require_POST
def excluir_imagem_prato(request, prato_id):
    return _delete_catalog_image(Prato, prato_id)


@staff_member_required(login_url="/admin/login/")
def gestao_bebidas(request):
    bebidas = Bebida.objects.all()
    bebida_edicao = None
    form = BebidaForm()

    edit_id = request.GET.get("edit")
    if edit_id:
        bebida_edicao = get_object_or_404(Bebida, id=edit_id)
        form = BebidaForm(instance=bebida_edicao)

    return render(
        request,
        "pedidos/bebidas_gestao.html",
        {
            "bebidas": bebidas,
            "form": form,
            "bebida_edicao": bebida_edicao,
            "form_modal_open": bool(bebida_edicao),
        },
    )


@staff_member_required(login_url="/admin/login/")
@require_POST
def salvar_bebida(request):
    bebida_id = request.POST.get("bebida_id")
    bebida = get_object_or_404(Bebida, id=bebida_id) if bebida_id else None
    form = BebidaForm(request.POST, request.FILES, instance=bebida)
    if form.is_valid():
        form.save()
        return redirect("pedidos:gestao_bebidas")

    bebidas = Bebida.objects.all()
    return render(
        request,
        "pedidos/bebidas_gestao.html",
        {
            "bebidas": bebidas,
            "form": form,
            "bebida_edicao": bebida,
            "form_modal_open": True,
        },
        status=400,
    )


@staff_member_required(login_url="/admin/login/")
@require_POST
def alternar_bebida(request, bebida_id):
    bebida = get_object_or_404(Bebida, id=bebida_id)
    bebida.ativo = not bebida.ativo
    bebida.save(update_fields=["ativo"])
    return redirect("pedidos:gestao_bebidas")


@staff_member_required(login_url="/admin/login/")
@require_POST
def excluir_imagem_bebida(request, bebida_id):
    return _delete_catalog_image(Bebida, bebida_id)


@staff_member_required(login_url="/admin/login/")
@require_POST
def salvar_adicional(request):
    adicional_id = request.POST.get("adicional_id")
    adicional = get_object_or_404(Adicional, id=adicional_id) if adicional_id else None
    form = AdicionalForm(request.POST, request.FILES, instance=adicional)
    if form.is_valid():
        form.save()
        return redirect("pedidos:adicionais_admin")

    adicionais = Adicional.objects.all()
    return render(
        request,
        "pedidos/adicionais_gestao.html",
        {
            "adicionais": adicionais,
            "form": form,
            "adicional_edicao": adicional,
            "form_modal_open": True,
        },
        status=400,
    )


@staff_member_required(login_url="/admin/login/")
@require_POST
def alternar_adicional(request, adicional_id):
    adicional = get_object_or_404(Adicional, id=adicional_id)
    adicional.ativo = not adicional.ativo
    adicional.save(update_fields=["ativo"])
    return redirect("pedidos:adicionais_admin")


@staff_member_required(login_url="/admin/login/")
@require_POST
def excluir_imagem_adicional(request, adicional_id):
    return _delete_catalog_image(Adicional, adicional_id)


@require_POST
def atualizar_status_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id)
    status = request.POST.get("status")
    if status not in dict(Pedido.Status.choices):
        return HttpResponseBadRequest("Status invalido.")
    pedido.status = status
    pedido.save(update_fields=["status"])
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "status": pedido.get_status_display()})
    return redirect("pedidos:cozinha_pedidos")


@staff_member_required(login_url="/admin/login/")
@require_GET
def api_pedidos_cozinha(request):
    pedidos = Pedido.objects.prefetch_related("itens").all()[:20]
    data = []
    for pedido in pedidos:
        data.append(
            {
                "id": pedido.id,
                "numero": pedido.numero,
                "cliente": pedido.nome_cliente,
                "telefone": pedido.telefone,
                "rua": pedido.rua,
                "numero_endereco": pedido.numero_endereco,
                "bairro": pedido.bairro,
                "cidade": pedido.cidade,
                "estado": pedido.estado,
                "endereco": pedido.endereco,
                "endereco_formatado": pedido.endereco_formatado,
                "lote_quadra": pedido.lote_quadra,
                "complemento": pedido.complemento,
                "ponto_referencia": pedido.ponto_referencia,
                "latitude": float(pedido.latitude) if pedido.latitude is not None else None,
                "longitude": float(pedido.longitude) if pedido.longitude is not None else None,
                "google_maps_route_url": pedido.google_maps_route_url,
                "has_coordinates": pedido.has_coordinates,
                "enviar_talheres": pedido.enviar_talheres,
                "distancia_km": float(pedido.distancia_km) if pedido.distancia_km is not None else 0,
                "valor_frete": f"R$ {pedido.valor_frete:.2f}".replace(".", ","),
                "observacao_geral": pedido.observacao_geral,
                "status": pedido.status,
                "status_label": pedido.get_status_display(),
                "horario": pedido.criado_em.strftime("%H:%M"),
                "total": f"R$ {pedido.total:.2f}".replace(".", ","),
                "itens": [
                    {
                        "nome": item.nome_prato_snapshot,
                        "quantidade": item.quantidade,
                        "observacao": item.observacao,
                        "subtotal": f"R$ {item.subtotal:.2f}".replace(".", ","),
                    }
                    for item in pedido.itens.all()
                ],
            }
        )
    return JsonResponse({"pedidos": data, "status_choices": list(Pedido.Status.choices)})
