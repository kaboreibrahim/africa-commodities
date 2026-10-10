"""
Réglages de production. Vérifier avec : python manage.py check --deploy --settings=config.settings.prod
"""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import DATABASES, MIDDLEWARE, SECRET_KEY, env

DEBUG = True

# --- Garde-fous : refuser de démarrer avec une configuration dangereuse ---
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY doit faire au moins 50 caractères en production.")
if not (env("DATABASE_URL", default="") or env("DB_NAME", default="")):
    raise ImproperlyConfigured("Base de données obligatoire en production : DB_NAME/DB_USER/DB_PASSWORD (MySQL) ou DATABASE_URL (PostgreSQL).")
if "sqlite" in DATABASES["default"]["ENGINE"]:
    raise ImproperlyConfigured("SQLite n'est pas autorisé en production : utiliser MySQL ou PostgreSQL.")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS ne doit pas être vide en production.")

# HTTPS partout
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Cookies
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])
MFA_TRUST_COOKIE_SECURE = True

# Derrière Nginx (1 proxy de confiance) : axes et le journal lisent la vraie IP du client dans
# X-Forwarded-For, en prenant l'adresse ajoutée par Nginx (la plus à droite). Voir comptes/axes.py.
# Nginx : proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
NB_PROXYS_DE_CONFIANCE = env.int("DJANGO_NB_PROXYS_DE_CONFIANCE", default=1)

# Fichiers statiques servis par l'application elle-même (WhiteNoise) : fonctionne sur cPanel sans règle Apache.
# Les noms de fichiers sont versionnés (empreinte) : plus de CSS/JS périmé en cache après une mise à jour.
# Prérequis au déploiement : python manage.py collectstatic --noinput
MIDDLEWARE = [MIDDLEWARE[0], "whitenoise.middleware.WhiteNoiseMiddleware", *MIDDLEWARE[1:]]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Fichiers téléversés (logos des sociétés) : sur cPanel, dossier public servi par Apache (voir DEPLOIEMENT_CPANEL.md).
MEDIA_ROOT = env("DJANGO_MEDIA_ROOT", default=str(BASE_DIR / "media"))
MEDIA_URL = env("DJANGO_MEDIA_URL", default="/media/")
