"""
Écritures sur les lignes. Toute création, modification, suppression ou restauration de ligne
passe par ces fonctions : elles vérifient le droit (`comptes.acces`), valident puis enregistrent.
Un refus lève `PermissionDenied` et il est journalisé.
"""
from django.db import transaction

from comptes import acces

from .models import Ligne

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


def _enregistrer(ligne: Ligne) -> Ligne:
    ligne.full_clean(exclude=CHAMPS_CALCULES)
    with transaction.atomic():
        ligne.save()
    return ligne


def creer_ligne(user, societe, **donnees) -> Ligne:
    _verifier_champs(donnees)
    if not acces.peut_saisir(user, societe):
        acces.refuser(user, "creer_ligne", societe=societe)
    return _enregistrer(Ligne(societe=societe, cree_par=user, **donnees))


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
    return _enregistrer(ligne)


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
