from pathlib import Path
import os

import dj_database_url
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _split_env(name, default=""):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]

SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-change-me")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"

ALLOWED_HOSTS = _split_env("ALLOWED_HOSTS", "127.0.0.1,localhost")
CSRF_TRUSTED_ORIGINS = _split_env(
    "CSRF_TRUSTED_ORIGINS",
    "http://127.0.0.1:8000,http://localhost:8000",
)

PRODUCTION_HOSTS = [
    "prato-delivery.onrender.com",
    "www.pratodelivery.com.br",
    "pratodelivery.com.br",
]
PRODUCTION_CSRF_ORIGINS = [f"https://{host}" for host in PRODUCTION_HOSTS]

for host in PRODUCTION_HOSTS:
    if host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(host)

for origin in PRODUCTION_CSRF_ORIGINS:
    if origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(origin)

render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
if render_hostname:
    if render_hostname not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(render_hostname)
    render_origin = f"https://{render_hostname}"
    if render_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(render_origin)

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
