from django.apps import AppConfig


class InterfaceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "interface"
    verbose_name = "interface web"

    def ready(self):
        from . import signals  # noqa: F401  (invalidation du cache de la règle en vigueur)
