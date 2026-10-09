"""
Contrôle d'accès : SEUL endroit du projet où la matrice des droits est appliquée.

Les vues (mixins de `comptes/mixins.py`), les services d'écriture et l'admin s'appuient
tous sur ces fonctions. Ne jamais se fier uniquement à ce que l'interface masque.

Deux familles d'habilitations, accordées par l'administrateur groupe (`comptes/services.py`) :
- l'accès à une société (`Affectation` : Responsable, Saisie ou Lecture) ;
- la Vue Groupe (`HabilitationVueGroupe` : toutes les sociétés ou une sélection, avec ou sans accès au détail).
Chacune peut avoir une date de début et une date de fin : une habilitation hors période ne donne aucun droit,
sans action manuelle. Rien n'est conservé entre deux requêtes : un retrait s'applique à la requête suivante.

Rôles possibles sur une société (`role_sur`) :
« admin_groupe », « responsable », « saisie », « lecture », « lecture_groupe » (lecture seule obtenue
par la Vue Groupe) ou None.
"""
import logging
from dataclasses import dataclass
from datetime import date

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import BooleanField, CharField, Q, Value
from django.utils import timezone

from comptes.models import Affectation, HabilitationVueGroupe, Utilisateur
from societes.models import Societe

logger = logging.getLogger("securite")

ADMIN_GROUPE = Utilisateur.RoleGlobal.ADMIN_GROUPE.value
RESPONSABLE = Affectation.Role.RESPONSABLE.value
SAISIE = Affectation.Role.SAISIE.value
LECTURE = Affectation.Role.LECTURE.value
LECTURE_GROUPE = "lecture_groupe"  # lecture seule obtenue via la Vue Groupe (détail autorisé)
VUE_GROUPE = "vue_groupe"  # « rôle » de titulaire d'une habilitation Vue Groupe (sert à imposer la 2FA)

ROLES_ECRITURE = {ADMIN_GROUPE, RESPONSABLE, SAISIE}
ROLES_GESTION = {ADMIN_GROUPE, RESPONSABLE}

TOUTES = HabilitationVueGroupe.Portee.TOUTES.value


# --- Outils internes -------------------------------------------------------------------------

@dataclass(frozen=True)
class _PorteeGroupe:
    portee: str
    detail: bool
    societes: frozenset  # ids des sociétés ACTIVES cochées (inutilisé quand portee == « toutes »)


@dataclass(frozen=True)
class _Droits:
    affectations: dict  # {id société: rôle}, affectations en vigueur sur des sociétés actives
    groupe: _PorteeGroupe | None  # habilitation Vue Groupe en vigueur


def _est_actif(user) -> bool:
    return user is not None and user.is_authenticated and user.is_active


def _droits(user) -> _Droits:
    """
    Habilitations en vigueur de l'utilisateur : UNE requête (UNION des affectations et de l'habilitation Vue Groupe
    avec ses sociétés), mise en cache sur l'objet `user` pour la durée de la requête HTTP seulement.
    """
    droits = getattr(user, "_droits_cache", None)
    if droits is None:
        aujourd_hui = timezone.localdate()
        affectations = (
            Affectation.objects.en_vigueur(aujourd_hui).filter(utilisateur_id=user.pk, societe__actif=True)
            .order_by()
            .annotate(genre=Value("a", CharField()), detail=Value(False, BooleanField()))
            .values_list("genre", "societe_id", "role", "detail")
        )
        groupe_qs = (
            HabilitationVueGroupe.objects.en_vigueur(aujourd_hui).filter(utilisateur_id=user.pk)
            .filter(Q(societes__isnull=True) | Q(societes__actif=True))
            .order_by()
            .annotate(genre=Value("g", CharField()))
            .values_list("genre", "societes__id", "portee", "detail_autorise")
        )
        lignes = list(affectations.union(groupe_qs, all=True))
        groupe_lignes = [ligne for ligne in lignes if ligne[0] == "g"]
        groupe = None
        if groupe_lignes:
            groupe = _PorteeGroupe(portee=groupe_lignes[0][2], detail=groupe_lignes[0][3],
                                   societes=frozenset(l[1] for l in groupe_lignes if l[1] is not None))
        droits = _Droits({l[1]: l[2] for l in lignes if l[0] == "a"}, groupe)
        user._droits_cache = droits
    return droits


def vider_cache(user) -> None:
    """À appeler si les habilitations d'un utilisateur changent pendant une même requête."""
    user.__dict__.pop("_droits_cache", None)


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


def peut_administrer(user) -> bool:
    """Habilitations, règle de répartition, sociétés, utilisateurs, admin Django."""
    return est_admin_groupe(user)


def habilitation_groupe(user) -> HabilitationVueGroupe | None:
    """L'habilitation Vue Groupe EN VIGUEUR de l'utilisateur (objet complet, pour l'affichage), sinon None."""
    if not _est_actif(user):
        return None
    return (HabilitationVueGroupe.objects.en_vigueur().filter(utilisateur_id=user.pk)
            .prefetch_related("societes").first())


def voit_vue_groupe(user) -> bool:
    """Admin groupe, ou titulaire d'une habilitation Vue Groupe en vigueur."""
    if not _est_actif(user):
        return False
    return est_admin_groupe(user) or _droits(user).groupe is not None


# Ancien nom (étape 2, rôle « Direction ») : conservé pour la compatibilité, même règle que voit_vue_groupe.
voit_tout_le_groupe = voit_vue_groupe


def societes_vue_groupe(user):
    """Sociétés actives sur lesquelles porte la Vue Groupe de l'utilisateur (aucune s'il n'y a pas droit)."""
    actives = Societe.objects.filter(actif=True)
    if not _est_actif(user):
        return actives.none()
    if est_admin_groupe(user):
        return actives
    groupe = _droits(user).groupe
    if groupe is None:
        return actives.none()
    if groupe.portee == TOUTES:
        return actives
    return actives.filter(pk__in=groupe.societes)


def portee_vue_groupe(user) -> str | None:
    """« toutes » ou « selection » pour qui voit la Vue Groupe (l'admin voit toujours « toutes »), sinon None."""
    if not _est_actif(user):
        return None
    if est_admin_groupe(user):
        return TOUTES
    groupe = _droits(user).groupe
    return groupe.portee if groupe is not None else None


def detail_via_groupe(user, societe) -> bool:
    """Vrai si l'habilitation Vue Groupe autorise le détail (lecture seule) de cette société."""
    if not _est_actif(user) or est_admin_groupe(user):
        return False
    groupe = _droits(user).groupe
    if groupe is None or not groupe.detail:
        return False
    return groupe.portee == TOUTES or _id_societe(societe) in groupe.societes


def roles_de(user) -> set[str]:
    """Tous les rôles de l'utilisateur (global, par société, Vue Groupe), par ex. pour imposer la 2FA."""
    if not _est_actif(user):
        return set()
    roles = set(_droits(user).affectations.values())
    if est_admin_groupe(user):
        roles.add(ADMIN_GROUPE)
    if _droits(user).groupe is not None:
        roles.add(VUE_GROUPE)
    return roles


def role_sur(user, societe) -> str | None:
    """Rôle effectif de `user` sur `societe` (objet Societe ou identifiant) : affectation, sinon lecture via la Vue Groupe."""
    if not _est_actif(user):
        return None
    if est_admin_groupe(user):
        return ADMIN_GROUPE
    role = _droits(user).affectations.get(_id_societe(societe))
    if role is not None:
        return role
    return LECTURE_GROUPE if detail_via_groupe(user, societe) else None


def societes_accessibles(user):
    """Sociétés actives que l'utilisateur peut lire : affectations en vigueur + détail autorisé par la Vue Groupe."""
    actives = Societe.objects.filter(actif=True)
    if not _est_actif(user):
        return actives.none()
    if est_admin_groupe(user):
        return actives
    droits = _droits(user)
    ids = set(droits.affectations)
    if droits.groupe is not None and droits.groupe.detail:
        if droits.groupe.portee == TOUTES:
            return actives
        ids |= droits.groupe.societes
    return actives.filter(pk__in=ids)


def societes_visibles(user):
    """Sociétés dont le NOM peut apparaître à l'utilisateur : accessibles ou comprises dans sa Vue Groupe."""
    actives = Societe.objects.filter(actif=True)
    if not _est_actif(user):
        return actives.none()
    if est_admin_groupe(user):
        return actives
    droits = _droits(user)
    ids = set(droits.affectations)
    if droits.groupe is not None:
        if droits.groupe.portee == TOUTES:
            return actives
        ids |= droits.groupe.societes
    return actives.filter(pk__in=ids)


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
