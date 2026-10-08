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
