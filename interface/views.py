"""
Vues de l'interface. Une vue vérifie l'accès (mixins), appelle un sélecteur ou un service,
puis rend un gabarit : aucune règle métier ni aucun calcul ici.
"""
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.generic import TemplateView

from comptes import acces

from .contexte import InterfaceMixin, PageGroupeMixin, PageSocieteMixin
from .theme import css_theme


# --- Accueil, thème, onglets ------------------------------------------------------------------

class AccueilView(InterfaceMixin, TemplateView):
    """Redirige vers la Vue Groupe (Admin, Direction) ou vers la 1re société accessible."""

    template_name = "interface/aucune_societe.html"

    def get(self, request, *args, **kwargs):
        if acces.voit_tout_le_groupe(request.user):
            return redirect("interface:groupe")
        if self.onglets:
            return redirect("interface:tableau", code_societe=self.onglets[0].code)
        return super().get(request, *args, **kwargs)


@login_required
def theme_css(request, code):
    """Variables de couleur du thème (société ou « groupe ») et couleurs de série des sociétés accessibles."""
    societes = list(acces.societes_accessibles(request.user))
    if code == "groupe":
        societe = None
    else:
        societe = next((s for s in societes if s.code == code), None)
        if societe is None:
            raise Http404("Société introuvable.")
    reponse = HttpResponse(css_theme(societe, societes), content_type="text/css; charset=utf-8")
    reponse["Cache-Control"] = "private, max-age=3600"
    return reponse


class OngletsView(InterfaceMixin, TemplateView):
    """Fragment HTMX : barre d'onglets rafraîchie après une saisie (✔ objectif atteint)."""

    template_name = "partials/onglets.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        code = self.request.GET.get("actif", "")
        contexte["societe"] = next((s for s in self.onglets if s.code == code), None)
        contexte["section"] = self.request.GET.get("section", "tableau")
        return contexte


# --- Tableau de bord société (lot 3.2) et Vue Groupe (lot 3.5) --------------------------------

class TableauDeBordView(PageSocieteMixin, TemplateView):
    template_name = "interface/tableau_de_bord.html"
    section = "tableau"


class VueGroupeView(PageGroupeMixin, TemplateView):
    template_name = "interface/groupe.html"
    section = "groupe"


class PageAVenirView(PageSocieteMixin, TemplateView):
    """Provisoire : remplacée lot par lot."""

    template_name = "interface/a_venir.html"


class RegleView(InterfaceMixin, TemplateView):
    template_name = "interface/a_venir.html"


# --- Pages d'erreur ---------------------------------------------------------------------------

def _erreur(request, gabarit, statut):
    return render(request, gabarit, status=statut)


def erreur_403(request, exception=None):
    return _erreur(request, "erreurs/403.html", 403)


def erreur_404(request, exception=None):
    return _erreur(request, "erreurs/404.html", 404)


def erreur_500(request):
    return _erreur(request, "erreurs/500.html", 500)

