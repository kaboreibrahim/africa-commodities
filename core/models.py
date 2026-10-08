from django.db import models
from django.utils import timezone


class TimestampMixin(models.Model):
    """Ajoute les dates de création et de dernière modification."""

    cree_le = models.DateTimeField("créé le", auto_now_add=True)
    modifie_le = models.DateTimeField("modifié le", auto_now=True)

    class Meta:
        abstract = True


class ActifQuerySet(models.QuerySet):
    def actifs(self):
        return self.filter(supprime_le__isnull=True)

    def supprimes(self):
        return self.filter(supprime_le__isnull=False)


class ActifManager(models.Manager.from_queryset(ActifQuerySet)):
    """Manager par défaut : masque les enregistrements supprimés (suppression douce)."""

    def get_queryset(self):
        return super().get_queryset().filter(supprime_le__isnull=True)


class SuppressionDouceMixin(models.Model):
    """
    Suppression « douce » : l'enregistrement est marqué supprimé au lieu d'être effacé,
    et peut être restauré. `objects` ne renvoie que les actifs, `tous` renvoie tout.
    """

    supprime_le = models.DateTimeField("supprimé le", null=True, blank=True, editable=False, db_index=True)

    objects = ActifManager()
    tous = ActifQuerySet.as_manager()

    class Meta:
        abstract = True

    def supprimer(self):
        self.supprime_le = timezone.now()
        self.save(update_fields=["supprime_le"])

    def restaurer(self):
        self.supprime_le = None
        self.save(update_fields=["supprime_le"])

    @property
    def est_supprime(self):
        return self.supprime_le is not None
