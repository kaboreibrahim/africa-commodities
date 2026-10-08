from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from repartition.models import RegleRepartition

from .contexte import oublier_regle_en_vigueur


@receiver(post_save, sender=RegleRepartition)
@receiver(post_delete, sender=RegleRepartition)
def regle_modifiee(sender, **kwargs):
    oublier_regle_en_vigueur()
