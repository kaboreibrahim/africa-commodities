"""Formulaires de l'interface. La validation métier reste dans les modèles et les services."""
from django import forms


class ObjectifForm(forms.Form):
    montant = forms.DecimalField(
        label="Objectif du mois (FCFA)", min_value=0, max_digits=16, decimal_places=0,
        widget=forms.NumberInput(attrs={"step": "10000", "inputmode": "numeric"}),
        help_text="Si aucun objectif n'est saisi pour un mois, celui du dernier mois renseigné s'applique.",
    )


class DepensesForm(forms.Form):
    montant = forms.DecimalField(
        label="Dépenses du mois (FCFA)", min_value=0, max_digits=16, decimal_places=0,
        help_text="Montant global réellement dépensé ce mois-ci (loyer, salaires, carburant…). "
                  "Il n'est pas reporté sur les mois suivants.",
    )
    note = forms.CharField(label="Note (facultatif)", max_length=255, required=False)


class LigneForm(forms.Form):
    """
    Saisie d'une ligne. Libellés et champ spécifique selon la société ; clients limités aux clients
    actifs de la société (liste déjà chargée). L'enregistrement passe par operations.services.
    """

    date = forms.DateField(label="Date", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    reference = forms.CharField(label="Référence", max_length=60)
    projet = forms.CharField(label="N° de projet", max_length=60, required=False,
                             widget=forms.TextInput(attrs={"placeholder": "ex : PRJ-2026-014"}))
    client = forms.ChoiceField(label="Client", required=False)
    quantite = forms.IntegerField(label="Quantité", min_value=1,
                                  widget=forms.NumberInput(attrs={"inputmode": "numeric", "min": "1"}))
    marge_unitaire = forms.DecimalField(label="Marge unitaire (FCFA)", min_value=1, max_digits=14, decimal_places=0,
                                        widget=forms.NumberInput(attrs={"inputmode": "numeric", "step": "1"}))
    observation = forms.CharField(label="Observation", max_length=255, required=False,
                                  widget=forms.TextInput(attrs={"placeholder": "facultatif"}))

    ORDRE = ["date", "extra", "reference", "projet", "client", "quantite", "marge_unitaire", "observation"]

    def __init__(self, *args, societe, clients, **kwargs):
        super().__init__(*args, **kwargs)
        self.societe = societe
        self.clients = {str(c.pk): c for c in clients}
        self.fields["reference"].label = societe.libelle_reference
        self.fields["quantite"].label = societe.libelle_quantite
        self.fields["marge_unitaire"].label = f"{societe.libelle_marge} (FCFA)"
        self.fields["client"].choices = [("", "— Choisir un client —")] + [(pk, c.nom) for pk, c in self.clients.items()]
        if societe.champ_extra_type == societe.TypeChampExtra.CHOIX:
            self.fields["extra"] = forms.ChoiceField(label=societe.champ_extra_libelle,
                                                     choices=[(c, c) for c in societe.choix_extra])
        elif societe.champ_extra_type == societe.TypeChampExtra.TEXTE:
            self.fields["extra"] = forms.CharField(label=societe.champ_extra_libelle, max_length=60, required=False)
        self.order_fields(self.ORDRE)

    def donnees(self) -> dict:
        """Données pour creer_ligne / modifier_ligne (le client devient un objet Client)."""
        donnees = dict(self.cleaned_data)
        donnees["client"] = self.clients.get(donnees.get("client") or "")
        return donnees

    def ajouter_erreurs(self, erreur) -> None:
        """Erreurs de validation du modèle (full_clean) affichées sous les champs concernés."""
        if hasattr(erreur, "error_dict"):
            for champ, messages in erreur.message_dict.items():
                self.add_error(champ if champ in self.fields else None, messages)
        else:
            self.add_error(None, erreur.messages)


class FiltresLignesForm(forms.Form):
    periode = forms.ChoiceField(label="Période", required=False)
    q = forms.CharField(label="Recherche", required=False, max_length=100,
                        widget=forms.TextInput(attrs={"type": "search", "placeholder": "réf., projet, client…"}))
    client = forms.ChoiceField(label="Client", required=False)
    projet = forms.ChoiceField(label="Projet", required=False)

    def __init__(self, *args, clients, projets, periodes, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["periode"].choices = list(periodes.items())
        self.fields["client"].choices = [("", "Tous les clients")] + [(str(c.pk), c.nom) for c in clients]
        self.fields["projet"].choices = [("", "Tous les projets")] + [(p, p) for p in projets]

    def valeurs(self) -> dict:
        """Filtres valides (une valeur inconnue est ignorée plutôt que de provoquer une erreur)."""
        self.is_valid()
        donnees = getattr(self, "cleaned_data", {})
        client = donnees.get("client") or ""
        return {
            "periode": donnees.get("periode") or "mois",
            "recherche": donnees.get("q", ""),
            "client_id": int(client) if client.isdigit() else None,
            "projet": donnees.get("projet", ""),
        }


class ClientForm(forms.Form):
    nom = forms.CharField(label="Nom du client", max_length=150)
    telephone = forms.CharField(label="Téléphone", max_length=30, required=False,
                                widget=forms.TextInput(attrs={"type": "tel", "autocomplete": "off"}))
    email = forms.EmailField(label="E-mail", required=False)

    def ajouter_erreurs(self, erreur) -> None:
        """Erreurs du modèle (doublon : « Ce client existe déjà pour cette société. »)."""
        if hasattr(erreur, "error_dict"):
            for champ, messages in erreur.message_dict.items():
                self.add_error(champ if champ in self.fields else "nom", messages)
        else:
            self.add_error("nom", erreur.messages)
