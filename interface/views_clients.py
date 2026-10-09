"""
Clients d'une société (lot 3.4). Lecture pour tous les rôles de la société ; ajout, modification
et retrait (suppression douce) pour le Responsable et l'Admin groupe, via societes.services.
"""
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.utils.functional import cached_property
from django.views.generic import TemplateView

from comptes import acces
from operations.selectors import clients_avec_nb_lignes
from societes import services
from societes.models import Client

from .contexte import GestionSocieteMixin, PageSocieteMixin
from .forms import ClientForm, LigneForm
from .htmx import declencher, toast


class ClientsView(PageSocieteMixin, TemplateView):
    """Liste des clients avec leur nombre de lignes ; formulaire d'ajout pour Responsable / Admin."""

    template_name = "interface/clients.html"
    section = "clients"

    def get_template_names(self):
        return ["partials/clients.html"] if self.est_htmx else [self.template_name]

    def get_context_data(self, form=None, **kwargs):
        contexte = super().get_context_data(**kwargs)
        q = self.request.GET.get("q", "").strip()
        clients = clients_avec_nb_lignes(self.societe)
        if q:  # recherche instantanée (HTMX) ; sans JavaScript, le même filtre passe par un envoi classique
            clients = clients.filter(Q(nom__icontains=q) | Q(telephone__icontains=q) | Q(email__icontains=q))
        contexte["clients"] = clients
        contexte["q"] = q
        contexte["form"] = form or ClientForm(auto_id="client_%s")
        return contexte

    def post(self, request, *args, **kwargs):
        if not acces.peut_gerer_societe(request.user, self.societe):
            acces.refuser(request.user, "ajouter_client", societe=self.societe.code)
        rapide = request.POST.get("rapide") == "1"  # ajout rapide depuis la page de saisie
        form = ClientForm(request.POST, auto_id="rapide_%s" if rapide else "client_%s")
        client = None
        if form.is_valid():
            try:
                client = services.ajouter_client(request.user, self.societe, **form.cleaned_data)
            except ValidationError as erreur:
                form.ajouter_erreurs(erreur)
        # Ajout rapide (page de saisie) ou fenêtre « Nouveau client » (page Clients) : deux fragments de formulaire.
        gabarit = "partials/client_rapide.html" if rapide else "partials/client_ajout.html"
        if client is None:
            if not self.est_htmx:
                return self.render_to_response(self.get_context_data(form=form), status=422)
            return TemplateResponse(request, gabarit, {"form": form, "societe": self.societe}, status=422)
        message = f"Client ajouté : {client.nom}"
        if not self.est_htmx:
            messages.success(request, message)
            return redirect(request.POST.get("retour") or request.path)
        vierge = ClientForm(auto_id="rapide_%s" if rapide else "client_%s")
        reponse = declencher(TemplateResponse(request, gabarit, {"form": vierge, "societe": self.societe}),
                             clientsModifies={"id": client.pk, "nom": client.nom}, toast=toast(message))
        return reponse if rapide else declencher(reponse, fermerDialogue=True)  # la fenêtre se referme, la liste se rafraîchit


class ClientMixin:
    @cached_property
    def client(self) -> Client:
        return get_object_or_404(Client, societe=self.societe, pk=self.kwargs["pk"])


class ClientModifierView(ClientMixin, GestionSocieteMixin, TemplateView):
    section = "clients"

    def get_template_names(self):
        return ["partials/client_modifier.html"] if self.est_htmx else ["interface/client_modifier.html"]

    def get_context_data(self, form=None, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(client=self.client, form=form or ClientForm(
            initial={"nom": self.client.nom, "telephone": self.client.telephone, "email": self.client.email},
            auto_id="modif_client_%s"))
        return contexte

    def post(self, request, *args, **kwargs):
        form = ClientForm(request.POST, auto_id="modif_client_%s")
        if form.is_valid():
            try:
                services.modifier_client(request.user, self.client, **form.cleaned_data)
            except ValidationError as erreur:
                form.ajouter_erreurs(erreur)
        if form.errors:
            return self.render_to_response(self.get_context_data(form=form), status=422)
        message = f"Client modifié : {self.client.nom}"
        if self.est_htmx:
            return declencher(HttpResponse(status=204), fermerDialogue=True, clientsModifies={"id": self.client.pk},
                              toast=toast(message))
        messages.success(request, message)
        return redirect("interface:clients", code_societe=self.societe.code)


class ClientRetirerView(ClientMixin, GestionSocieteMixin, TemplateView):
    """Suppression douce : les lignes existantes gardent leur client."""

    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        services.retirer_client(request.user, self.client)
        message = f"Client retiré : {self.client.nom}"
        if self.est_htmx:
            return declencher(HttpResponse(""), clientsModifies={"id": self.client.pk}, toast=toast(message))
        messages.success(request, message)
        return redirect("interface:clients", code_societe=self.societe.code)


class ChampClientView(PageSocieteMixin, TemplateView):
    """Fragment HTMX : liste déroulante des clients du formulaire de saisie, rafraîchie après un ajout."""

    template_name = "partials/champ_client.html"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        clients = list(Client.objects.filter(societe=self.societe).order_by("nom"))
        form = LigneForm(initial={"client": self.request.GET.get("client", "")}, societe=self.societe,
                         clients=clients)
        contexte["form"] = form
        return contexte
