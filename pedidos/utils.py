from datetime import timedelta
from urllib.parse import urlencode

WEEKDAY_LABELS_LONG = {
    0: "segunda",
    1: "terça",
    2: "quarta",
    3: "quinta",
    4: "sexta",
    5: "sábado",
    6: "domingo",
}


def closed_dates_map(start_date, days=14):
    from .models import DataFechada

    end_date = start_date + timedelta(days=max(days - 1, 0))
    return {
        item.data: item
        for item in DataFechada.objects.filter(ativo=True, data__gte=start_date, data__lte=end_date)
    }


def is_closed_date(target_date, closed_dates=None):
    if closed_dates is None:
        closed_dates = closed_dates_map(target_date, days=1)
    return target_date in closed_dates


def next_open_date(start_date, closed_dates=None, max_days=14):
    closed_dates = closed_dates if closed_dates is not None else closed_dates_map(start_date, days=max_days)
    for offset in range(max_days):
        candidate = start_date + timedelta(days=offset)
        if candidate not in closed_dates:
            return candidate
    return start_date


def relative_day_label(target_date, current_date, *, capitalize=False):
    if target_date == current_date:
        label = "hoje"
    elif target_date == current_date + timedelta(days=1):
        label = "amanhã"
    else:
        label = WEEKDAY_LABELS_LONG[target_date.weekday()]
    return label.capitalize() if capitalize else label


def build_route_origin():
    from .models import ConfiguracaoEntrega

    config = ConfiguracaoEntrega.objects.order_by("pk").first()
    if not config or config.origem_latitude is None or config.origem_longitude is None:
        return ""
    return f"{config.origem_latitude},{config.origem_longitude}"


def build_order_destination(order):
    has_lat = getattr(order, "latitude", None) is not None and str(getattr(order, "latitude", "")).strip() != ""
    has_lng = getattr(order, "longitude", None) is not None and str(getattr(order, "longitude", "")).strip() != ""
    if has_lat and has_lng:
        return f"{order.latitude},{order.longitude}"

    parts = [
        getattr(order, "rua", ""),
        getattr(order, "numero_endereco", ""),
        getattr(order, "bairro", ""),
        getattr(order, "cidade", "Rio Verde"),
        getattr(order, "estado", "GO"),
    ]
    destination = ", ".join([str(part).strip() for part in parts if str(part).strip()])
    if destination:
        return destination
    return str(getattr(order, "endereco", "")).strip()


def build_google_maps_route_url(order):
    destination = build_order_destination(order)
    params = {
        "api": "1",
        "origin": build_route_origin(),
        "destination": destination,
        "travelmode": "driving",
    }
    return "https://www.google.com/maps/dir/?" + urlencode(params)
