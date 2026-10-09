"""
Contexte commun à toutes les pages de l'interface (en-tête, onglets, pied de page)
et mixins de vues. Les droits viennent de `comptes.acces`, les calculs des sélecteurs.
"""
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property

from comptes import acces
from comptes.mixins import AccesSocieteMixin, SaisieSocieteMixin, VueGroupeMixin
from comptes.models import Affectation, Utilisateur
from operations.selectors import avec_etat_du_mois, objectif_atteint
from repartition.models import RegleRepartition

from .periode import decaler, mois_depuis_requete
from .theme import url_logo

CLE_REGLE = "interface:regle_en_vigueur"

LIBELLES_ROLES = {
    acces.ADMIN_GROUPE: Utilisateur.RoleGlobal.ADMIN_GROUPE.label,
    acces.RESPONSABLE: Affectation.Role.RESPONSABLE.label,
    acces.SAISIE: Affectation.Role.SAISIE.label,
    acces.LECTURE: Affectation.Role.LECTURE.label,
    acces.VUE_GROUPE: "Vue Groupe",
    acces.LECTURE_GROUPE: "Lecture (Vue Groupe)",
}


def regle_en_vigueur():
    """Règle en vigueur aujourd'hui (pied de page), mise en cache 5 minutes et oubliée à chaque modification."""
    aujourd_hui = timezone.localdate()
    en_cache = cache.get(CLE_REGLE)
    if en_cache is not None and en_cache[0] == aujourd_hui:
        return en_cache[1]
    try:
        regle = RegleRepartition.objects.en_vigueur(aujourd_hui)
    except RegleRepartition.DoesNotExist:
        regle = None
    cache.set(CLE_REGLE, (aujourd_hui, regle), 300)
    return regle


def oublier_regle_en_vigueur() -> None:
    cache.delete(CLE_REGLE)


def libelle_role(user, societe=None) -> str:
    """Rôle affiché dans le menu : rôle sur la société active, sinon rôle global."""
    role = acces.role_sur(user, societe) if societe is not None else None
    if role is None:
        roles = acces.roles_de(user)
        role = next((r for r in LIBELLES_ROLES if r in roles), None)
    return LIBELLES_ROLES.get(role, "")


class InterfaceMixin(LoginRequiredMixin):
    """Mois de suivi, onglets (sociétés accessibles avec l'état de leur objectif) et contexte commun."""

    societe = None
    section = "tableau"  # page de la société ouverte par les onglets

    @cached_property
    def mois(self):
        return mois_depuis_requete(self.request)

    @cached_property
    def onglets(self) -> list:
        societes = list(avec_etat_du_mois(acces.societes_accessibles(self.request.user), self.mois))
        for s in societes:
            s.objectif_atteint = objectif_atteint(s.marge_mois, s.objectif_mois)
        return societes

    def trouver_societe(self, request, code):
        """Recherche dans les onglets déjà chargés : pas de requête supplémentaire."""
        return next((s for s in self.onglets if s.code == code), None)

    @property
    def est_htmx(self) -> bool:
        return self.request.headers.get("HX-Request") == "true"

    def contexte_commun(self) -> dict:
        user = self.request.user
        url_courante = self.request.path
        return {
            "mois": self.mois,
            "mois_precedent": decaler(self.mois, -1),
            "mois_suivant": decaler(self.mois, 1),
            "url_courante": url_courante,
            "onglets": self.onglets,
            "section": self.section,
            "societe": self.societe,
            "logo_url": url_logo(self.societe),
            "voit_groupe": acces.voit_vue_groupe(user),
            "peut_gerer": self.societe is not None and acces.peut_gerer_societe(user, self.societe),
            "peut_administrer": acces.peut_administrer(user),
            "role_libelle": libelle_role(user, self.societe),
            "regle_pied": regle_en_vigueur(),
            "version": settings.VERSION_APPLICATION,
            "url_theme": reverse("interface:theme", args=[self.societe.code if self.societe else "groupe"]),
        }

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(self.contexte_commun())
        return contexte


class PageSocieteMixin(InterfaceMixin, AccesSocieteMixin):
    """Page d'une société lisible par l'utilisateur (sinon 404)."""


class SaisieSocieteInterfaceMixin(InterfaceMixin, SaisieSocieteMixin):
    """Page d'une société où l'utilisateur peut saisir (sinon 404 / 403)."""


class GestionSocieteMixin(InterfaceMixin, AccesSocieteMixin):
    """Clients, objectifs, corbeille : Responsable et Admin groupe (403 pour les autres lecteurs)."""

    def verifier_droit(self, request) -> None:
        if not acces.peut_gerer_societe(request.user, self.societe):
            acces.refuser(request.user, "gerer_societe", societe=self.societe.code, chemin=request.path)


class PageGroupeMixin(InterfaceMixin, VueGroupeMixin):
    """Vue Groupe : admin groupe ou habilitation Vue Groupe en vigueur (404 pour les autres)."""
