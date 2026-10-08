"""
Écritures sur les clients, les objectifs et les dépenses mensuels d'une société.
Chaque fonction vérifie le droit (`comptes.acces`), valide puis enregistre.
Un refus lève `PermissionDenied` et il est journalisé.
"""
from comptes import acces

from .models import Client, DepenseMensuelle, ObjectifMensuel, premier_du_mois

CHAMPS_CLIENT = frozenset({"nom", "telephone", "email"})


def _verifier_droit(user, societe, action: str, **details) -> None:
    if not acces.peut_gerer_societe(user, societe):
        acces.refuser(user, action, societe=societe, **details)


def _verifier_champs(donnees: dict) -> None:
    inconnus = set(donnees) - CHAMPS_CLIENT
    if inconnus:
        raise ValueError(f"Champ(s) non modifiable(s) : {', '.join(sorted(inconnus))}.")


def _enregistrer_client(user, client: Client) -> Client:
    client._history_user = user  # auteur de l'entrée d'historique, même hors requête HTTP
    client.nom = " ".join(client.nom.split())  # même nettoyage qu'à l'enregistrement, avant la validation
    client.full_clean()
    client.save()
    return client


def ajouter_client(user, societe, nom, **extra) -> Client:
    _verifier_champs(extra)
    _verifier_droit(user, societe, "ajouter_client")
    return _enregistrer_client(user, Client(societe=societe, nom=nom, **extra))


def modifier_client(user, client: Client, **donnees) -> Client:
    _verifier_champs(donnees)
    _verifier_droit(user, client.societe_id, "modifier_client", client=client.pk)
    for champ, valeur in donnees.items():
        setattr(client, champ, valeur)
    return _enregistrer_client(user, client)


def retirer_client(user, client: Client) -> None:
    """Suppression douce (restaurable)."""
    _verifier_droit(user, client.societe_id, "retirer_client", client=client.pk)
    client._history_user = user
    client.supprimer()


def definir_objectif(user, societe, mois, montant) -> ObjectifMensuel:
    """Crée ou met à jour l'objectif du mois (toujours enregistré au 1er du mois)."""
    _verifier_droit(user, societe, "definir_objectif", mois=mois)
    mois = premier_du_mois(mois)
    objectif = (ObjectifMensuel.objects.filter(societe=societe, mois=mois).first()
                or ObjectifMensuel(societe=societe, mois=mois))
    objectif.montant = montant
    objectif._history_user = user
    objectif.full_clean()
    objectif.save()
    return objectif


def supprimer_objectif(user, objectif: ObjectifMensuel) -> None:
    """Le mois reprend alors l'objectif du dernier mois renseigné (ou celui par défaut)."""
    _verifier_droit(user, objectif.societe_id, "supprimer_objectif", objectif=objectif.pk)
    objectif._history_user = user
    objectif.delete()


def definir_depenses(user, societe, mois, montant, note="") -> DepenseMensuelle:
    """
    Crée ou met à jour les dépenses réelles du mois (montant global, 1er du mois).
    Mêmes droits que les objectifs : Responsable de la société ou Admin groupe.
    """
    _verifier_droit(user, societe, "definir_depenses", mois=mois)
    mois = premier_du_mois(mois)
    depense = (DepenseMensuelle.objects.filter(societe=societe, mois=mois).first()
               or DepenseMensuelle(societe=societe, mois=mois))
    depense.montant = montant
    depense.note = note or ""
    depense.saisi_par = user
    depense._history_user = user
    depense.full_clean()
    depense.save()
    return depense
