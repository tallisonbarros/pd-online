from pathlib import Path
import os

import dj_database_url
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _split_env(name, default=""):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def _append_unique(values, additions):
    for item in additions:
        if item and item not in values:
            values.append(item)


SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-change-me")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"

ALLOWED_HOSTS = _split_env("ALLOWED_HOSTS", "127.0.0.1,localhost")
CSRF_TRUSTED_ORIGINS = _split_env(
    "CSRF_TRUSTED_ORIGINS",
    "http://127.0.0.1:8000,http://localhost:8000",
)

# The Render dashboard can retain old environment values after manual edits.
# Keep the known production domains here as a guarded fallback while still
# treating ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS as the primary deploy config.
DEFAULT_PRODUCTION_HOSTS = [
    "prato-delivery.onrender.com",
    "www.pratodelivery.com.br",
    "pratodelivery.com.br",
]
DEFAULT_PRODUCTION_CSRF_ORIGINS = [f"https://{host}" for host in DEFAULT_PRODUCTION_HOSTS]

_append_unique(ALLOWED_HOSTS, DEFAULT_PRODUCTION_HOSTS)
_append_unique(CSRF_TRUSTED_ORIGINS, DEFAULT_PRODUCTION_CSRF_ORIGINS)

render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
if render_hostname:
    _append_unique(ALLOWED_HOSTS, [render_hostname])
    _append_unique(CSRF_TRUSTED_ORIGINS, [f"https://{render_hostname}"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "pedidos",
]

MIDDLEWARE = [
    "pedidos.middleware.HealthcheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "pedidos.context_processors.frontend_config",
                "pedidos.context_processors.ops_sidebar_counts",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

default_database_url = f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
DATABASES = {
    "default": dj_database_url.parse(
        os.getenv("DATABASE_URL", default_database_url),
        conn_max_age=600,
        ssl_require=not DEBUG and "postgres" in os.getenv("DATABASE_URL", ""),
    )
}
if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
    DATABASES["default"].setdefault("OPTIONS", {})
    DATABASES["default"]["OPTIONS"].setdefault("timeout", 20)

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

if not DEBUG:
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

RESTAURANT_WHATSAPP = os.getenv("RESTAURANT_WHATSAPP", "")
DELIVERY_ETA_MULTIPLIER = os.getenv("DELIVERY_ETA_MULTIPLIER", "2.2")
DELIVERY_ETA_BUFFER_MINUTES = os.getenv("DELIVERY_ETA_BUFFER_MINUTES", "3")
DELIVERY_ETA_SHORT_TRIP_KM = os.getenv("DELIVERY_ETA_SHORT_TRIP_KM", "6")
DELIVERY_ETA_SHORT_TRIP_PENALTY_MINUTES = os.getenv("DELIVERY_ETA_SHORT_TRIP_PENALTY_MINUTES", "1")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
GOOGLE_MAPS_LANGUAGE = os.getenv("GOOGLE_MAPS_LANGUAGE", "pt-BR").strip() or "pt-BR"
GOOGLE_MAPS_REGION = os.getenv("GOOGLE_MAPS_REGION", "BR").strip() or "BR"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
