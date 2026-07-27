from django.conf import settings
from django.utils import timezone

from .models import ConfiguracaoEntrega, Pedido
from .turno_services import cart_window_for_turno

DIRETOR_GROUP_NAME = "Diretor"


def _cart_operational_window(config, now=None):
    return cart_window_for_turno(config=config, now=now or timezone.localtime())


def frontend_config(request):
    config = ConfiguracaoEntrega.objects.order_by("pk").first()
    google_maps_api_key = (
        config.google_maps_api_key_effective if config else getattr(settings, "GOOGLE_MAPS_API_KEY", "")
    )
    google_maps_language = (
        config.google_maps_language_effective if config else getattr(settings, "GOOGLE_MAPS_LANGUAGE", "pt-BR")
    )
    google_maps_region = (
        config.google_maps_region_effective if config else getattr(settings, "GOOGLE_MAPS_REGION", "BR")
    )
    checkout_map_provider = "google" if google_maps_api_key else "google_unconfigured"
    cart_window = _cart_operational_window(config)

    return {
        "PRATO_FRONTEND_CONFIG": {
            "google_maps_api_key": google_maps_api_key,
            "google_maps_language": google_maps_language,
            "google_maps_region": google_maps_region,
            "checkout_map_provider": checkout_map_provider,
            "cart_cycle_key": cart_window["cycle_key"],
            "cart_expires_at": cart_window["expires_at"],
            "server_now": cart_window["server_now"],
            "turno_codigo": cart_window["turno_codigo"],
            "promocao_habilitada": cart_window["promocao_habilitada"],
            "cupom_habilitado": cart_window["cupom_habilitado"],
            "entrega_habilitada": cart_window["entrega_habilitada"],
            "retirada_habilitada": cart_window["retirada_habilitada"],
        }
    }


def ops_sidebar_counts(request):
    if not request.path.startswith("/controle/"):
        return {}
    user = getattr(request, "user", None)
    if not getattr(user, "is_staff", False):
        return {}

    can_view_dashboard = user.groups.filter(name=DIRETOR_GROUP_NAME).exists()
    active_statuses = [
        Pedido.Status.NOVO,
        Pedido.Status.EM_PREPARO,
        Pedido.Status.AGUARDANDO_ENTREGADOR,
        Pedido.Status.SAIU_ENTREGA,
    ]
    return {
        "ops_pedidos_badge": Pedido.objects.filter(status__in=active_statuses).count(),
        "ops_aprovacao_count": Pedido.objects.filter(status=Pedido.Status.AGUARDANDO_APROVACAO).count(),
        "ops_can_view_dashboard": can_view_dashboard,
    }
