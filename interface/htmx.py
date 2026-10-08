"""Petits outils HTMX : détection des requêtes et évènements envoyés au navigateur (HX-Trigger)."""
import json

from django.core.serializers.json import DjangoJSONEncoder

from core.templatetags.format_fr import mois_long


def est_htmx(request) -> bool:
    return request.headers.get("HX-Request") == "true"


def declencher(reponse, **evenements):
    """Ajoute des évènements à l'en-tête HX-Trigger (fusionnés avec ceux déjà présents)."""
    existants = json.loads(reponse.headers.get("HX-Trigger", "{}") or "{}")
    existants.update(evenements)
    # JSON en ASCII (\uXXXX) : un en-tête HTTP non ASCII serait encodé en MIME et illisible par HTMX.
    reponse["HX-Trigger"] = json.dumps(existants, cls=DjangoJSONEncoder, ensure_ascii=True)
    return reponse


def toast(message: str, niveau: str = "success", action: dict | None = None) -> dict:
    """Détail de l'évènement « toast » (affiché par app.js)."""
    detail = {"message": message, "niveau": niveau}
    if action:
        detail["action"] = action
    return detail


def evenements_franchissement(seuils: set[str], societe, mois) -> dict:
    """
    Évènements HX-Trigger quand un enregistrement fait franchir un seuil :
    « objectifAtteint » (confettis) et « chargesCouvertes » (toast seulement, pas de confettis).
    """
    evenements = {}
    if "objectif_atteint" in seuils:
        evenements["objectifAtteint"] = {"societe": societe.code.upper(), "mois": mois_long(mois),
                                         "couleurs": [societe.couleur_principale, societe.couleur_accent]}
    if "charges_couvertes" in seuils:
        evenements["chargesCouvertes"] = {"societe": societe.code.upper(), "mois": mois_long(mois)}
    return evenements
