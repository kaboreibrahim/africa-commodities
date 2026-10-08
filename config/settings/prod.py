"""
Réglages de production. Vérifier avec : python manage.py check --deploy --settings=config.settings.prod
(Le durcissement complet — 2FA, axes, CSP, audit — arrive à l'étape 2.)
"""
from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

# HTTPS partout
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# Cookies
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

X_FRAME_OPTIONS = "DENY"

# axes derrière Nginx (1 proxy de confiance) : la vraie IP du client est lue dans X-Forwarded-For.
# Nginx doit écraser l'en-tête : proxy_set_header X-Forwarded-For $remote_addr;
AXES_IPWARE_PROXY_COUNT = env.int("AXES_PROXY_COUNT", default=1)
AXES_IPWARE_META_PRECEDENCE_ORDER = ["HTTP_X_FORWARDED_FOR", "REMOTE_ADDR"]
