"""
Vues de l'interface. Une vue vérifie l'accès (mixins), appelle un sélecteur ou un service,
puis rend un gabarit : aucune règle métier ni aucun calcul ici.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.generic import FormView, TemplateView

from comptes import acces
from core.templatetags.format_fr import fcfa, mois_long
from operations.selectors import tableau_de_bord_societe
from societes.services import definir_objectif

from . import graphiques
from .contexte import GestionSocieteMixin, InterfaceMixin, PageGroupeMixin, PageSocieteMixin
from .forms import ObjectifForm
from .htmx import declencher, toast
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
    """Tableau de bord d'une société. En HTMX (rafraîchissement), seul le contenu est renvoyé."""

    template_name = "interface/tableau_de_bord.html"
    section = "tableau"

    def get_template_names(self):
        return ["partials/tableau_de_bord.html"] if self.est_htmx else [self.template_name]

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        donnees = tableau_de_bord_societe(self.societe, self.mois)
        contexte.update(
            donnees=donnees,
            ind=donnees["indicateurs"],
            postes=graphiques.postes(donnees["indicateurs"], self.societe.code),
            progression=graphiques.progression(donnees["indicateurs"]),
            graphiques=graphiques.donnees_tableau_de_bord(donnees, self.societe),
        )
        return contexte


class ObjectifView(GestionSocieteMixin, FormView):
    """Définir l'objectif du mois (Responsable, Admin groupe) via le service `definir_objectif`."""

    form_class = ObjectifForm
    section = "tableau"

    def get_template_names(self):
        return ["partials/objectif_form.html"] if self.est_htmx else ["interface/objectif.html"]

    def get_initial(self):
        return {"montant": self.societe.objectif_pour(self.mois)}

    def form_valid(self, form):
        try:
            definir_objectif(self.request.user, self.societe, self.mois, form.cleaned_data["montant"])
        except ValidationError as erreur:
            form.add_error("montant", erreur.messages)
            return self.form_invalid(form)
        message = f"Objectif de {mois_long(self.mois)} enregistré : {fcfa(form.cleaned_data['montant'])}."
        if self.est_htmx:
            reponse = HttpResponse(status=204)
            return declencher(reponse, objectifModifie=True, toast=toast(message))
        messages.success(self.request, message)
        return redirect("interface:tableau", code_societe=self.societe.code)

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form), status=422)


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

