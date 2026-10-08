from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import TimestampMixin

pourcentage = [MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))]


class RegleRepartitionQuerySet(models.QuerySet):
    def en_vigueur(self, le: date):
        """Règle applicable à une date : la plus récente dont la date de début est <= `le`."""
        regle = self.filter(date_debut__lte=le).order_by("-date_debut").first()
        if regle is None:
            raise RegleRepartition.DoesNotExist(f"Aucune règle de répartition en vigueur au {le:%d/%m/%Y}.")
        return regle


class RegleRepartition(TimestampMixin, models.Model):
    """
    Règle de répartition de la marge, commune à toutes les sociétés et versionnée dans le temps :
    1. `pct_charges` % de la marge va aux charges ;
    2. `pct_africa_commodities` % du reste va à Africa Commodities ;
    3. le solde est partagé entre Risques / Provision / Comptes selon un nombre de parts.

    Une nouvelle règle s'applique à partir de sa date de début ; les lignes déjà
    enregistrées gardent la répartition calculée avec la règle de leur date.
    """

    date_debut = models.DateField("applicable à partir du", unique=True)
    pct_charges = models.DecimalField("part charges (% de la marge)", max_digits=5, decimal_places=2,
                                      default=Decimal("25"), validators=pourcentage)
    pct_africa_commodities = models.DecimalField("Africa Commodities (% du reste)", max_digits=5, decimal_places=2,
                                                 default=Decimal("60"), validators=pourcentage)
    parts_risques = models.PositiveSmallIntegerField("risques (nb de parts)", default=1)
    parts_provision = models.PositiveSmallIntegerField("provision (nb de parts)", default=1)
    parts_comptes = models.PositiveSmallIntegerField("comptes (nb de parts)", default=1)
    note = models.CharField("note / décision", max_length=255, blank=True)

    objects = RegleRepartitionQuerySet.as_manager()

    class Meta:
        ordering = ["-date_debut"]
        verbose_name = "règle de répartition"
        verbose_name_plural = "règles de répartition"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(pct_charges__gte=0, pct_charges__lte=100,
                                   pct_africa_commodities__gte=0, pct_africa_commodities__lte=100),
                name="regle_pourcentages_valides",
            ),
            models.CheckConstraint(
                condition=models.Q(parts_risques__gt=0) | models.Q(parts_provision__gt=0) | models.Q(parts_comptes__gt=0),
                name="regle_au_moins_une_part",
            ),
        ]

    def __str__(self):
        return (f"Depuis le {self.date_debut:%d/%m/%Y} : {self.pct_charges:g} % charges, "
                f"{self.pct_africa_commodities:g} % AC, parts {self.parts_risques}/{self.parts_provision}/{self.parts_comptes}")

    @property
    def total_parts(self) -> int:
        return self.parts_risques + self.parts_provision + self.parts_comptes

    def clean(self):
        if self.total_parts == 0:
            raise ValidationError("Il faut au moins une part pour Risques, Provision ou Comptes.")
