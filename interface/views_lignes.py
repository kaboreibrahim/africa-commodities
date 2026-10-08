"""
Saisie et liste des lignes (lot 3.3) : ajout, aperçu de répartition, modification, suppression douce,
restauration, corbeille. Les écritures passent UNIQUEMENT par operations.services, les droits par
comptes.acces, les calculs par repartition.services et operations.selectors.
"""
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.views.generic import TemplateView

from comptes import acces
from core.templatetags.format_fr import mois_long
from operations import services
from operations.models import Ligne
from operations.selectors import PERIODES, etat_du_mois, lignes_filtrees, projets_de_la_societe, totaux
from repartition.models import RegleRepartition
from repartition.services import calculer_repartition
from societes.models import Client, premier_du_mois

from .contexte import GestionSocieteMixin, PageSocieteMixin, regle_en_vigueur
from .forms import FiltresLignesForm, LigneForm
from .htmx import declencher, evenements_franchissement, toast

LIGNES_PAR_PAGE = 50


def _libelle(societe, verbe: str) -> str:
    """« Dossier ajouté(e) », « Opération modifié(e) »…"""
    return f"{societe.libelle_ligne[:1].upper()}{societe.libelle_ligne[1:]} {verbe}(e)"


class LignesMixin:
    """Outils communs aux vues des lignes d'une société."""

    @cached_property
    def clients(self) -> list:
        return list(Client.objects.filter(societe=self.societe).order_by("nom"))

    prefixe_ids = "id_%s"

    def formulaire(self, data=None, initial=None) -> LigneForm:
        initial = initial or {"date": timezone.localdate(), "quantite": 1, "marge_unitaire": self.societe.marge_defaut}
        return LigneForm(data, initial=initial, societe=self.societe, clients=self.clients, auto_id=self.prefixe_ids)

    def enregistrer(self, form, ligne=None):
        """
        Enregistre via les services et renvoie (ligne, seuils franchis) ; None si le modèle refuse
        les données (les erreurs sont alors ajoutées au formulaire).
        """
        donnees = form.donnees()
        mois = premier_du_mois(donnees["date"])
        avant = etat_du_mois(self.societe, mois)
        try:
            if ligne is None:
                ligne = services.creer_ligne(self.request.user, self.societe, **donnees)
            else:
                ligne = services.modifier_ligne(self.request.user, ligne, **donnees)
        except ValidationError as erreur:
            form.ajouter_erreurs(erreur)
            return None, set()
        return ligne, services.franchissements(avant, etat_du_mois(self.societe, mois))

    def reponse_enregistrement(self, reponse, ligne, seuils, message):
        """Évènements HTMX (rafraîchissements, toast, confettis) ou messages Django (sans JavaScript)."""
        mois = premier_du_mois(ligne.date)
        if self.est_htmx:
            declencher(reponse, lignesModifiees=True, toast=toast(message))
            return declencher(reponse, **evenements_franchissement(seuils, self.societe, mois))
        messages.success(self.request, message)
        if "objectif_atteint" in seuils:
            messages.success(self.request, f"🎉 Objectif {self.societe.code.upper()} de {mois_long(mois)} atteint !",
                             extra_tags="objectif")
        if "charges_couvertes" in seuils:
            messages.success(self.request, f"✔ Charges {self.societe.code.upper()} de {mois_long(mois)} couvertes")
        return reponse


class LignesView(LignesMixin, PageSocieteMixin, TemplateView):
    """Liste filtrée des lignes + formulaire d'ajout (si l'utilisateur peut saisir)."""

    template_name = "interface/lignes.html"
    section = "lignes"

    def get_template_names(self):
        if self.est_htmx and self.request.headers.get("HX-Target") == "liste-lignes":
            return ["partials/lignes_liste.html"]
        return [self.template_name]

    def get_context_data(self, form=None, **kwargs):
        contexte = super().get_context_data(**kwargs)
        filtres = FiltresLignesForm(self.request.GET or None, clients=self.clients,
                                    projets=projets_de_la_societe(self.societe), periodes=PERIODES,
                                    initial={"periode": "mois"}, auto_id="filtre_%s")
        valeurs = filtres.valeurs()
        qs = lignes_filtrees(self.societe, self.mois, **valeurs)
        page = Paginator(qs, LIGNES_PAR_PAGE).get_page(self.request.GET.get("page"))
        user = self.request.user
        for ligne in page:
            ligne.peut_modifier = acces.peut_modifier_ligne(user, ligne)
            ligne.peut_supprimer = acces.peut_supprimer_ligne(user, ligne)
        parametres = self.request.GET.copy()
        parametres.pop("page", None)
        peut_saisir = acces.peut_saisir(user, self.societe)
        contexte.update(
            filtres=filtres, periode=valeurs["periode"], page=page, totaux=totaux(qs),
            parametres=parametres.urlencode(), peut_saisir=peut_saisir,
            form=form or (self.formulaire() if peut_saisir else None),
            regle_apercu=contexte["regle_pied"],
        )
        return contexte

    def post(self, request, *args, **kwargs):
        """Ajout d'une ligne (Responsable, Saisie, Admin groupe)."""
        if not acces.peut_saisir(request.user, self.societe):
            acces.refuser(request.user, "creer_ligne", societe=self.societe.code)
        form = self.formulaire(request.POST)
        ligne, seuils = self.enregistrer(form) if form.is_valid() else (None, set())
        if ligne is None:
            if self.est_htmx:
                return self.render_fragment_formulaire(form, status=422)
            return self.render_to_response(self.get_context_data(form=form), status=422)
        message = _libelle(self.societe, "ajouté")
        if self.est_htmx:
            # Formulaire vidé, mais date, client et marge gardés pour enchaîner les saisies.
            suivant = self.formulaire(initial={"date": ligne.date, "client": ligne.client_id or "",
                                               "marge_unitaire": ligne.marge_unitaire, "quantite": 1})
            return self.reponse_enregistrement(self.render_fragment_formulaire(suivant), ligne, seuils, message)
        return self.reponse_enregistrement(redirect(request.get_full_path()), ligne, seuils, message)

    def render_fragment_formulaire(self, form, status=200):
        contexte = {"form": form, "societe": self.societe, "regle_apercu": regle_en_vigueur()}
        return TemplateResponse(self.request, "partials/ligne_form.html", contexte, status=status)


class ApercuView(PageSocieteMixin, TemplateView):
    """Fragment HTMX : marge totale et 5 parts, calculées côté serveur par calculer_repartition."""

    template_name = "partials/apercu.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        try:
            quantite = int(self.request.GET.get("quantite", ""))
            marge_unitaire = Decimal(self.request.GET.get("marge_unitaire", ""))
        except (ValueError, InvalidOperation):
            quantite, marge_unitaire = 0, Decimal("0")
        try:
            le = date.fromisoformat(self.request.GET.get("date", ""))
        except ValueError:
            le = timezone.localdate()
        repartition = regle = None
        if quantite > 0 and marge_unitaire > 0:
            try:
                regle = RegleRepartition.objects.en_vigueur(le)
                repartition = calculer_repartition(quantite * marge_unitaire, regle)
            except RegleRepartition.DoesNotExist:
                pass
        contexte.update(repartition=repartition, regle=regle, date_apercu=le)
        return contexte


class LigneMixin(LignesMixin):
    """Charge la ligne `pk` de la société (404 si elle n'en fait pas partie)."""

    corbeille = False

    @cached_property
    def ligne(self) -> Ligne:
        source = Ligne.tous if self.corbeille else Ligne.objects
        return get_object_or_404(source.select_related("client"), societe=self.societe, pk=self.kwargs["pk"])


class LigneModifierView(LigneMixin, PageSocieteMixin, TemplateView):
    """Modification dans une boîte de dialogue (HTMX) ou sur une page (sans JavaScript)."""

    section = "lignes"
    prefixe_ids = "modif_%s"  # pas d'identifiants en double avec le formulaire d'ajout de la page

    def get_template_names(self):
        return ["partials/ligne_modifier.html"] if self.est_htmx else ["interface/ligne_modifier.html"]

    def verifier_droit(self, request) -> None:
        if not acces.peut_modifier_ligne(request.user, self.ligne):
            acces.refuser(request.user, "modifier_ligne", ligne=self.ligne.pk)

    def get_context_data(self, form=None, **kwargs):
        contexte = super().get_context_data(**kwargs)
        initial = {champ: getattr(self.ligne, champ) for champ in LigneForm.ORDRE if champ != "client"}
        initial["client"] = self.ligne.client_id or ""
        contexte.update(ligne=self.ligne, form=form or self.formulaire(initial=initial),
                        regle_apercu=contexte["regle_pied"])
        return contexte

    def post(self, request, *args, **kwargs):
        form = self.formulaire(request.POST)
        ligne, seuils = self.enregistrer(form, self.ligne) if form.is_valid() else (None, set())
        if ligne is None:
            return self.render_to_response(self.get_context_data(form=form), status=422)
        message = _libelle(self.societe, "modifié")
        if self.est_htmx:
            reponse = declencher(HttpResponse(status=204), fermerDialogue=True)
            return self.reponse_enregistrement(reponse, ligne, seuils, message)
        return self.reponse_enregistrement(redirect("interface:lignes", code_societe=self.societe.code),
                                           ligne, seuils, message)


class LigneSupprimerView(LigneMixin, PageSocieteMixin, TemplateView):
    """Suppression douce ; en HTMX, la ligne disparaît et le toast propose « Annuler »."""

    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        services.supprimer_ligne(request.user, self.ligne)
        message = f"{_libelle(self.societe, 'supprimé')} : {self.ligne.reference} du {self.ligne.date:%d/%m/%Y}"
        if self.est_htmx:
            url_restaurer = reverse("interface:ligne_restaurer", args=[self.societe.code, self.ligne.pk])
            return declencher(HttpResponse(""), lignesModifiees=True,
                              toast=toast(message, action={"libelle": "Annuler", "url": url_restaurer}))
        messages.success(request, message + " (restaurable depuis la corbeille).")
        return redirect("interface:lignes", code_societe=self.societe.code)


class LigneRestaurerView(LigneMixin, PageSocieteMixin, TemplateView):
    corbeille = True
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        services.restaurer_ligne(request.user, self.ligne)
        message = _libelle(self.societe, "restauré")
        if self.est_htmx:
            return declencher(HttpResponse(""), lignesModifiees=True, toast=toast(message))
        messages.success(request, message)
        return redirect("interface:corbeille", code_societe=self.societe.code)


class CorbeilleView(GestionSocieteMixin, TemplateView):
    """Lignes supprimées (Responsable, Admin groupe) : restauration possible."""

    template_name = "interface/corbeille.html"
    section = "corbeille"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        lignes = (Ligne.tous.supprimes().filter(societe=self.societe).select_related("client")
                  .order_by("-supprime_le"))
        contexte["page"] = Paginator(lignes, LIGNES_PAR_PAGE).get_page(self.request.GET.get("page"))
        return contexte
