"""
Lectures agrégées (tableaux de bord). Tous les totaux sont calculés PAR LA BASE
(SUM / GROUP BY), jamais en bouclant sur les lignes en Python.
"""
import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, DecimalField, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth

from repartition.models import RegleRepartition
from repartition.services import arrondi_fcfa
from societes.models import Client, DepenseMensuelle, ObjectifMensuel, Societe, premier_du_mois

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


def _totaux_vides() -> dict:
    return {cle: Decimal("0") for cle in CHAMPS_TOTAUX} | {"quantite": 0, "nb_lignes": 0}


def totaux(qs) -> dict:
    """Totaux d'un ensemble de lignes (1 requête)."""
    return qs.aggregate(**_agregats())


def fin_du_mois(mois: date) -> date:
    return date(mois.year + mois.month // 12, mois.month % 12 + 1, 1) - timedelta(days=1)


def objectif_atteint(marge, objectif) -> bool:
    """Règle unique : objectif non nul, marge positive et au moins égale à l'objectif."""
    return bool(objectif) and marge > 0 and marge >= objectif


def _progression(marge, objectif) -> Decimal:
    return (marge / objectif * 100) if objectif else Decimal("0")


# --- Couverture des charges par les dépenses réelles ---------------------------------------------

@dataclass(frozen=True)
class CouvertureCharges:
    """La part « charges » de la marge (25 %) couvre-t-elle les dépenses réelles du mois ?"""

    part_charges: Decimal
    depenses: Decimal
    depenses_saisies: bool
    couvert: bool
    reste_a_couvrir: Decimal
    excedent: Decimal
    taux: Decimal | None  # en %, None si les dépenses ne sont pas saisies (= 0)
    marge_necessaire: Decimal
    marge_restante: Decimal
    unites_restantes: int


def _pct_charges_du_mois(mois: date) -> Decimal | None:
    try:
        return RegleRepartition.objects.en_vigueur(mois).pct_charges
    except RegleRepartition.DoesNotExist:
        return None


def _depenses_du_mois(societe, mois: date) -> Decimal:
    montant = DepenseMensuelle.objects.filter(societe=societe, mois=mois).values_list("montant", flat=True).first()
    return montant or Decimal("0")


def taux_couverture(part_charges, depenses) -> Decimal | None:
    """Part charges ÷ dépenses × 100, à 1 décimale ; None si les dépenses ne sont pas saisies (= 0)."""
    depenses = Decimal(depenses or 0)
    if depenses <= 0:
        return None
    return (Decimal(part_charges or 0) / depenses * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def couverture_charges(societe, mois: date, *, marge, part_charges, quantite,
                       depenses=None, pct_charges=None) -> CouvertureCharges:
    """
    SEUL endroit où la couverture des charges est calculée (les vues, gabarits et JS ne recalculent rien).

    - marge nécessaire = dépenses ÷ (pct_charges ÷ 100), avec pct_charges de la règle en vigueur
      le 1er du mois ;
    - unités restantes = (marge nécessaire − marge) ÷ marge moyenne par unité du mois (ou marge par défaut).

    `depenses` et `pct_charges` peuvent être fournis s'ils ont déjà été chargés (sinon : 1 requête chacun).
    """
    mois = premier_du_mois(mois)
    marge, part_charges = Decimal(marge or 0), Decimal(part_charges or 0)
    depenses = Decimal(_depenses_du_mois(societe, mois) if depenses is None else depenses)
    if pct_charges is None:
        pct_charges = _pct_charges_du_mois(mois)

    saisies = depenses > 0
    couvert = saisies and part_charges >= depenses
    reste = max(Decimal("0"), depenses - part_charges)
    excedent = max(Decimal("0"), part_charges - depenses) if saisies else Decimal("0")
    taux = taux_couverture(part_charges, depenses)

    marge_necessaire = arrondi_fcfa(depenses * 100 / Decimal(pct_charges)) if saisies and pct_charges else Decimal("0")
    marge_restante = max(Decimal("0"), marge_necessaire - marge)
    unites = 0
    if marge_restante > 0:
        moyenne = (marge / quantite) if quantite else Decimal(societe.marge_defaut or 0)
        unites = math.ceil(marge_restante / moyenne) if moyenne > 0 else 0  # arrondi au supérieur

    return CouvertureCharges(
        part_charges=arrondi_fcfa(part_charges), depenses=arrondi_fcfa(depenses), depenses_saisies=saisies,
        couvert=couvert, reste_a_couvrir=arrondi_fcfa(reste), excedent=arrondi_fcfa(excedent), taux=taux,
        marge_necessaire=marge_necessaire, marge_restante=arrondi_fcfa(marge_restante), unites_restantes=unites,
    )


# --- Société : un mois -----------------------------------------------------------------------------

def tableau_de_bord_mois(societe: Societe, mois: date) -> dict:
    """
    Indicateurs d'une société pour un mois : totaux, objectif, progression, dépenses et couverture
    des charges (4 requêtes : totaux, objectif, dépenses, règle du mois).
    """
    mois = premier_du_mois(mois)
    t = totaux(Ligne.objects.filter(societe=societe).du_mois(mois))
    objectif = societe.objectif_pour(mois)
    t["objectif"] = objectif
    t["progression"] = _progression(t["marge"], objectif)
    t["objectif_atteint"] = objectif_atteint(t["marge"], objectif)
    t["depenses"] = _depenses_du_mois(societe, mois)
    t["couverture"] = couverture_charges(societe, mois, marge=t["marge"], part_charges=t["charges"],
                                         quantite=t["quantite"], depenses=t["depenses"])
    return t


def marges_par_mois(societe: Societe | None, annee: int) -> dict[date, Decimal]:
    """Marge par mois sur une année, pour une société ou pour tout le groupe (1 requête)."""
    qs = Ligne.objects.de_l_annee(annee)
    if societe is not None:
        qs = qs.filter(societe=societe)
    rows = qs.annotate(m=TruncMonth("date")).values("m").annotate(marge=Sum("marge_totale")).order_by("m")
    return {r["m"]: r["marge"] for r in rows}


def marges_par_mois_par_societe(annee: int, societes=None) -> dict[int, dict[date, Decimal]]:
    """{id société: {mois: marge}} sur une année, toutes sociétés en 1 requête (Vue Groupe)."""
    qs = Ligne.objects.de_l_annee(annee)
    if societes is not None:
        qs = qs.filter(societe__in=societes)
    resultat: dict[int, dict[date, Decimal]] = {}
    for r in (qs.annotate(m=TruncMonth("date")).values("societe", "m")
              .annotate(marge=Sum("marge_totale")).order_by("societe", "m")):
        resultat.setdefault(r["societe"], {})[r["m"]] = r["marge"]
    return resultat


def marges_par_projet(societe: Societe, debut: date, fin: date) -> list[dict]:
    return list(
        Ligne.objects.filter(societe=societe, date__range=(debut, fin))
        .values("projet").annotate(marge=Sum("marge_totale"), quantite=Sum("quantite"))
        .order_by("-marge")
    )


def charges_vs_depenses_par_mois(societe: Societe, annee: int) -> list[dict]:
    """12 entrées {mois, part_charges, depenses} pour le graphique « charges réservées / dépenses » (2 requêtes)."""
    charges = dict(
        Ligne.objects.filter(societe=societe).de_l_annee(annee).annotate(m=TruncMonth("date"))
        .values("m").annotate(part=Sum("part_charges")).order_by("m").values_list("m", "part")
    )
    depenses = dict(DepenseMensuelle.objects.filter(societe=societe, mois__year=annee).values_list("mois", "montant"))
    return [{"mois": m, "part_charges": charges.get(m) or Decimal("0"), "depenses": depenses.get(m) or Decimal("0")}
            for m in (date(annee, n, 1) for n in range(1, 13))]


# --- Groupe ------------------------------------------------------------------------------------------

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


def synthese_groupe(mois: date, societes=None) -> list[dict]:
    """
    Une ligne par société active pour le mois : totaux, objectif, progression, dépenses, couverture.
    Nombre de requêtes constant (5), quel que soit le nombre de sociétés : totaux, sociétés,
    objectifs, dépenses, règle du mois. `societes` peut être fourni déjà chargé (1 requête de moins).
    """
    mois = premier_du_mois(mois)
    societes = list(Societe.objects.filter(actif=True) if societes is None else societes)
    par_societe = {
        r["societe"]: r
        for r in (Ligne.objects.du_mois(mois).filter(societe__in=[s.pk for s in societes])
                  .values("societe").annotate(**_agregats()).order_by())
    }
    objectifs = objectifs_resolus(societes, [mois])
    depenses = dict(DepenseMensuelle.objects.filter(mois=mois, societe__in=societes).values_list("societe", "montant"))
    pct_charges = _pct_charges_du_mois(mois)
    resultat = []
    for s in societes:
        t = {**_totaux_vides(), **par_societe.get(s.pk, {})}
        t.pop("societe", None)
        objectif = objectifs[(s.pk, mois)]
        t.update(societe=s, objectif=objectif, progression=_progression(t["marge"], objectif),
                 objectif_atteint=objectif_atteint(t["marge"], objectif),
                 depenses=depenses.get(s.pk, Decimal("0")))
        t["couverture"] = couverture_charges(s, mois, marge=t["marge"], part_charges=t["charges"],
                                             quantite=t["quantite"], depenses=t["depenses"], pct_charges=pct_charges)
        resultat.append(t)
    return resultat


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


# --- Tableau de bord société complet ------------------------------------------------------------------

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
    return math.ceil(reste / moyenne)  # arrondi au supérieur


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
    Toutes les données du tableau de bord d'une société pour un mois, en 5 requêtes :
    1. totaux de chacun des 12 mois de l'année (le mois affiché en fait partie) ;
    2. objectifs de l'année ; 3. dépenses de l'année ; 4. règle du mois ; 5. marge par projet du mois.
    Mêmes résultats que tableau_de_bord_mois + marges_par_mois + charges_vs_depenses_par_mois.
    """
    mois = premier_du_mois(mois)
    liste_mois = [date(mois.year, n, 1) for n in range(1, 13)]
    par_mois = {r["m"]: r for r in (Ligne.objects.filter(societe=societe).de_l_annee(mois.year)
                                    .annotate(m=TruncMonth("date")).values("m").annotate(**_agregats()).order_by("m"))}
    objectifs = objectifs_resolus([societe], liste_mois)
    depenses = dict(DepenseMensuelle.objects.filter(societe=societe, mois__year=mois.year).values_list("mois", "montant"))
    pct_charges = _pct_charges_du_mois(mois)

    ind = {**_totaux_vides(), **{k: v for k, v in par_mois.get(mois, {}).items() if k != "m"}}
    marge, charges, quantite = ind["marge"], ind["charges"], ind["quantite"]
    objectif = objectifs[(societe.pk, mois)]
    ind.update(
        objectif=objectif, progression=_progression(marge, objectif), objectif_atteint=objectif_atteint(marge, objectif),
        marge_moyenne=(marge / quantite) if quantite else societe.marge_defaut,
        unites_restantes=unites_restantes(marge, objectif, quantite, societe.marge_defaut),
        # Parts réellement appliquées ce mois-ci (None s'il n'y a pas encore de marge).
        pct_charges=(charges / marge * 100) if marge else None,
        pct_africa_commodities=(ind["africa_commodities"] / (marge - charges) * 100) if marge > charges else None,
        risques_et_provision=ind["risques"] + ind["provision"],
        depenses=depenses.get(mois, Decimal("0")),
    )
    ind["couverture"] = couverture_charges(societe, mois, marge=marge, part_charges=charges, quantite=quantite,
                                           depenses=ind["depenses"], pct_charges=pct_charges)

    annee = []
    for m in liste_mois:
        ligne = par_mois.get(m, {})
        marge_m = ligne.get("marge") or Decimal("0")
        part_m, depenses_m = ligne.get("charges") or Decimal("0"), depenses.get(m, Decimal("0"))
        annee.append({"mois": m, "marge": marge_m, "objectif": objectifs[(societe.pk, m)],
                      "objectif_atteint": objectif_atteint(marge_m, objectifs[(societe.pk, m)]),
                      "part_charges": part_m, "depenses": depenses_m, "selectionne": m == mois,
                      # écart (reste / excédent) seulement : la règle du mois affiché suffit, aucune requête en plus
                      "couverture": couverture_charges(societe, m, marge=marge_m, part_charges=part_m,
                                                       quantite=ligne.get("quantite") or 0, depenses=depenses_m,
                                                       pct_charges=pct_charges)})

    projets = regrouper_projets(marges_par_projet(societe, mois, fin_du_mois(mois)))
    return {"indicateurs": ind, "annee": annee, "projets": projets}


def etat_du_mois(societe: Societe, mois: date) -> dict:
    """État d'une société pour un mois : objectif atteint ? charges couvertes ? (4 requêtes)."""
    t = tableau_de_bord_mois(societe, mois)
    return {"marge": t["marge"], "objectif_atteint": t["objectif_atteint"], "charges_couvertes": t["couverture"].couvert}


# --- Liste des lignes ----------------------------------------------------------------------------

PERIODES = {"mois": "Mois de suivi", "annee": "Toute l'année", "tout": "Tout"}


def lignes_filtrees(societe: Societe, mois: date, periode: str = "mois", recherche: str = "",
                    client_id: int | None = None, projet: str = ""):
    """
    Lignes actives d'une société selon les filtres de la liste (queryset, aucune requête exécutée) :
    période (mois de suivi / année / tout), recherche texte, client, projet. Triées par date.
    """
    qs = Ligne.objects.filter(societe=societe).select_related("client")
    mois = premier_du_mois(mois)
    if periode == "mois":
        qs = qs.du_mois(mois)
    elif periode == "annee":
        qs = qs.de_l_annee(mois.year)
    recherche = (recherche or "").strip()
    if recherche:
        qs = qs.filter(Q(reference__icontains=recherche) | Q(projet__icontains=recherche)
                       | Q(client__nom__icontains=recherche) | Q(observation__icontains=recherche)
                       | Q(extra__icontains=recherche))
    if client_id:
        qs = qs.filter(client_id=client_id)
    if projet:
        qs = qs.filter(projet=projet)
    return qs.order_by("date", "id")


def projets_de_la_societe(societe: Societe) -> list[str]:
    """N° de projet déjà utilisés par la société (filtre de la liste, 1 requête)."""
    return list(Ligne.objects.filter(societe=societe).exclude(projet="").order_by("projet")
                .values_list("projet", flat=True).distinct())


def clients_avec_nb_lignes(societe: Societe):
    """Clients actifs de la société avec `nb_lignes` (lignes actives qui les utilisent), en 1 requête."""
    return (Client.objects.filter(societe=societe)
            .annotate(nb_lignes=Count("lignes", filter=Q(lignes__supprime_le__isnull=True)))
            .order_by("nom"))


def totaux_synthese(synthese: list[dict]) -> dict:
    """
    Ligne TOTAL GROUPE de la synthèse : sommes des montants, progression globale,
    sociétés à l'objectif et sociétés aux charges couvertes, taux de couverture global.
    """
    total = _totaux_vides()
    for cle in [*CHAMPS_TOTAUX, "quantite", "nb_lignes"]:
        total[cle] = sum((r[cle] for r in synthese), total[cle])
    total["objectif"] = sum((r["objectif"] for r in synthese), Decimal("0"))
    total["depenses"] = sum((r["depenses"] for r in synthese), Decimal("0"))
    total["progression"] = _progression(total["marge"], total["objectif"])
    total["a_l_objectif"] = [r["societe"] for r in synthese if r["objectif_atteint"]]
    total["charges_couvertes"] = [r["societe"] for r in synthese if r["couverture"].couvert]
    # Couverture globale : seulement les sociétés qui ont saisi leurs dépenses du mois (sinon leur part
    # charges gonflerait artificiellement le taux du groupe).
    avec_depenses = [r for r in synthese if r["couverture"].depenses_saisies]
    total["nb_depenses_saisies"] = len(avec_depenses)
    total["charges_avec_depenses"] = sum((r["charges"] for r in avec_depenses), Decimal("0"))
    total["taux_couverture"] = taux_couverture(total["charges_avec_depenses"], total["depenses"])
    total["ecart_charges"] = total["charges_avec_depenses"] - total["depenses"]  # + excédent / − reste à couvrir
    total["risques_et_provision"] = total["risques"] + total["provision"]
    return total
