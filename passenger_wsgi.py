"""
Point d'entrée Passenger pour cPanel « Setup Python App ».
Application startup file : passenger_wsgi.py - Application Entry point : application.

Les réglages sont ceux de production (config.settings.prod). Les valeurs sensibles (clé secrète, base MySQL, domaines)
viennent du fichier .env placé à côté de ce fichier : il n'est jamais dans Git.
"""
import os
import sys
from pathlib import Path

# Racine du projet (là où se trouve ce fichier) : Django doit y trouver les paquets config, comptes, interface…
PROJ_DIR = Path(__file__).resolve().parent
if str(PROJ_DIR) not in sys.path:
    sys.path.insert(0, str(PROJ_DIR))

# Le .env peut surcharger le module de réglages (rarement utile) ; sinon : production.
try:
    import environ

    environ.Env.read_env(PROJ_DIR / ".env")
except ImportError:
    pass
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
