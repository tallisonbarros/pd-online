from django.conf import settings

from .models import ConfiguracaoEntrega


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

    return {
        "PRATO_FRONTEND_CONFIG": {
            "google_maps_api_key": google_maps_api_key,
            "google_maps_language": google_maps_language,
            "google_maps_region": google_maps_region,
            "checkout_map_provider": checkout_map_provider,
        }
    }
