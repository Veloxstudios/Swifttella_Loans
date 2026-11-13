"""Django settings for the Swiftella Loans application database.

All secrets come from environment variables. See README.md for the list.
"""

import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-insecure-key-do-not-use-in-production"
    else:
        raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off.")

# Fernet key used to encrypt NI numbers and bank account numbers at rest.
# Generate one with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FIELD_ENCRYPTION_KEY = os.environ.get("FIELD_ENCRYPTION_KEY", "")
if not FIELD_ENCRYPTION_KEY:
    if DEBUG:
        FIELD_ENCRYPTION_KEY = "cSaU5qxeIF90YLF07ysz2dyhZ_jpeBpanip3wrfIGZs="  # dev only
    else:
        raise RuntimeError("FIELD_ENCRYPTION_KEY must be set when DJANGO_DEBUG is off.")

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "loans",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "loans.security.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "swiftella.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "loans.context.site_links",
            ],
        },
    },
]

WSGI_APPLICATION = "swiftella.wsgi.application"

# SQLite locally; set DATABASE_URL (e.g. Railway Postgres) in production.
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

# Shared cache for rate limits. The database is used so every gunicorn worker
# sees the same counts; `createcachetable` in the Procfile creates the table.
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    if DEBUG
    else {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "swiftella_cache"}
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/London"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        if DEBUG
        else "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Security hardening for production.
# Sessions end after 30 minutes without activity and when the browser closes.
SESSION_COOKIE_AGE = int(os.environ.get("SESSION_IDLE_SECONDS", 30 * 60))
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"  # "no-referrer" makes Chrome send Origin: null and fail CSRF
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# Number of proxies in front of the app that add to X-Forwarded-For
# (Railway's edge adds one). Set to 0 when not behind a proxy.
TRUSTED_PROXIES = int(os.environ.get("TRUSTED_PROXIES", 0 if DEBUG else 1))

# Rate limits.
APPLY_RATE_LIMIT = int(os.environ.get("APPLY_RATE_LIMIT", 5))          # applications per IP...
APPLY_RATE_WINDOW = int(os.environ.get("APPLY_RATE_WINDOW", 60 * 60))  # ...per hour
LOGIN_MAX_FAILURES = int(os.environ.get("LOGIN_MAX_FAILURES", 5))      # failed staff sign-ins...
LOGIN_LOCKOUT_SECONDS = int(os.environ.get("LOGIN_LOCKOUT_SECONDS", 15 * 60))  # ...locks out for 15 minutes

# How long a customer's invoice download link stays valid in their session.
INVOICE_SESSION_KEY = "swiftella_invoices"

# Lender details printed on the invoice. Set real values in the environment.
LENDER_NAME = os.environ.get("LENDER_NAME", "Swiftella Loans")
LENDER_ADDRESS = os.environ.get("LENDER_ADDRESS", "United Kingdom")
LENDER_FCA_NUMBER = os.environ.get("LENDER_FCA_NUMBER", "")
LENDER_EMAIL = os.environ.get("LENDER_EMAIL", "")
LENDER_COMPANY_NUMBER = os.environ.get("LENDER_COMPANY_NUMBER", "")
LENDER_ICO_NUMBER = os.environ.get("LENDER_ICO_NUMBER", "")
# HCSTC lenders must link to at least one FCA-authorised price comparison website.
PRICE_COMPARISON_URL = os.environ.get("PRICE_COMPARISON_URL", "")
PRICE_COMPARISON_NAME = os.environ.get("PRICE_COMPARISON_NAME", "")

# Days to keep applications that never became a loan (submitted, declined,
# withdrawn) before `anonymise_old_applications` removes the personal data.
DATA_RETENTION_DAYS = int(os.environ.get("DATA_RETENTION_DAYS", 365))
# Minimum money left each month after the repayment for an application to
# pass the affordability check (in pence).
AFFORDABILITY_BUFFER_PENCE = int(os.environ.get("AFFORDABILITY_BUFFER_PENCE", 10000))
# Main Swiftella website, used for the header and footer links.
MAIN_SITE_URL = os.environ.get("MAIN_SITE_URL", "https://easy-pay-loan-production.up.railway.app").rstrip("/")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
