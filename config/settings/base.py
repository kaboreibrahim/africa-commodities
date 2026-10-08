"""
Réglages communs à tous les environnements.
Les valeurs sensibles viennent des variables d'environnement (fichier .env en dev).
"""
from datetime import timedelta
from pathlib import Path

import environ
from csp.constants import NONE, SELF

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "comptes.apps.AdminGroupeConfig",  # admin réservé à l'admin groupe
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Applications du projet
    "core",
    "comptes",
    "societes",
    "repartition",
    "operations",
    # Sécurité
    "allauth",
    "allauth.account",
    "allauth.mfa",
    "axes",
    "simple_history",
    "csp",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "csp.middleware.CSPMiddleware",
    "core.middleware.EnTetesSecuriteMiddleware",  # Permissions-Policy
    "comptes.journal.JournalSecuriteMiddleware",  # écrit le journal APRÈS la vue (hors transaction)
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "comptes.middleware.MFAObligatoireMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "axes.middleware.AxesMiddleware",  # doit rester en DERNIER
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
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Base de données : PostgreSQL en production, SQLite possible en dev.
DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True  # chaque requête = une transaction
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)

AUTH_USER_MODEL = "comptes.Utilisateur"

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",  # en premier : bloque avant toute vérification
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
    "comptes.backends.PermissionsAdminGroupe",  # permissions de l'admin pour l'admin groupe
]

# --- allauth : connexion par e-mail, pas d'inscription publique ---
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_ADAPTER = "comptes.adapters.AdaptateurCompte"  # is_open_for_signup -> False
ACCOUNT_EMAIL_VERIFICATION = "none"  # comptes créés par l'admin groupe
ACCOUNT_LOGOUT_ON_PASSWORD_CHANGE = True
ACCOUNT_SESSION_REMEMBER = False
# Le blocage par identifiant est fait par axes ; allauth garde seulement sa limite par IP.
ACCOUNT_RATE_LIMITS = {"login_failed": "10/m/ip"}
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "/"

# --- Historique des modifications (django-simple-history) ---
# Pas de « restaurer cette version » dans l'admin : il contournerait les services d'écriture.
SIMPLE_HISTORY_REVERT_DISABLED = True

MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
MFA_TOTP_ISSUER = "Groupe – Suivi des marges"
# Rôles pour lesquels la 2FA (TOTP) est obligatoire (voir comptes/middleware.py).
MFA_ROLES_OBLIGATOIRES = ["admin_groupe", "responsable"]

# --- axes : 5 échecs -> blocage 30 min, par couple identifiant + IP ---
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=30)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
AXES_USERNAME_FORM_FIELD = "login"  # nom du champ dans le formulaire allauth
# allauth transmet l'identifiant sous la clé « email » : on le lit nous-mêmes.
AXES_USERNAME_CALLABLE = "comptes.axes.identifiant_tentative"
AXES_LOCKOUT_TEMPLATE = "comptes/compte_bloque.html"
# IP du client (axes et journal de sécurité). Derrière Nginx, voir NB_PROXYS_DE_CONFIANCE (prod.py).
AXES_CLIENT_IP_CALLABLE = "comptes.axes.ip_client"
NB_PROXYS_DE_CONFIANCE = env.int("DJANGO_NB_PROXYS_DE_CONFIANCE", default=0)

# --- Sessions : expiration après 2 h d'inactivité ---
SESSION_COOKIE_AGE = 60 * 60 * 2
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True

# Rôle « Saisie » : modification de ses propres lignes du mois en cours et des N mois précédents.
SAISIE_FENETRE_MODIFICATION_MOIS = env.int("SAISIE_FENETRE_MODIFICATION_MOIS", default=1)

# Argon2 en premier : hachage des mots de passe le plus robuste supporté par Django.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Abidjan"
USE_I18N = True
USE_TZ = True
USE_THOUSAND_SEPARATOR = True

# --- En-têtes de sécurité HTTP (valables aussi en dev) ---
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Content Security Policy (django-csp 4) : aucune ressource externe, aucun script ni style inline.
# HTMX et Chart.js seront servis depuis static/vendor/ (étape 3). Jamais d'« unsafe-inline » ni
# d'« unsafe-eval » : si un gabarit a besoin d'un script inline, utiliser un nonce (csp.constants.NONCE).
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": [SELF],
        "script-src": [SELF],
        "style-src": [SELF],
        "img-src": [SELF, "data:"],
        "font-src": [SELF],
        "connect-src": [SELF],
        "object-src": [NONE],
        "base-uri": [SELF],
        "form-action": [SELF],
        "frame-ancestors": [NONE],
    }
}

# Taille maximale des envois (formulaires et fichiers gardés en mémoire).
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# URL de l'admin non standard (configurable).
ADMIN_URL = env("DJANGO_ADMIN_URL", default="gestion-interne/")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "{asctime} {levelname} {name} : {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "axes": {"level": "WARNING"},  # les événements utiles vont dans le journal de sécurité
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "securite": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
