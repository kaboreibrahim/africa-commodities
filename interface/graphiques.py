"""
Mise en forme des données des graphiques (transmises au JavaScript par `json_script`).
Aucun calcul métier ici : les montants viennent des sélecteurs, on ne fait que les présenter.
"""
from decimal import Decimal

from core.templatetags.format_fr import fcfa_court, mois_court, mois_long, pct

from .theme import COULEURS_POSTES

POSTES = [
    ("charges", "Charges"),
    ("africa_commodities", "Africa Commodities"),
    ("risques", "Risques"),
    ("provision", "Provision"),
    ("comptes", "Comptes"),
]


def _entier(valeur) -> int:
    return int(Decimal(valeur or 0))


def postes(indicateurs: dict, code: str) -> list[dict]:
    """Les 5 postes de répartition, avec leur part (%) de la marge : légende et tableau équivalent."""
    marge = indicateurs["marge"] or 0
    return [{
        "cle": cle,
        "nom": f"Comptes {code.upper()}" if cle == "comptes" else nom,
        "valeur": indicateurs[cle],
        "part": (indicateurs[cle] / marge * 100) if marge else Decimal("0"),
        "couleur": COULEURS_POSTES[cle],
    } for cle, nom in POSTES]


def progression(indicateurs: dict) -> list[dict]:
    """Réalisé / Reste à faire / Dépassement (anneau « Progression vers l'objectif »)."""
    marge, objectif = indicateurs["marge"], indicateurs["objectif"]
    parts = [
        {"cle": "realise", "nom": "Réalisé", "valeur": min(marge, objectif)},
        {"cle": "reste", "nom": "Reste à faire", "valeur": max(Decimal("0"), objectif - marge)},
    ]
    if marge > objectif:
        parts.append({"cle": "depassement", "nom": "Dépassement", "valeur": marge - objectif})
    total = sum(p["valeur"] for p in parts) or 1
    for p in parts:
        p["part"] = p["valeur"] / total * 100
    return parts


def donnees_tableau_de_bord(donnees: dict, societe) -> dict:
    """Données JSON des 4 graphiques du tableau de bord société."""
    ind = donnees["indicateurs"]
    return {
        "repartition": {
            "centre": fcfa_court(ind["marge"]) or "0", "sousTitre": "marge du mois",
            "parts": [{"cle": p["cle"], "nom": p["nom"], "valeur": _entier(p["valeur"]), "couleur": p["couleur"]}
                      for p in postes(ind, societe.code)],
        },
        "objectif": {
            "centre": pct(ind["progression"]), "sousTitre": "de l'objectif",
            "parts": [{"cle": p["cle"], "nom": p["nom"], "valeur": _entier(p["valeur"])} for p in progression(ind)],
        },
        "mois": {
            "etiquettes": [mois_court(m["mois"]).capitalize() for m in donnees["annee"]],
            "titres": [mois_long(m["mois"]) for m in donnees["annee"]],
            "marges": [_entier(m["marge"]) for m in donnees["annee"]],
            "objectifs": [_entier(m["objectif"]) for m in donnees["annee"]],
            "atteints": [m["objectif_atteint"] for m in donnees["annee"]],
            "selection": next((i for i, m in enumerate(donnees["annee"]) if m["selectionne"]), None),
        },
        "chargesDepenses": {
            "etiquettes": [mois_court(m["mois"]).capitalize() for m in donnees["annee"]],
            "titres": [mois_long(m["mois"]) for m in donnees["annee"]],
            "parts": [_entier(m["part_charges"]) for m in donnees["annee"]],
            "depenses": [_entier(m["depenses"]) for m in donnees["annee"]],
            # Écart déjà calculé par couverture_charges : positif = excédent, négatif = reste à couvrir.
            "ecarts": [_entier(m["couverture"].excedent - m["couverture"].reste_a_couvrir)
                       if m["couverture"].depenses_saisies else None for m in donnees["annee"]],
            "selection": next((i for i, m in enumerate(donnees["annee"]) if m["selectionne"]), None),
        },
        "projets": {
            "etiquettes": [p["projet"] for p in donnees["projets"]],
            "marges": [_entier(p["marge"]) for p in donnees["projets"]],
            "quantites": [p["quantite"] for p in donnees["projets"]],
            "unite": societe.unite,
        },
    }
