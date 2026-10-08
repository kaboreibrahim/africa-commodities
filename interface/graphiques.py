"""
Mise en forme des données des graphiques (transmises au JavaScript par `json_script`).
Aucun calcul métier ici : les montants viennent des sélecteurs, on ne fait que les présenter.
"""
from datetime import date
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


def nom_court(societe) -> str:
    """Libellé court d'une société dans les graphiques (code, sauf noms courts lisibles)."""
    return {"alon": "ALON Prop.", "mlp": "Mon Livreur Pro"}.get(societe.code, societe.code.upper())


def donnees_groupe(synthese: list[dict], total: dict, marges_annee: dict, mois) -> dict:
    """Données JSON des graphiques de la Vue Groupe."""
    liste_mois = [date(mois.year, n, 1) for n in range(1, 13)]
    total_ac = total["africa_commodities"] or 0
    return {
        "societes": {
            "etiquettes": [nom_court(r["societe"]) + (" ✔" if r["objectif_atteint"] else "") for r in synthese],
            "noms": [r["societe"].nom for r in synthese],
            "marges": [_entier(r["marge"]) for r in synthese],
            "objectifs": [_entier(r["objectif"]) for r in synthese],
            "progressions": [float(r["progression"]) for r in synthese],
            "couleurs": [r["societe"].couleur_serie for r in synthese],
        },
        "africaCommodities": {
            "centre": fcfa_court(total_ac) or "0", "sousTitre": "Africa Com.",
            "parts": [{"nom": r["societe"].nom, "code": r["societe"].code, "valeur": _entier(r["africa_commodities"]),
                       "part": float(r["africa_commodities"] / total_ac * 100) if total_ac else 0.0,
                       "couleur": r["societe"].couleur_serie} for r in synthese],
        },
        "charges": {
            "etiquettes": [nom_court(r["societe"]) + (" ✔" if r["couverture"].couvert else
                                                      " ⚠" if r["couverture"].depenses_saisies else "")
                           for r in synthese],
            "noms": [r["societe"].nom for r in synthese],
            "parts": [_entier(r["charges"]) for r in synthese],
            "depenses": [_entier(r["depenses"]) for r in synthese],
            "ecarts": [_entier(r["couverture"].excedent - r["couverture"].reste_a_couvrir)
                       if r["couverture"].depenses_saisies else None for r in synthese],
        },
        "mois": {
            "etiquettes": [mois_court(m).capitalize() for m in liste_mois],
            "titres": [mois_long(m) for m in liste_mois],
            "selection": mois.month - 1,
            "series": [{"nom": r["societe"].nom, "couleur": r["societe"].couleur_serie,
                        "marges": [_entier(marges_annee.get(r["societe"].pk, {}).get(m)) for m in liste_mois]}
                       for r in synthese],
            # Tableau équivalent : une ligne par mois, une colonne par société.
            "tableau": [{"titre": mois_long(m), "marges": [_entier(marges_annee.get(r["societe"].pk, {}).get(m))
                                                           for r in synthese]} for m in liste_mois],
        },
    }
