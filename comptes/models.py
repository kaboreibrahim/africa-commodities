from django.contrib.auth.models import AbstractUser
from django.db import models


class Utilisateur(AbstractUser):
    """
    Modèle utilisateur personnalisé, créé dès le départ (le changer plus tard est très coûteux).
    Les rôles et l'accès par société seront ajoutés à l'étape 2 (sécurité).
    """

    email = models.EmailField("adresse e-mail", unique=True)
    telephone = models.CharField("téléphone", max_length=30, blank=True)

    class Meta:
        verbose_name = "utilisateur"
        verbose_name_plural = "utilisateurs"

    def __str__(self):
        return self.get_full_name() or self.username
