"""Intégration de django-axes avec la connexion allauth."""
from django.conf import settings


def identifiant_tentative(request, credentials=None) -> str | None:
    """
    Identifiant utilisé pour compter les échecs de connexion.

    allauth appelle `authenticate(email=…, password=…)` alors que son formulaire envoie le champ
    « login » : on accepte les deux. L'identifiant est mis en minuscules pour que « Awa@… » et
    « awa@… » partagent le même compteur.
    """
    identifiant = None
    if credentials:
        identifiant = credentials.get("email") or credentials.get("login") or credentials.get("username")
    if not identifiant and request is not None:
        donnees = getattr(request, "data", None) or request.POST
        identifiant = donnees.get("login") or donnees.get("email") or donnees.get("username")
    return identifiant.strip().lower() if identifiant else None


def ip_client(request) -> str | None:
    """
    Adresse IP réelle du client, utilisée par axes et par le journal de sécurité.

    Sans proxy (NB_PROXYS_DE_CONFIANCE = 0) : REMOTE_ADDR.
    Derrière N proxys de confiance (Nginx) : la N-ième adresse en partant de la DROITE de
    X-Forwarded-For, c'est-à-dire celle ajoutée par notre propre proxy. Les adresses plus à gauche
    peuvent être inventées par le client et ne sont jamais utilisées.
    """
    nb_proxys = getattr(settings, "NB_PROXYS_DE_CONFIANCE", 0)
    if nb_proxys > 0:
        adresses = [a.strip() for a in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if a.strip()]
        if len(adresses) >= nb_proxys:
            return adresses[-nb_proxys]
    return request.META.get("REMOTE_ADDR")
