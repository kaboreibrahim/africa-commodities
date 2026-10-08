"""Vérifications de sécurité lancées par `python manage.py check --deploy`."""
from django.conf import settings
from django.core.checks import Error, Tags, Warning, register
from django.db import DatabaseError
from django.db.models import Q

BACKEND_AXES = "axes.backends.AxesStandaloneBackend"


@register(Tags.security, deploy=True)
def verifier_mfa_administrateurs(app_configs, **kwargs):
    """comptes.W001 : un admin groupe ou un superutilisateur actif n'a pas de TOTP."""
    from allauth.mfa.models import Authenticator

    from comptes.models import Utilisateur

    try:
        sans_totp = list(
            Utilisateur.objects.filter(is_active=True)
            .filter(Q(is_superuser=True) | Q(role_global=Utilisateur.RoleGlobal.ADMIN_GROUPE))
            .exclude(pk__in=Authenticator.objects.filter(type=Authenticator.Type.TOTP).values("user_id"))
            .values_list("email", flat=True)[:10]
        )
    except DatabaseError:
        return []  # base inaccessible ou non migrée : rien à vérifier ici
    if not sans_totp:
        return []
    return [Warning(
        f"Administrateur(s) actif(s) sans double authentification : {', '.join(sans_totp)}.",
        hint="Chacun doit activer la 2FA (TOTP) depuis /compte/2fa/ avant la mise en production.",
        id="comptes.W001",
    )]


@register(Tags.security, deploy=True)
def verifier_url_admin(app_configs, **kwargs):
    """comptes.W002 : l'admin est encore à l'adresse par défaut, très ciblée par les robots."""
    if settings.ADMIN_URL.strip("/") == "admin":
        return [Warning("L'administration est accessible à l'adresse par défaut « admin/ ».",
                        hint="Choisir une autre valeur pour DJANGO_ADMIN_URL.", id="comptes.W002")]
    return []


@register(Tags.security, deploy=True)
def verifier_backend_axes(app_configs, **kwargs):
    """comptes.E001 : axes doit être le premier backend, sinon le blocage peut être contourné."""
    backends = list(getattr(settings, "AUTHENTICATION_BACKENDS", []))
    if not backends or backends[0] != BACKEND_AXES:
        return [Error("AUTHENTICATION_BACKENDS ne commence pas par le backend d'axes.",
                      hint=f"Placer « {BACKEND_AXES} » en premier.", id="comptes.E001")]
    return []
