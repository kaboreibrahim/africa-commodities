"""
Mixins de vues (pour l'étape 3). Les droits viennent de `comptes.acces`.

Un accès hors périmètre renvoie une 404 (et non une 403) pour ne pas révéler l'existence
de la ressource ; il est journalisé.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404

from comptes import acces
from societes.models import Societe


class AccesSocieteMixin(LoginRequiredMixin):
    """Charge la société `code_societe` de l'URL dans `self.societe` si l'utilisateur peut la lire."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        code = kwargs.get("code_societe")
        self.societe = Societe.objects.pour_utilisateur(request.user).filter(code=code).first()
        if self.societe is None:
            acces.signaler_refus(request.user, "lire_societe", societe=code, chemin=request.path)
            raise Http404("Société introuvable.")
        self.verifier_droit(request)
        return super().dispatch(request, *args, **kwargs)

    def verifier_droit(self, request) -> None:
        """Contrôle supplémentaire des sous-classes ; la lecture est déjà vérifiée."""


class SaisieSocieteMixin(AccesSocieteMixin):
    """Exige le droit de saisie sur la société (la société étant lisible, le refus est une 403)."""

    def verifier_droit(self, request) -> None:
        if not acces.peut_saisir(request.user, self.societe):
            acces.refuser(request.user, "saisir", societe=self.societe.code, chemin=request.path)


class VueGroupeMixin(LoginRequiredMixin):
    """Vue Groupe consolidée : Admin groupe et Direction uniquement."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not acces.voit_tout_le_groupe(request.user):
            acces.signaler_refus(request.user, "vue_groupe", chemin=request.path)
            raise Http404("Page introuvable.")
        return super().dispatch(request, *args, **kwargs)

