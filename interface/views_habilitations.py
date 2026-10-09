"""
Écran « Habilitations » (admin groupe) : liste, fiche d'un utilisateur, matrice, création de compte.
Toute modification passe par `comptes/services.py` (motifs, journal, sessions). Réservé à `peut_administrer` : 404 sinon.
"""
import csv

from allauth.mfa.models import Authenticator
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, Prefetch, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.views.generic import TemplateView

from comptes import acces, services
from comptes.models import Affectation, HabilitationVueGroupe, Utilisateur

from . import habilitations as logique
from .contexte import InterfaceMixin
from .forms_habilitations import (AccesSocietesForm, FiltresUtilisateursForm, MotifForm, NouvelUtilisateurForm,
                                  RoleGlobalForm, VueGroupeForm)


class AdminHabilitationsMixin(InterfaceMixin):
    """Page réservée à l'administrateur groupe (404 pour les autres, accès refusé journalisé)."""

    section = "habilitations"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not acces.peut_administrer(request.user):
            acces.signaler_refus(request.user, "habilitations", chemin=request.path)
            raise Http404("Page introuvable.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["onglet_habilitations"] = self.onglet_habilitations
        return contexte

    onglet_habilitations = "utilisateurs"


# --- Liste des utilisateurs -------------------------------------------------------------------------

class UtilisateursView(AdminHabilitationsMixin, TemplateView):
    template_name = "interface/habilitations.html"

    def get_template_names(self):
        return ["partials/habilitations_liste.html"] if self.est_htmx else [self.template_name]

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        aujourd_hui = timezone.localdate()
        formulaire = FiltresUtilisateursForm(self.request.GET or None)
        formulaire.is_valid()
        f = getattr(formulaire, "cleaned_data", {})

        utilisateurs = Utilisateur.objects.all()
        if f.get("q"):
            for mot in f["q"].split():
                utilisateurs = utilisateurs.filter(Q(first_name__icontains=mot) | Q(last_name__icontains=mot)
                                                   | Q(email__icontains=mot))
        if f.get("actif"):
            utilisateurs = utilisateurs.filter(is_active=f["actif"] == "oui")
        if f.get("societe"):
            utilisateurs = utilisateurs.filter(
                Exists(Affectation.objects.filter(utilisateur=OuterRef("pk"), actif=True, societe__code=f["societe"]))
                | Exists(HabilitationVueGroupe.objects.filter(utilisateur=OuterRef("pk"), actif=True,
                                                              portee=HabilitationVueGroupe.Portee.TOUTES))
                | Exists(HabilitationVueGroupe.objects.filter(utilisateur=OuterRef("pk"), actif=True,
                                                              societes__code=f["societe"])))
        en_vigueur = Exists(HabilitationVueGroupe.objects.en_vigueur().filter(utilisateur=OuterRef("pk")))
        if f.get("vue_groupe") == "oui":
            utilisateurs = utilisateurs.filter(en_vigueur)
        elif f.get("vue_groupe") == "non":
            utilisateurs = utilisateurs.filter(~en_vigueur)
        avec_totp = Exists(Authenticator.objects.filter(user=OuterRef("pk"), type=Authenticator.Type.TOTP))
        if f.get("mfa_manquante"):
            utilisateurs = utilisateurs.filter(~avec_totp)
        if f.get("expire_bientot"):
            debut, fin = logique.expire_dans(30)
            utilisateurs = utilisateurs.filter(
                Exists(Affectation.objects.en_vigueur().filter(utilisateur=OuterRef("pk"), date_fin__range=(debut, fin)))
                | Exists(HabilitationVueGroupe.objects.en_vigueur().filter(utilisateur=OuterRef("pk"),
                                                                           date_fin__range=(debut, fin))))

        utilisateurs = (utilisateurs.select_related("habilitation_groupe")
                        .prefetch_related(Prefetch("affectations", queryset=Affectation.objects.filter(actif=True)
                                                   .select_related("societe").order_by("societe__ordre")),
                                          "habilitation_groupe__societes")
                        .order_by("last_name", "first_name", "email"))
        avec_mfa = set(Authenticator.objects.filter(type=Authenticator.Type.TOTP).values_list("user_id", flat=True))
        lignes = [{"u": u, "mfa": u.pk in avec_mfa, "badges": logique.badges_acces(u, aujourd_hui),
                   "groupe": logique.resume_vue_groupe(u, aujourd_hui)} for u in utilisateurs]
        contexte.update(formulaire=formulaire, lignes=lignes, aujourd_hui=aujourd_hui)
        return contexte


# --- Fiche d'un utilisateur -------------------------------------------------------------------------

class FicheView(AdminHabilitationsMixin, TemplateView):
    template_name = "interface/habilitation_fiche.html"

    @cached_property
    def cible(self):
        return get_object_or_404(Utilisateur, pk=self.kwargs["pk"])

    def formulaires(self, **liees):
        affectations = {a.societe_id: a for a in Affectation.objects.filter(utilisateur=self.cible, actif=True)}
        habilitation = HabilitationVueGroupe.objects.filter(utilisateur=self.cible).first()
        return {
            "form_acces": liees.get("acces") or AccesSocietesForm(affectations=affectations),
            "form_groupe": liees.get("vue_groupe") or VueGroupeForm(habilitation=habilitation),
            "form_role": RoleGlobalForm(initial={"role_global": self.cible.role_global}),
            "form_motif": MotifForm(),
        }

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["cible"] = self.cible
        contexte["apercu"] = logique.apercu_droits(self.cible)
        contexte["mfa"] = Authenticator.objects.filter(user=self.cible, type=Authenticator.Type.TOTP).exists()
        for cle, valeur in self.formulaires(**kwargs.get("liees", {})).items():
            contexte.setdefault(cle, valeur)
        return contexte

    def post(self, request, *args, **kwargs):
        bloc = request.POST.get("bloc", "")
        if bloc in ("acces", "vue_groupe"):
            return self.traiter_bloc(request, bloc)
        try:
            if bloc == "role_global":
                formulaire = RoleGlobalForm(request.POST)
                if formulaire.is_valid():
                    services.definir_role_global(request.user, self.cible, formulaire.cleaned_data["role_global"],
                                                 motif=formulaire.cleaned_data["motif"])
                    messages.success(request, "Rôle groupe enregistré.")
            elif bloc == "activer":
                services.activer_compte(request.user, self.cible)
                messages.success(request, "Compte activé.")
            elif bloc == "desactiver":
                services.desactiver_compte(request.user, self.cible, motif=request.POST.get("motif", ""))
                messages.success(request, "Compte désactivé ; ses sessions ont été fermées.")
            else:
                raise Http404("Action inconnue.")
        except ValidationError as erreur:
            messages.error(request, " ".join(erreur.messages))
        except PermissionDenied:
            messages.error(request, "Action refusée : seul un superutilisateur peut retirer le rôle d'administrateur groupe.")
        return redirect("interface:habilitation_fiche", pk=self.cible.pk)

    def traiter_bloc(self, request, bloc):
        """Accès société ou Vue Groupe : formulaire → résumé à confirmer (avec motif) → application par les services."""
        if bloc == "acces":
            formulaire = AccesSocietesForm(request.POST)
        else:
            formulaire = VueGroupeForm(request.POST)
        if not formulaire.is_valid():
            contexte = self.get_context_data(liees={bloc: formulaire})
            return self.render_to_response(contexte, status=422)

        if bloc == "acces":
            plan = logique.plan_acces(self.cible, formulaire.demandes())
            textes = [c.texte for c in plan]
            motif_obligatoire = any(c.genre == "retirer" for c in plan)
        else:
            changement = logique.plan_vue_groupe(self.cible, formulaire.cleaned_data)
            plan = [changement] if changement else []
            textes = [changement.texte] if changement else []
            motif_obligatoire = True
        if not plan:
            messages.info(request, "Aucun changement à enregistrer.")
            return redirect("interface:habilitation_fiche", pk=self.cible.pk)

        motif = request.POST.get("motif", "").strip()
        if request.POST.get("etape") == "confirmer":
            if motif_obligatoire and not motif:
                return self.confirmation(request, textes, motif, "Un motif est obligatoire.", motif_obligatoire)
            try:
                with transaction.atomic():
                    if bloc == "acces":
                        logique.appliquer_acces(request.user, self.cible, plan, motif)
                    else:
                        logique.appliquer_vue_groupe(request.user, self.cible, plan[0], motif)
            except ValidationError as erreur:
                return self.confirmation(request, textes, motif, " ".join(erreur.messages), motif_obligatoire)
            messages.success(request, "Habilitations enregistrées : " + " ; ".join(textes) + ".")
            return redirect("interface:habilitation_fiche", pk=self.cible.pk)
        return self.confirmation(request, textes, motif, "", motif_obligatoire)

    def confirmation(self, request, textes, motif, erreur, motif_obligatoire):
        champs = [(nom, valeur) for nom, valeurs in request.POST.lists()
                  if nom not in ("csrfmiddlewaretoken", "etape", "motif") for valeur in valeurs]
        contexte = self.get_context_data(liees={})
        contexte.update(textes=textes, champs=champs, motif=motif, erreur_motif=erreur, motif_obligatoire=motif_obligatoire)
        return render(request, "interface/habilitation_confirmation.html", contexte, status=422 if erreur else 200)


# --- Matrice --------------------------------------------------------------------------------------

class MatriceView(AdminHabilitationsMixin, TemplateView):
    template_name = "interface/habilitations_matrice.html"
    onglet_habilitations = "matrice"

    def utilisateurs(self):
        return Utilisateur.objects.filter(is_active=True).order_by("last_name", "first_name", "email")

    def get(self, request, *args, **kwargs):
        societes, lignes = logique.matrice(self.utilisateurs())
        if request.GET.get("format") == "csv":
            reponse = HttpResponse(content_type="text/csv; charset=utf-8")
            reponse["Content-Disposition"] = 'attachment; filename="matrice-habilitations.csv"'
            reponse.write("﻿")  # BOM : Excel reconnaît l'UTF-8
            ecrivain = csv.writer(reponse, delimiter=";", lineterminator="\n")
            ecrivain.writerow(["Utilisateur", "E-mail"] + [s.code.upper() for s in societes] + ["Vue Groupe"])
            for ligne in lignes:
                ecrivain.writerow([ligne["utilisateur"].get_full_name(), ligne["utilisateur"].email]
                                  + [c["lettre"] for c in ligne["cellules"]] + [ligne["groupe"]["lettre"]])
            return reponse
        self.societes, self.lignes = societes, lignes
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte.update(societes_matrice=self.societes, lignes=self.lignes, legende=logique.LIBELLES_LETTRES)
        return contexte


# --- Création d'un compte --------------------------------------------------------------------------

class NouvelUtilisateurView(AdminHabilitationsMixin, TemplateView):
    template_name = "interface/habilitation_nouveau.html"
    onglet_habilitations = "nouveau"

    def formulaires(self, donnees=None):
        return {"form_compte": NouvelUtilisateurForm(donnees), "form_acces": AccesSocietesForm(donnees),
                "form_groupe": VueGroupeForm(donnees, avec_motif=True)}

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        for cle, valeur in self.formulaires().items():
            contexte.setdefault(cle, valeur)
        return contexte

    def post(self, request, *args, **kwargs):
        formulaires = self.formulaires(request.POST)
        if not all(f.is_valid() for f in formulaires.values()):
            return self.render_to_response(self.get_context_data(**formulaires), status=422)
        compte, acces_f, groupe_f = (formulaires["form_compte"].cleaned_data, formulaires["form_acces"],
                                     formulaires["form_groupe"].cleaned_data)
        demandes = [d for d in acces_f.demandes().values() if d["role"]]
        vue_groupe = None
        if groupe_f.get("autoriser"):
            portee = groupe_f.get("portee") or HabilitationVueGroupe.Portee.TOUTES
            vue_groupe = {"portee": portee, "detail_autorise": groupe_f["detail_autorise"], "motif": groupe_f["motif"],
                          "societes": [] if portee == HabilitationVueGroupe.Portee.TOUTES else list(groupe_f["societes"]),
                          "date_debut": groupe_f.get("date_debut"), "date_fin": groupe_f.get("date_fin")}
        try:
            with transaction.atomic():
                utilisateur, mot_de_passe = services.creer_compte(
                    request.user, email=compte["email"], nom=compte["nom"], prenom=compte["prenom"],
                    telephone=compte["telephone"], role_global=compte["role_global"], acces_societes=demandes,
                    vue_groupe=vue_groupe)
        except ValidationError as erreur:
            formulaires["form_compte"].add_error(None, erreur.messages)
            return self.render_to_response(self.get_context_data(**formulaires), status=422)
        # Le mot de passe provisoire n'est affiché qu'ici, une seule fois : pas de redirection, pas de mise en cache.
        reponse = render(request, "interface/habilitation_cree.html",
                         {**self.get_context_data(**self.formulaires()), "nouveau": utilisateur, "mot_de_passe": mot_de_passe})
        reponse["Cache-Control"] = "no-store"
        return reponse
