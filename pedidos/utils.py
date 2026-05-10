from urllib.parse import urlencode


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
