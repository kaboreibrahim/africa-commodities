from django.apps import AppConfig
from django.contrib.admin import apps as admin_apps


class ComptesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "comptes"
    verbose_name = "comptes et sécurité"


class AdminGroupeConfig(admin_apps.AdminConfig):
    """Remplace le site d'administration par défaut par `SiteAdministration`."""

    default = False  # à déclarer explicitement dans INSTALLED_APPS
    default_site = "comptes.admin_site.SiteAdministration"
