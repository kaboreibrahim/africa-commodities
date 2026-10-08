"""
Lectures agrégées (tableaux de bord). Tous les totaux sont calculés PAR LA BASE
(SUM / GROUP BY), jamais en bouclant sur les lignes en Python.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth

from societes.models import ObjectifMensuel, Societe, premier_du_mois

from .models import Ligne

ZERO = Value(Decimal("0"), output_field=DecimalField(max_digits=16, decimal_places=0))

CHAMPS_TOTAUX = {
    "marge": "marge_totale",
    "charges": "part_charges",
    "africa_commodities": "part_africa_commodities",
    "risques": "part_risques",
    "provision": "part_provision",
    "comptes": "part_comptes",
}


def _agregats():
    agg = {cle: Coalesce(Sum(champ), ZERO) for cle, champ in CHAMPS_TOTAUX.items()}
    agg["quantite"] = Coalesce(Sum("quantite"), 0)
    agg["nb_lignes"] = Count("id")
    return agg


def totaux(qs) -> dict:
    """Totaux d'un ensemble de lignes (1 requête)."""
    return qs.aggregate(**_agregats())


def tableau_de_bord_mois(societe: Societe, mois: date) -> dict:
    """Indicateurs d'une société pour un mois : totaux, objectif, progression."""
    mois = premier_du_mois(mois)
    t = totaux(Ligne.objects.filter(societe=societe).du_mois(mois))
    objectif = societe.objectif_pour(mois)
    t["objectif"] = objectif
    t["progression"] = (t["marge"] / objectif * 100) if objectif else Decimal("0")
    t["objectif_atteint"] = bool(objectif) and t["marge"] >= objectif and t["marge"] > 0
    return t


def marges_par_mois(societe: Societe | None, annee: int) -> dict[date, Decimal]:
    """Marge par mois sur une année, pour une société ou pour tout le groupe (1 requête)."""
    qs = Ligne.objects.de_l_annee(annee)
    if societe is not None:
        qs = qs.filter(societe=societe)
    rows = qs.annotate(m=TruncMonth("date")).values("m").annotate(marge=Sum("marge_totale")).order_by("m")
    return {r["m"]: r["marge"] for r in rows}


def marges_par_projet(societe: Societe, debut: date, fin: date) -> list[dict]:
    return list(
        Ligne.objects.filter(societe=societe, date__range=(debut, fin))
        .values("projet").annotate(marge=Sum("marge_totale"), quantite=Sum("quantite"))
        .order_by("-marge")
    )


def synthese_groupe(mois: date) -> list[dict]:
    """
    Une ligne par société active pour le mois : totaux + objectif + progression.
    1 requête pour les totaux de toutes les sociétés + 1 par société pour l'objectif.
    """
    mois = premier_du_mois(mois)
    par_societe = {
        r["societe"]: r
        for r in Ligne.objects.du_mois(mois).values("societe").annotate(**_agregats()).order_by()
    }
    vide = {cle: Decimal("0") for cle in CHAMPS_TOTAUX} | {"quantite": 0, "nb_lignes": 0}
    resultat = []
    for s in Societe.objects.filter(actif=True):
        t = {**vide, **par_societe.get(s.pk, {})}
        t.pop("societe", None)
        objectif = s.objectif_pour(mois)
        t.update(societe=s, objectif=objectif,
                 progression=(t["marge"] / objectif * 100) if objectif else Decimal("0"),
                 objectif_atteint=bool(objectif) and t["marge"] >= objectif and t["marge"] > 0)
        resultat.append(t)
    return resultat


def objectif_atteint(marge, objectif) -> bool:
    """Règle unique : objectif non nul, marge positive et au moins égale à l'objectif."""
    return bool(objectif) and marge > 0 and marge >= objectif


def avec_etat_du_mois(societes, mois: date):
    """
    Ajoute à un queryset de sociétés `marge_mois` et `objectif_mois` (1 seule requête, sous-requêtes).
    Utilisé pour les onglets (✔ quand l'objectif du mois est atteint).
    """
    mois = premier_du_mois(mois)
    marge = (Ligne.objects.filter(societe=OuterRef("pk")).du_mois(mois).order_by()
             .values("societe").annotate(total=Sum("marge_totale")).values("total"))
    objectif = (ObjectifMensuel.objects.filter(societe=OuterRef("pk"), mois__lte=mois)
                .order_by("-mois").values("montant")[:1])
    return societes.annotate(
        marge_mois=Coalesce(Subquery(marge, output_field=ZERO.output_field), ZERO),
        objectif_mois=Coalesce(Subquery(objectif, output_field=ZERO.output_field), F("objectif_defaut")),
    )


def objectifs_resolus(societes, liste_mois) -> dict[tuple[int, date], Decimal]:
    """
    Objectif de chaque (société, mois) en 1 seule requête : valeur du mois, sinon celle du
    dernier mois renseigné avant, sinon l'objectif par défaut (même règle que Societe.objectif_pour).
    """
    societes = list(societes)
    liste_mois = [premier_du_mois(m) for m in liste_mois]
    if not societes or not liste_mois:
        return {}
    saisis: dict[int, list] = {s.pk: [] for s in societes}
    for societe_id, mois, montant in (ObjectifMensuel.objects
                                      .filter(societe__in=societes, mois__lte=max(liste_mois))
                                      .order_by("societe", "mois").values_list("societe", "mois", "montant")):
        saisis[societe_id].append((mois, montant))
    resultat = {}
    for s in societes:
        for mois in liste_mois:
            precedents = [montant for m, montant in saisis[s.pk] if m <= mois]
            resultat[(s.pk, mois)] = precedents[-1] if precedents else s.objectif_defaut
    return resultat


def unites_restantes(marge, objectif, quantite, marge_defaut) -> int:
    """
    Nombre approximatif d'unités (conteneurs, livraisons…) encore nécessaires pour atteindre
    l'objectif, à la marge moyenne du mois (ou à la marge par défaut s'il n'y a encore rien).
    """
    if objectif_atteint(marge, objectif) or not objectif:
        return 0
    moyenne = (Decimal(marge) / quantite) if quantite else Decimal(marge_defaut or 0)
    if moyenne <= 0:
        return 0
    reste = Decimal(objectif) - Decimal(marge)
    return int(-(-reste // moyenne))  # arrondi au supérieur


def regrouper_projets(projets: list[dict], maximum: int = 7) -> list[dict]:
    """Les `maximum` premiers projets par marge, le reste cumulé dans « Autres projets »."""
    projets = [{**p, "projet": p["projet"] or "(sans projet)"} for p in projets]
    if len(projets) <= maximum + 1:
        return projets
    autres = projets[maximum:]
    return projets[:maximum] + [{
        "projet": "Autres projets",
        "marge": sum((p["marge"] for p in autres), Decimal("0")),
        "quantite": sum(p["quantite"] for p in autres),
    }]


def tableau_de_bord_societe(societe: Societe, mois: date) -> dict:
    """
    Toutes les données du tableau de bord d'une société pour un mois (5 requêtes) :
    indicateurs du mois, marge et objectif des 12 mois de l'année, marge par projet du mois.
    """
    mois = premier_du_mois(mois)
    indicateurs = tableau_de_bord_mois(societe, mois)
    marge, charges = indicateurs["marge"], indicateurs["charges"]
    quantite = indicateurs["quantite"]
    indicateurs.update(
        marge_moyenne=(marge / quantite) if quantite else societe.marge_defaut,
        unites_restantes=unites_restantes(marge, indicateurs["objectif"], quantite, societe.marge_defaut),
        # Parts réellement appliquées ce mois-ci (None s'il n'y a pas encore de marge).
        pct_charges=(charges / marge * 100) if marge else None,
        pct_africa_commodities=(indicateurs["africa_commodities"] / (marge - charges) * 100) if marge > charges else None,
        risques_et_provision=indicateurs["risques"] + indicateurs["provision"],
    )

    liste_mois = [date(mois.year, m, 1) for m in range(1, 13)]
    marges = marges_par_mois(societe, mois.year)
    objectifs = objectifs_resolus([societe], liste_mois)
    annee = []
    for m in liste_mois:
        marge_m = marges.get(m) or Decimal("0")
        objectif_m = objectifs[(societe.pk, m)]
        annee.append({"mois": m, "marge": marge_m, "objectif": objectif_m,
                      "objectif_atteint": objectif_atteint(marge_m, objectif_m), "selectionne": m == mois})

    fin_du_mois = date(mois.year + mois.month // 12, mois.month % 12 + 1, 1) - timedelta(days=1)
    projets = regrouper_projets(marges_par_projet(societe, mois, fin_du_mois))
    return {"indicateurs": indicateurs, "annee": annee, "projets": projets}
