"""Journal de sécurité (admin groupe) et page « Mon compte » (tout utilisateur connecté)."""
import csv
import json

from allauth.mfa.models import Authenticator
from django import forms
from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from django.views.generic import TemplateView

from comptes import acces
from comptes.models import Affectation, JournalSecurite

from . import habilitations as logique
from .contexte import InterfaceMixin
from .views_habilitations import AdminHabilitationsMixin

E = JournalSecurite.Evenement
PAR_PAGE = 50
EXPORT_MAX = 5000

# Famille d'un événement : sert à l'icône ET à une étiquette texte (la couleur ne porte jamais l'information seule).
FAMILLES = {
    E.CONNEXION: "acces", E.DECONNEXION: "acces",
    E.ECHEC_CONNEXION: "alerte", E.COMPTE_BLOQUE: "alerte", E.ACCES_REFUSE: "alerte",
    E.MFA_ACTIVEE: "securite", E.MFA_DESACTIVEE: "securite", E.MOT_DE_PASSE_CHANGE: "securite",
}
LIBELLES_FAMILLES = {"acces": "Accès", "alerte": "Alerte", "securite": "Sécurité", "droits": "Droits"}


def famille(evenement: str) -> str:
    return FAMILLES.get(evenement, "droits")


def _texte(valeur) -> str:
    if isinstance(valeur, bool):
        return "oui" if valeur else "non"
    if valeur in (None, "", []):
        return "—"
    if isinstance(valeur, (list, tuple)):
        return ", ".join(_texte(v) for v in valeur)
    if isinstance(valeur, dict):
        return "; ".join(f"{k} : {_texte(v)}" for k, v in valeur.items())
    return str(valeur)


def lignes_detail(valeur) -> list[tuple[str, str]]:
    return [(cle, _texte(v)) for cle, v in valeur.items()] if isinstance(valeur, dict) else []


def preparer(entree) -> dict:
    """Une entrée du journal prête pour l'affichage : famille, détails à plat, avant/après en deux colonnes."""
    details = entree.details or {}
    autres = {k: v for k, v in details.items() if k not in ("avant", "apres")}
    fam = famille(entree.evenement)
    return {
        "e": entree, "famille": fam, "libelle_famille": LIBELLES_FAMILLES[fam],
        "autres": lignes_detail(autres), "avant": lignes_detail(details.get("avant")),
        "apres": lignes_detail(details.get("apres")), "a_detail": bool(details),
    }


class FiltresJournalForm(forms.Form):
    evenement = forms.ChoiceField(label="Événement", required=False)
    q = forms.CharField(label="Utilisateur", required=False, max_length=100,
                        widget=forms.TextInput(attrs={"type": "search", "placeholder": "e-mail ou identifiant"}))
    du = forms.DateField(label="Du", required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    au = forms.DateField(label="Au", required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["evenement"].choices = [("", "Tous les événements")] + list(E.choices)

    def appliquer(self, qs):
        self.is_valid()
        f = getattr(self, "cleaned_data", {})
        if f.get("evenement"):
            qs = qs.filter(evenement=f["evenement"])
        if f.get("q"):
            qs = qs.filter(Q(utilisateur__email__icontains=f["q"]) | Q(identifiant_saisi__icontains=f["q"])
                           | Q(details__cible_email__icontains=f["q"]))
        if f.get("du"):
            qs = qs.filter(date__date__gte=f["du"])
        if f.get("au"):
            qs = qs.filter(date__date__lte=f["au"])
        return qs


class JournalView(AdminHabilitationsMixin, TemplateView):
    """Journal de sécurité filtrable (événement, utilisateur, dates), avec pagination et export CSV. Admin groupe seulement."""

    template_name = "administration/journal.html"
    section = "journal"
    onglet_habilitations = "journal"

    def get(self, request, *args, **kwargs):
        self.filtres = FiltresJournalForm(request.GET or None)
        self.qs = self.filtres.appliquer(JournalSecurite.objects.select_related("utilisateur"))
        if request.GET.get("format") == "csv":
            return self.exporter()
        return super().get(request, *args, **kwargs)

    def exporter(self):
        reponse = HttpResponse(content_type="text/csv; charset=utf-8")
        reponse["Content-Disposition"] = 'attachment; filename="journal-securite.csv"'
        reponse["Cache-Control"] = "private, no-store"
        reponse.write("﻿")
        ecrivain = csv.writer(reponse, delimiter=";", lineterminator="\n")
        ecrivain.writerow(["Date", "Événement", "Utilisateur", "Identifiant saisi", "Adresse IP", "Détails"])
        for e in self.qs[:EXPORT_MAX]:
            ecrivain.writerow([f"{timezone.localtime(e.date):%d/%m/%Y %H:%M:%S}", e.get_evenement_display(),
                               e.utilisateur.email if e.utilisateur else "", e.identifiant_saisi, e.ip or "",
                               json.dumps(e.details, ensure_ascii=False)])
        return reponse

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        page = Paginator(self.qs, PAR_PAGE).get_page(self.request.GET.get("page"))
        parametres = self.request.GET.copy()
        parametres.pop("page", None)
        parametres.pop("format", None)
        contexte.update(formulaire=self.filtres, page=page, lignes=[preparer(e) for e in page],
                        parametres=parametres.urlencode(), familles=LIBELLES_FAMILLES)
        return contexte


class MonCompteView(InterfaceMixin, TemplateView):
    """Identité, accès, état de la 2FA et dernières connexions de l'utilisateur connecté (lecture seule)."""

    template_name = "comptes/mon_compte.html"
    section = "compte"

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        user = self.request.user
        aujourd_hui = timezone.localdate()
        affectations = list(Affectation.objects.filter(utilisateur=user, actif=True).select_related("societe")
                            .order_by("societe__ordre"))
        for a in affectations:
            a.etat = logique.etat_periode(a, aujourd_hui)
            a.role_court = logique.ROLES_COURTS[a.role]
        contexte.update(
            affectations=affectations,
            groupe=logique.resume_vue_groupe(user, aujourd_hui),
            est_admin=acces.est_admin_groupe(user),
            mfa=Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).exists(),
            mfa_obligatoire=bool(acces.roles_de(user) & set(settings.MFA_ROLES_OBLIGATOIRES)),
            connexions=[preparer(e) for e in JournalSecurite.objects.filter(
                utilisateur=user, evenement__in=[E.CONNEXION, E.ECHEC_CONNEXION]).order_by("-date")[:10]],
        )
        return contexte
