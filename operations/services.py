"""
Écritures sur les lignes. Toute création, modification, suppression ou restauration de ligne
passe par ces fonctions : elles vérifient le droit (`comptes.acces`), valident puis enregistrent.
Un refus lève `PermissionDenied` et il est journalisé.
"""
from django.db import transaction

from comptes import acces

from .models import Ligne
from .selectors import objectif_atteint

# Champs qu'un utilisateur peut renseigner ; la société, la répartition et la traçabilité sont exclues.
CHAMPS_SAISIE = frozenset({"date", "reference", "projet", "client", "client_id", "extra", "quantite",
                           "marge_unitaire", "observation"})

# Champs calculés : contrôlés par le calcul lui-même et par la contrainte en base.
CHAMPS_CALCULES = ["regle", "marge_totale", "part_charges", "part_africa_commodities", "part_risques",
                   "part_provision", "part_comptes"]


def _verifier_champs(donnees: dict) -> None:
    inconnus = set(donnees) - CHAMPS_SAISIE
    if inconnus:
        raise ValueError(f"Champ(s) non modifiable(s) : {', '.join(sorted(inconnus))}.")


def _enregistrer(user, ligne: Ligne) -> Ligne:
    ligne._history_user = user  # auteur de l'entrée d'historique, même hors requête HTTP
    ligne.full_clean(exclude=CHAMPS_CALCULES)
    with transaction.atomic():
        ligne.save()
    return ligne


def creer_ligne(user, societe, **donnees) -> Ligne:
    _verifier_champs(donnees)
    if not acces.peut_saisir(user, societe):
        acces.refuser(user, "creer_ligne", societe=societe)
    return _enregistrer(user, Ligne(societe=societe, cree_par=user, **donnees))


def modifier_ligne(user, ligne: Ligne, **donnees) -> Ligne:
    _verifier_champs(donnees)
    if not acces.peut_modifier_ligne(user, ligne):
        acces.refuser(user, "modifier_ligne", ligne=ligne.pk)
    for champ, valeur in donnees.items():
        setattr(ligne, champ, valeur)
    # Le droit est revérifié après modification : une Saisie ne peut pas sortir une ligne de sa fenêtre.
    if not acces.peut_modifier_ligne(user, ligne):
        acces.refuser(user, "modifier_ligne", ligne=ligne.pk, motif="hors fenêtre de modification")
    ligne.modifie_par = user
    return _enregistrer(user, ligne)


def supprimer_ligne(user, ligne: Ligne) -> None:
    """Suppression douce (restaurable)."""
    if not acces.peut_supprimer_ligne(user, ligne):
        acces.refuser(user, "supprimer_ligne", ligne=ligne.pk)
    ligne._history_user = user
    ligne.supprimer()


def restaurer_ligne(user, ligne: Ligne) -> None:
    if not acces.peut_supprimer_ligne(user, ligne):
        acces.refuser(user, "restaurer_ligne", ligne=ligne.pk)
    ligne._history_user = user
    ligne.restaurer()


def objectif_franchi(societe, mois, marge_avant, marge_apres) -> bool:
    """L'enregistrement fait-il passer la société au-dessus de son objectif du mois ?"""
    objectif = societe.objectif_pour(mois)
    return not objectif_atteint(marge_avant, objectif) and objectif_atteint(marge_apres, objectif)


def franchissements(etat_avant: dict, etat_apres: dict) -> set[str]:
    """
    Seuils franchis entre deux états du mois (voir selectors.etat_du_mois) :
    « objectif_atteint » (confettis) et/ou « charges_couvertes » (simple notification).
    Un seuil déjà franchi avant l'enregistrement ne compte pas : une seule notification par franchissement.
    """
    return {cle for cle in ("objectif_atteint", "charges_couvertes") if etat_apres[cle] and not etat_avant[cle]}
