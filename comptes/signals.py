"""Signaux du module comptes."""
from allauth.account.signals import password_changed, password_set
from django.dispatch import receiver


@receiver(password_changed)
@receiver(password_set)
def mot_de_passe_definitif(sender, request, user, **kwargs):
    """Le mot de passe provisoire a été remplacé : on lève l'obligation de le changer."""
    if user.doit_changer_mot_de_passe:
        user.doit_changer_mot_de_passe = False
        user.save(update_fields=["doit_changer_mot_de_passe"])
