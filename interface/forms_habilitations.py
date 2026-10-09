"""Formulaires de l'écran « Habilitations » (admin groupe). Les règles métier restent dans comptes/services.py."""
from django import forms

from comptes.models import Affectation, HabilitationVueGroupe, Utilisateur
from societes.models import Societe

ROLES_ACCES = [("", "Aucun")] + [(valeur, libelle) for valeur, libelle in Affectation.Role.choices]
OUI_NON = [("", "Tous"), ("oui", "Oui"), ("non", "Non")]


def _date(libelle):
    return forms.DateField(label=libelle, required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))


class AccesSocietesForm(forms.Form):
    """Un rôle (Aucun / Lecture / Saisie / Responsable) et des dates facultatives par société active."""

    def __init__(self, *args, affectations=None, **kwargs):
        """`affectations` : {id société: Affectation active} pour pré-remplir (fiche d'un utilisateur existant)."""
        super().__init__(*args, **kwargs)
        self.societes = list(Societe.objects.filter(actif=True))
        for s in self.societes:
            self.fields[f"role_{s.code}"] = forms.ChoiceField(label=f"Rôle sur {s.nom}", choices=ROLES_ACCES, required=False)
            self.fields[f"debut_{s.code}"] = _date(f"{s.nom} : valable à partir du")
            self.fields[f"fin_{s.code}"] = _date(f"{s.nom} : valable jusqu'au")
            existante = (affectations or {}).get(s.pk)
            if existante is not None and not self.is_bound:
                self.initial[f"role_{s.code}"] = existante.role
                self.initial[f"debut_{s.code}"] = existante.date_debut
                self.initial[f"fin_{s.code}"] = existante.date_fin

    def lignes(self):
        """Pour le gabarit : (société, champ rôle, champ début, champ fin)."""
        return [(s, self[f"role_{s.code}"], self[f"debut_{s.code}"], self[f"fin_{s.code}"]) for s in self.societes]

    def clean(self):
        donnees = super().clean()
        for s in self.societes:
            debut, fin = donnees.get(f"debut_{s.code}"), donnees.get(f"fin_{s.code}")
            if debut and fin and fin < debut:
                self.add_error(f"fin_{s.code}", f"{s.code.upper()} : la date de fin précède la date de début.")
        return donnees

    def demandes(self) -> dict:
        """{code société: {role, date_debut, date_fin}} pour chaque société du formulaire."""
        return {s.code: {"societe": s, "role": self.cleaned_data.get(f"role_{s.code}") or "",
                         "date_debut": self.cleaned_data.get(f"debut_{s.code}"),
                         "date_fin": self.cleaned_data.get(f"fin_{s.code}")} for s in self.societes}


class VueGroupeForm(forms.Form):
    autoriser = forms.BooleanField(label="Autoriser la Vue Groupe", required=False)
    portee = forms.ChoiceField(label="Portée", choices=HabilitationVueGroupe.Portee.choices, required=False,
                               widget=forms.RadioSelect, initial=HabilitationVueGroupe.Portee.TOUTES)
    societes = forms.ModelMultipleChoiceField(label="Sociétés de la portée", required=False, to_field_name="code",
                                              queryset=Societe.objects.none(), widget=forms.CheckboxSelectMultiple)
    detail_autorise = forms.BooleanField(
        label="Autoriser l'accès au détail (lecture seule) des sociétés de la portée", required=False,
        help_text="Tableau de bord et liste des lignes de ces sociétés. Sinon : uniquement les chiffres consolidés.")
    date_debut = _date("Valable à partir du")
    date_fin = _date("Valable jusqu'au")

    def __init__(self, *args, habilitation=None, avec_motif=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["societes"].queryset = Societe.objects.filter(actif=True)
        if avec_motif:
            self.fields["motif"] = forms.CharField(label="Motif (obligatoire)", max_length=255, required=False)
        if habilitation is not None and habilitation.actif and not self.is_bound:
            self.initial.update(autoriser=True, portee=habilitation.portee, detail_autorise=habilitation.detail_autorise,
                                date_debut=habilitation.date_debut, date_fin=habilitation.date_fin,
                                societes=list(habilitation.societes.values_list("code", flat=True)))

    def clean(self):
        donnees = super().clean()
        if not donnees.get("autoriser"):
            return donnees
        if donnees.get("date_debut") and donnees.get("date_fin") and donnees["date_fin"] < donnees["date_debut"]:
            self.add_error("date_fin", "La date de fin précède la date de début.")
        portee = donnees.get("portee") or HabilitationVueGroupe.Portee.TOUTES
        if portee == HabilitationVueGroupe.Portee.SELECTION and len(donnees.get("societes") or []) < 2:
            self.add_error("societes", "Cochez au moins 2 sociétés : sinon ce n'est plus une vue consolidée.")
        if "motif" in self.fields and not (donnees.get("motif") or "").strip():
            self.add_error("motif", "Un motif est obligatoire pour une habilitation Vue Groupe.")
        return donnees


class RoleGlobalForm(forms.Form):
    role_global = forms.ChoiceField(label="Rôle groupe", choices=Utilisateur.RoleGlobal.choices, required=False)
    motif = forms.CharField(label="Motif", max_length=255, required=False)


class MotifForm(forms.Form):
    motif = forms.CharField(label="Motif", max_length=255, required=False)


class FiltresUtilisateursForm(forms.Form):
    q = forms.CharField(label="Rechercher", required=False, max_length=100,
                        widget=forms.TextInput(attrs={"type": "search", "placeholder": "nom ou e-mail"}))
    societe = forms.ChoiceField(label="Société", required=False)
    vue_groupe = forms.ChoiceField(label="Vue Groupe", required=False, choices=OUI_NON)
    actif = forms.ChoiceField(label="Compte actif", required=False, choices=OUI_NON)
    mfa_manquante = forms.BooleanField(label="2FA manquante", required=False)
    expire_bientot = forms.BooleanField(label="Expire sous 30 jours", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["societe"].choices = [("", "Toutes")] + [(s.code, s.nom) for s in Societe.objects.filter(actif=True)]


class NouvelUtilisateurForm(forms.Form):
    prenom = forms.CharField(label="Prénom", max_length=150)
    nom = forms.CharField(label="Nom", max_length=150)
    email = forms.EmailField(label="Adresse e-mail")
    telephone = forms.CharField(label="Téléphone", max_length=30, required=False)
    role_global = forms.ChoiceField(label="Rôle groupe", choices=Utilisateur.RoleGlobal.choices, required=False)
