"""
Services d'administration des habilitations : SEUL point d'entrée pour accorder, modifier ou retirer un droit.

Chaque service :
- vérifie que l'appelant est administrateur groupe (sinon `PermissionDenied` + entrée « accès refusé ») ;
- applique les règles métier (motifs obligatoires, dernier admin, pas d'auto-restriction…) en levant
  `ValidationError` avec un message en français ;
- écrit EN UNE TRANSACTION la modification et l'entrée du journal de sécurité (auteur, cible, avant, après, motif) ;
- supprime les sessions de la personne concernée quand un droit lui est retiré, pour un effet immédiat.

Les vues et l'admin Django ne modifient jamais `Affectation` / `HabilitationVueGroupe` autrement qu'ici.
"""
from contextlib import contextmanager
from datetime import date

from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from comptes import acces
from comptes.journal import journaliser, par_service
from comptes.models import Affectation, HabilitationVueGroupe, JournalSecurite, Utilisateur
from societes.models import Societe

E = JournalSecurite.Evenement
PORTEE = HabilitationVueGroupe.Portee
CHAMPS_AFFECTATION = {"role", "date_debut", "date_fin", "motif", "actif"}
CHAMPS_VUE_GROUPE = {"portee", "societes", "detail_autorise", "date_debut", "date_fin", "motif", "actif"}


# --- Outils internes -------------------------------------------------------------------------

@contextmanager
def _operation():
    """Transaction + indication aux signaux de ne pas dupliquer l'entrée de journal."""
    jeton = par_service.set(True)
    try:
        with transaction.atomic():
            yield
    finally:
        par_service.reset(jeton)


def _exiger_admin(admin, action: str, **details) -> None:
    if not acces.peut_administrer(admin):
        acces.refuser(admin, f"habilitations.{action}", **details)


def _motif_obligatoire(motif: str, quoi: str) -> str:
    motif = (motif or "").strip()
    if not motif:
        raise ValidationError(f"Un motif est obligatoire pour {quoi}.")
    return motif


def _verifier_dates(date_debut, date_fin) -> None:
    for valeur in (date_debut, date_fin):
        if valeur is not None and not isinstance(valeur, date):
            raise ValidationError("Date invalide.")
    if date_debut and date_fin and date_fin < date_debut:
        raise ValidationError("La date de fin doit être postérieure ou égale à la date de début.")


def supprimer_sessions(utilisateur) -> int:
    """Déconnecte la personne partout : supprime toutes ses sessions. Renvoie le nombre de sessions supprimées."""
    cle = str(utilisateur.pk)
    a_supprimer = [s.pk for s in Session.objects.filter(expire_date__gt=timezone.now())
                   if s.get_decoded().get("_auth_user_id") == cle]
    Session.objects.filter(pk__in=a_supprimer).delete()
    return len(a_supprimer)


def _cible(utilisateur) -> dict:
    return {"cible_id": utilisateur.pk, "cible_email": utilisateur.email}


def _etat_affectation(affectation) -> dict | None:
    if affectation is None:
        return None
    return {"role": affectation.role, "actif": affectation.actif, "date_debut": affectation.date_debut,
            "date_fin": affectation.date_fin, "motif": affectation.motif}


def _codes(societes) -> list[str]:
    return sorted(s.code for s in societes)


def _etat_vue_groupe(habilitation) -> dict | None:
    if habilitation is None or habilitation.pk is None:
        return None
    return {"portee": habilitation.portee, "societes": _codes(habilitation.societes.all()),
            "detail_autorise": habilitation.detail_autorise, "actif": habilitation.actif,
            "date_debut": habilitation.date_debut, "date_fin": habilitation.date_fin, "motif": habilitation.motif}


def _admins_actifs_hors(utilisateur) -> int:
    return (Utilisateur.objects.filter(is_active=True)
            .filter(Q(role_global=Utilisateur.RoleGlobal.ADMIN_GROUPE) | Q(is_superuser=True))
            .exclude(pk=utilisateur.pk).count())


def _est_admin(utilisateur) -> bool:
    return utilisateur.is_superuser or utilisateur.role_global == Utilisateur.RoleGlobal.ADMIN_GROUPE


def _verifier_societes_vue_groupe(portee, societes) -> list[Societe]:
    if portee not in PORTEE.values:
        raise ValidationError("Portée de la Vue Groupe inconnue.")
    if portee == PORTEE.TOUTES:
        return []
    liste = list({s.pk: s for s in societes}.values())
    if len(liste) < 2:
        raise ValidationError("Une Vue Groupe sur une sélection doit porter sur au moins 2 sociétés "
                              "(sinon ce n'est plus une vue consolidée).")
    return liste


# --- Accès société ---------------------------------------------------------------------------

def accorder_acces_societe(admin, utilisateur, societe, role, *, date_debut=None, date_fin=None, motif="") -> Affectation:
    """Donne à `utilisateur` le rôle `role` sur `societe` (réactive et met à jour l'accès s'il existait déjà)."""
    _exiger_admin(admin, "accorder_acces_societe", cible=utilisateur.email, societe=societe.code)
    if role not in Affectation.Role.values:
        raise ValidationError("Rôle inconnu.")
    _verifier_dates(date_debut, date_fin)
    with _operation():
        affectation = Affectation.objects.filter(utilisateur=utilisateur, societe=societe).first()
        avant = _etat_affectation(affectation)
        if affectation is None:
            affectation = Affectation(utilisateur=utilisateur, societe=societe)
        affectation.role, affectation.actif = role, True
        affectation.date_debut, affectation.date_fin = date_debut, date_fin
        affectation.motif = (motif or "").strip()
        affectation.accorde_par = admin
        affectation.save()
        journaliser(E.ACCES_SOCIETE_ACCORDE, utilisateur=admin, **_cible(utilisateur), societe=societe.code,
                    avant=avant, apres=_etat_affectation(affectation), motif=affectation.motif)
    acces.vider_cache(utilisateur)
    return affectation


def modifier_acces_societe(admin, affectation, **changements) -> Affectation:
    """Modifie le rôle, les dates, le motif ou l'état d'un accès société existant."""
    _exiger_admin(admin, "modifier_acces_societe", cible=affectation.utilisateur.email,
                  societe=affectation.societe.code)
    inconnus = set(changements) - CHAMPS_AFFECTATION
    if inconnus:
        raise ValidationError(f"Champ non modifiable : {', '.join(sorted(inconnus))}.")
    if "role" in changements and changements["role"] not in Affectation.Role.values:
        raise ValidationError("Rôle inconnu.")
    _verifier_dates(changements.get("date_debut", affectation.date_debut), changements.get("date_fin", affectation.date_fin))
    with _operation():
        avant = _etat_affectation(affectation)
        for champ, valeur in changements.items():
            setattr(affectation, champ, (valeur or "").strip() if champ == "motif" else valeur)
        affectation.accorde_par = admin
        affectation.save()
        journaliser(E.ACCES_SOCIETE_MODIFIE, utilisateur=admin, **_cible(affectation.utilisateur),
                    societe=affectation.societe.code, avant=avant, apres=_etat_affectation(affectation),
                    motif=affectation.motif)
        if avant["actif"] and not affectation.actif:
            supprimer_sessions(affectation.utilisateur)
    acces.vider_cache(affectation.utilisateur)
    return affectation


def retirer_acces_societe(admin, affectation, motif="") -> None:
    """Retire l'accès (l'affectation est désactivée, jamais supprimée : l'historique reste)."""
    _exiger_admin(admin, "retirer_acces_societe", cible=affectation.utilisateur.email, societe=affectation.societe.code)
    motif = _motif_obligatoire(motif, "retirer un accès")
    with _operation():
        avant = _etat_affectation(affectation)
        affectation.actif = False
        affectation.motif = motif
        affectation.accorde_par = admin
        affectation.save()
        journaliser(E.ACCES_SOCIETE_RETIRE, utilisateur=admin, **_cible(affectation.utilisateur),
                    societe=affectation.societe.code, avant=avant, apres=_etat_affectation(affectation), motif=motif)
        supprimer_sessions(affectation.utilisateur)
    acces.vider_cache(affectation.utilisateur)


# --- Vue Groupe ------------------------------------------------------------------------------

def accorder_vue_groupe(admin, utilisateur, *, portee, societes=(), detail_autorise=False,
                        date_debut=None, date_fin=None, motif="") -> HabilitationVueGroupe:
    """Accorde (ou met à jour et réactive) la Vue Groupe. Motif obligatoire ; une sélection compte au moins 2 sociétés."""
    _exiger_admin(admin, "accorder_vue_groupe", cible=utilisateur.email)
    motif = _motif_obligatoire(motif, "une habilitation Vue Groupe")
    liste = _verifier_societes_vue_groupe(portee, societes)
    _verifier_dates(date_debut, date_fin)
    with _operation():
        habilitation = HabilitationVueGroupe.objects.filter(utilisateur=utilisateur).first()
        avant = _etat_vue_groupe(habilitation)
        if habilitation is None:
            habilitation = HabilitationVueGroupe(utilisateur=utilisateur)
        habilitation.portee, habilitation.detail_autorise, habilitation.actif = portee, bool(detail_autorise), True
        habilitation.date_debut, habilitation.date_fin, habilitation.motif = date_debut, date_fin, motif
        habilitation.accorde_par = admin
        habilitation.save()
        habilitation.societes.set(liste)
        journaliser(E.VUE_GROUPE_ACCORDEE, utilisateur=admin, **_cible(utilisateur), avant=avant,
                    apres=_etat_vue_groupe(habilitation), motif=motif)
    acces.vider_cache(utilisateur)
    return habilitation


def modifier_vue_groupe(admin, habilitation, **changements) -> HabilitationVueGroupe:
    """Modifie la portée, les sociétés, le détail, les dates ou le motif d'une Vue Groupe existante."""
    _exiger_admin(admin, "modifier_vue_groupe", cible=habilitation.utilisateur.email)
    inconnus = set(changements) - CHAMPS_VUE_GROUPE
    if inconnus:
        raise ValidationError(f"Champ non modifiable : {', '.join(sorted(inconnus))}.")
    portee = changements.get("portee", habilitation.portee)
    societes = changements["societes"] if "societes" in changements else list(habilitation.societes.all())
    liste = _verifier_societes_vue_groupe(portee, societes)
    _verifier_dates(changements.get("date_debut", habilitation.date_debut), changements.get("date_fin", habilitation.date_fin))
    motif = _motif_obligatoire(changements.get("motif", habilitation.motif), "une habilitation Vue Groupe")
    with _operation():
        avant = _etat_vue_groupe(habilitation)
        for champ in ("portee", "detail_autorise", "date_debut", "date_fin", "actif"):
            if champ in changements:
                setattr(habilitation, champ, changements[champ])
        habilitation.motif = motif
        habilitation.accorde_par = admin
        habilitation.save()
        habilitation.societes.set(liste)
        journaliser(E.VUE_GROUPE_MODIFIEE, utilisateur=admin, **_cible(habilitation.utilisateur), avant=avant,
                    apres=_etat_vue_groupe(habilitation), motif=motif)
        if avant["actif"] and not habilitation.actif:
            supprimer_sessions(habilitation.utilisateur)
    acces.vider_cache(habilitation.utilisateur)
    return habilitation


def retirer_vue_groupe(admin, utilisateur, motif="") -> None:
    """Retire la Vue Groupe (désactivée, jamais supprimée) et déconnecte la personne."""
    _exiger_admin(admin, "retirer_vue_groupe", cible=utilisateur.email)
    motif = _motif_obligatoire(motif, "retirer la Vue Groupe")
    habilitation = HabilitationVueGroupe.objects.filter(utilisateur=utilisateur).first()
    if habilitation is None:
        raise ValidationError("Cette personne n'a pas d'habilitation Vue Groupe.")
    with _operation():
        avant = _etat_vue_groupe(habilitation)
        habilitation.actif = False
        habilitation.motif = motif
        habilitation.accorde_par = admin
        habilitation.save()
        journaliser(E.VUE_GROUPE_RETIREE, utilisateur=admin, **_cible(utilisateur), avant=avant,
                    apres=_etat_vue_groupe(habilitation), motif=motif)
        supprimer_sessions(utilisateur)
    acces.vider_cache(utilisateur)


# --- Compte ----------------------------------------------------------------------------------

def definir_role_global(admin, utilisateur, role_global, motif="") -> Utilisateur:
    """Aucun ↔ Administrateur groupe. Retirer ce rôle : superutilisateur seulement, jamais à soi-même ni au dernier admin."""
    _exiger_admin(admin, "definir_role_global", cible=utilisateur.email)
    if role_global not in Utilisateur.RoleGlobal.values:
        raise ValidationError("Rôle groupe inconnu.")
    avant = utilisateur.role_global
    if avant == role_global:
        return utilisateur
    retire_admin = avant == Utilisateur.RoleGlobal.ADMIN_GROUPE
    if retire_admin:
        if utilisateur.pk == admin.pk:
            raise ValidationError("Vous ne pouvez pas vous retirer vos propres droits d'administrateur.")
        if not admin.is_superuser:
            acces.refuser(admin, "habilitations.retirer_role_admin", cible=utilisateur.email)
        if _admins_actifs_hors(utilisateur) == 0:
            raise ValidationError("Il doit toujours rester au moins un administrateur groupe actif.")
        motif = _motif_obligatoire(motif, "retirer le rôle d'administrateur groupe")
    with _operation():
        utilisateur.role_global = role_global
        utilisateur.save(update_fields=["role_global"])
        journaliser(E.ROLE_GLOBAL_MODIFIE, utilisateur=admin, **_cible(utilisateur),
                    avant={"role_global": avant or "aucun"}, apres={"role_global": role_global or "aucun"},
                    motif=(motif or "").strip())
        if retire_admin:
            supprimer_sessions(utilisateur)
    acces.vider_cache(utilisateur)
    return utilisateur


def activer_compte(admin, utilisateur) -> Utilisateur:
    _exiger_admin(admin, "activer_compte", cible=utilisateur.email)
    if utilisateur.is_active:
        return utilisateur
    with _operation():
        utilisateur.is_active = True
        utilisateur.save(update_fields=["is_active"])
        journaliser(E.COMPTE_ACTIVE, utilisateur=admin, **_cible(utilisateur),
                    avant={"actif": False}, apres={"actif": True})
    return utilisateur


def desactiver_compte(admin, utilisateur, motif="") -> Utilisateur:
    """Désactive le compte et supprime immédiatement ses sessions. Jamais son propre compte, jamais le dernier admin."""
    _exiger_admin(admin, "desactiver_compte", cible=utilisateur.email)
    if utilisateur.pk == admin.pk:
        raise ValidationError("Vous ne pouvez pas désactiver votre propre compte.")
    if not utilisateur.is_active:
        return utilisateur
    if _est_admin(utilisateur) and _admins_actifs_hors(utilisateur) == 0:
        raise ValidationError("Il doit toujours rester au moins un administrateur groupe actif.")
    motif = _motif_obligatoire(motif, "désactiver un compte")
    with _operation():
        utilisateur.is_active = False
        utilisateur.save(update_fields=["is_active"])
        supprimer_sessions(utilisateur)
        journaliser(E.COMPTE_DESACTIVE, utilisateur=admin, **_cible(utilisateur),
                    avant={"actif": True}, apres={"actif": False}, motif=motif)
    return utilisateur


def creer_compte(admin, *, email, nom, prenom, telephone="", role_global="", acces_societes=(), vue_groupe=None):
    """
    Crée un compte avec un mot de passe provisoire aléatoire (renvoyé, à afficher UNE SEULE FOIS ; changement obligatoire
    à la première connexion) et ses habilitations initiales.

    `acces_societes` : liste de dicts {societe, role, date_debut, date_fin, motif} ;
    `vue_groupe` : dict d'arguments de `accorder_vue_groupe` (sans `admin` ni `utilisateur`) ou None.
    Renvoie (utilisateur, mot_de_passe_provisoire).
    """
    from allauth.account.models import EmailAddress
    from django.contrib.auth.password_validation import validate_password

    from comptes.management.commands.creer_utilisateur import mot_de_passe_aleatoire

    _exiger_admin(admin, "creer_compte", cible=email)
    email = Utilisateur.objects.normalize_email(email).strip().lower()
    if Utilisateur.objects.filter(email__iexact=email).exists():
        raise ValidationError(f"Un compte existe déjà pour {email}.")
    mot_de_passe = mot_de_passe_aleatoire()
    utilisateur = Utilisateur(username=email, email=email, first_name=prenom.strip(), last_name=nom.strip(),
                              telephone=telephone.strip(), doit_changer_mot_de_passe=True)
    utilisateur.full_clean(exclude=["password"])
    validate_password(mot_de_passe, utilisateur)
    with _operation():
        utilisateur.set_password(mot_de_passe)
        utilisateur.save()
        EmailAddress.objects.create(user=utilisateur, email=email, primary=True, verified=True)
        journaliser(E.COMPTE_CREE, utilisateur=admin, **_cible(utilisateur), avant=None, apres={"actif": True})
        if role_global:
            definir_role_global(admin, utilisateur, role_global)
        for demande in acces_societes:
            accorder_acces_societe(admin, utilisateur, demande["societe"], demande["role"],
                                   date_debut=demande.get("date_debut"), date_fin=demande.get("date_fin"),
                                   motif=demande.get("motif", ""))
        if vue_groupe:
            accorder_vue_groupe(admin, utilisateur, **vue_groupe)
    return utilisateur, mot_de_passe
