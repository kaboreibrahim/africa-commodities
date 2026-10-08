from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from simple_history.models import HistoricalRecords

from core.models import ActifQuerySet, SuppressionDouceMixin, TimestampMixin
from repartition.models import RegleRepartition
from repartition.services import calculer_repartition
from societes.models import Client, FiltreSocieteMixin, Societe

MONTANT = dict(max_digits=16, decimal_places=0)


class LigneQuerySet(FiltreSocieteMixin, ActifQuerySet):
    def du_mois(self, mois):
        return self.filter(date__year=mois.year, date__month=mois.month)

    def de_l_annee(self, annee: int):
        return self.filter(date__year=annee)

    def avec_relations(self):
        return self.select_related("societe", "client", "regle")


class LigneManager(models.Manager.from_queryset(LigneQuerySet)):
    def get_queryset(self):
        return super().get_queryset().filter(supprime_le__isnull=True)


class Ligne(TimestampMixin, SuppressionDouceMixin, models.Model):
    """
    Une ligne enregistrée : dossier (OOA, ANL, OTL), opération (ALON) ou lot de livraisons (MLP).

    La répartition (charges, Africa Commodities, risques, provision, comptes) est calculée
    et FIGÉE à l'enregistrement avec la règle en vigueur à la date de la ligne.
    """

    societe = models.ForeignKey(Societe, on_delete=models.PROTECT, related_name="lignes")
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="lignes", null=True, blank=True)
    date = models.DateField("date")
    reference = models.CharField("référence", max_length=60)
    projet = models.CharField("N° de projet", max_length=60, blank=True, db_index=True)
    extra = models.CharField("champ spécifique", max_length=60, blank=True, help_text="Type (ALON) / Zone (MLP)")
    quantite = models.PositiveIntegerField("quantité")
    marge_unitaire = models.DecimalField("marge unitaire (FCFA)", max_digits=14, decimal_places=0)
    observation = models.CharField("observation", max_length=255, blank=True)

    # --- Répartition figée (calculée, non modifiable à la main) ---
    regle = models.ForeignKey(RegleRepartition, on_delete=models.PROTECT, editable=False, related_name="lignes")
    marge_totale = models.DecimalField("marge totale", editable=False, **MONTANT)
    part_charges = models.DecimalField("charges", editable=False, **MONTANT)
    part_africa_commodities = models.DecimalField("Africa Commodities", editable=False, **MONTANT)
    part_risques = models.DecimalField("risques", editable=False, **MONTANT)
    part_provision = models.DecimalField("provision", editable=False, **MONTANT)
    part_comptes = models.DecimalField("comptes", editable=False, **MONTANT)

    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                 editable=False, related_name="lignes_creees")
    modifie_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    editable=False, related_name="lignes_modifiees", verbose_name="modifié par")

    objects = LigneManager()
    tous = LigneQuerySet.as_manager()
    history = HistoricalRecords()

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name = "ligne"
        verbose_name_plural = "lignes"
        indexes = [
            models.Index(fields=["societe", "date"], name="ligne_societe_date_idx"),
            models.Index(fields=["date"], name="ligne_date_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(quantite__gt=0), name="ligne_quantite_positive"),
            models.CheckConstraint(condition=models.Q(marge_unitaire__gt=0), name="ligne_marge_positive"),
            models.CheckConstraint(
                condition=models.Q(
                    marge_totale=models.F("part_charges") + models.F("part_africa_commodities")
                    + models.F("part_risques") + models.F("part_provision") + models.F("part_comptes")
                ),
                name="ligne_repartition_complete",
            ),
        ]

    def __str__(self):
        return f"{self.societe.code} · {self.reference} · {self.date:%d/%m/%Y}"

    # --- Validation métier ---
    def clean(self):
        erreurs = {}
        if self.client_id and self.societe_id and self.client.societe_id != self.societe_id:
            erreurs["client"] = "Ce client n'appartient pas à cette société."
        if self.societe_id:
            s = self.societe
            if s.champ_extra_type == Societe.TypeChampExtra.CHOIX and self.extra and self.extra not in s.choix_extra:
                erreurs["extra"] = f"Valeur autorisée : {', '.join(s.choix_extra)}."
            if not s.champ_extra_type and self.extra:
                erreurs["extra"] = "Cette société n'utilise pas de champ spécifique."
        if self.date and not RegleRepartition.objects.filter(date_debut__lte=self.date).exists():
            erreurs["date"] = "Aucune règle de répartition n'est en vigueur à cette date."
        if erreurs:
            raise ValidationError(erreurs)

    # --- Calcul figé ---
    def calculer(self):
        """(Re)calcule la marge totale et la répartition avec la règle en vigueur à la date de la ligne."""
        self.regle = RegleRepartition.objects.en_vigueur(self.date)
        self.marge_totale = self.quantite * self.marge_unitaire
        r = calculer_repartition(self.marge_totale, self.regle)
        self.part_charges = r.charges
        self.part_africa_commodities = r.africa_commodities
        self.part_risques = r.risques
        self.part_provision = r.provision
        self.part_comptes = r.comptes

    def save(self, *args, **kwargs):
        # Le calcul est refait seulement à la création ou si un élément du calcul change :
        # une simple correction de libellé ne fait pas changer de règle une ligne ancienne.
        if self._state.adding or self._elements_calcul_modifies():
            self.calculer()
        with transaction.atomic():
            super().save(*args, **kwargs)

    def _elements_calcul_modifies(self) -> bool:
        ancien = type(self).tous.filter(pk=self.pk).values("date", "quantite", "marge_unitaire").first()
        if ancien is None:
            return True
        return (ancien["date"] != self.date or ancien["quantite"] != self.quantite
                or ancien["marge_unitaire"] != self.marge_unitaire)
