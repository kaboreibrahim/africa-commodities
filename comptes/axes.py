"""Intégration de django-axes avec la connexion allauth."""


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
