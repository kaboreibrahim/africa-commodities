"""
Contrôle d'accès : SEUL endroit du projet où la matrice des droits est appliquée.

Les vues (mixins de `comptes/mixins.py`), les services d'écriture et l'admin s'appuient
tous sur ces fonctions. Ne jamais se fier uniquement à ce que l'interface masque.

Rôles possibles sur une société (`role_sur`) :
« admin_groupe », « direction », « responsable », « saisie », « lecture » ou None.
"""
import logging
from datetime import date

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from comptes.models import Affectation, Utilisateur
from societes.models import Societe

logger = logging.getLogger("securite")

ADMIN_GROUPE = Utilisateur.RoleGlobal.ADMIN_GROUPE.value
DIRECTION = Utilisateur.RoleGlobal.DIRECTION.value
RESPONSABLE = Affectation.Role.RESPONSABLE.value
SAISIE = Affectation.Role.SAISIE.value
LECTURE = Affectation.Role.LECTURE.value

ROLES_ECRITURE = {ADMIN_GROUPE, RESPONSABLE, SAISIE}
ROLES_GESTION = {ADMIN_GROUPE, RESPONSABLE}


# --- Outils internes -------------------------------------------------------------------------

def _est_actif(user) -> bool:
    return user is not None and user.is_authenticated and user.is_active


def _affectations(user) -> dict[int, str]:
    """
    {id société: rôle} des affectations actives (sur des sociétés actives).
    Mis en cache sur l'objet `user`, donc une seule requête par requête HTTP.
    """
    cache = getattr(user, "_affectations_cache", None)
    if cache is None:
        cache = dict(
            Affectation.objects.filter(utilisateur_id=user.pk, actif=True, societe__actif=True)
            .values_list("societe_id", "role")
        )
        user._affectations_cache = cache
    return cache


def vider_cache(user) -> None:
    """À appeler si les affectations d'un utilisateur changent pendant une même requête."""
    user.__dict__.pop("_affectations_cache", None)


def _id_societe(societe) -> int:
    return societe.pk if isinstance(societe, Societe) else int(societe)


def debut_fenetre_saisie(aujourd_hui: date | None = None) -> date:
    """Premier jour de la fenêtre de modification du rôle Saisie (mois en cours + N mois avant)."""
    jour = aujourd_hui or timezone.localdate()
    n = settings.SAISIE_FENETRE_MODIFICATION_MOIS
    total = jour.year * 12 + (jour.month - 1) - n
    return date(total // 12, total % 12 + 1, 1)


# --- Rôles -----------------------------------------------------------------------------------

def est_admin_groupe(user) -> bool:
    return _est_actif(user) and (user.is_superuser or user.role_global == ADMIN_GROUPE)


def voit_tout_le_groupe(user) -> bool:
    """Admin groupe ou Direction : lecture de toutes les sociétés et de la vue Groupe."""
    return est_admin_groupe(user) or (_est_actif(user) and user.role_global == DIRECTION)


def peut_administrer(user) -> bool:
    """Règle de répartition, sociétés, utilisateurs, affectations, admin Django."""
    return est_admin_groupe(user)


def role_sur(user, societe) -> str | None:
    """Rôle effectif de `user` sur `societe` (objet Societe ou identifiant)."""
    if not _est_actif(user):
        return None
    if est_admin_groupe(user):
        return ADMIN_GROUPE
    role = _affectations(user).get(_id_societe(societe))
    # La Direction lit tout ; une affectation Responsable ou Saisie lui ajoute l'écriture.
    if user.role_global == DIRECTION and role not in ROLES_ECRITURE:
        return DIRECTION
    return role


def societes_accessibles(user):
    """Sociétés actives que l'utilisateur peut lire."""
    actives = Societe.objects.filter(actif=True)
    if not _est_actif(user):
        return actives.none()
    if voit_tout_le_groupe(user):
        return actives
    return actives.filter(pk__in=list(_affectations(user)))


# --- Droits ----------------------------------------------------------------------------------

def peut_lire(user, societe) -> bool:
    return role_sur(user, societe) is not None


def peut_saisir(user, societe) -> bool:
    """Créer une ligne."""
    return role_sur(user, societe) in ROLES_ECRITURE


def peut_modifier_ligne(user, ligne) -> bool:
    """Responsable et admin : toutes les lignes. Saisie : ses lignes, dans la fenêtre de modification."""
    role = role_sur(user, ligne.societe_id)
    if role in ROLES_GESTION:
        return True
    if role == SAISIE:
        return (ligne.cree_par_id == user.pk and ligne.supprime_le is None
                and ligne.date is not None and ligne.date >= debut_fenetre_saisie())
    return False


def peut_supprimer_ligne(user, ligne) -> bool:
    """Suppression douce et restauration."""
    return role_sur(user, ligne.societe_id) in ROLES_GESTION


def peut_gerer_societe(user, societe) -> bool:
    """Clients et objectifs mensuels."""
    return role_sur(user, societe) in ROLES_GESTION


# --- Refus -----------------------------------------------------------------------------------

def signaler_refus(user, action: str, **details) -> None:
    """Journalise un accès refusé (sans lever d'exception)."""
    from comptes.journal import journaliser_refus  # import tardif : évite une boucle d'imports

    journaliser_refus(user, action, **details)


def refuser(user, action: str, **details):
    """Journalise le refus puis lève PermissionDenied."""
    signaler_refus(user, action, **details)
    raise PermissionDenied("Vous n'avez pas le droit d'effectuer cette action.")
