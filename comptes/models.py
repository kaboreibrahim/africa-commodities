from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

from core.models import TimestampMixin


class Utilisateur(AbstractUser):
    """
    Modèle utilisateur personnalisé, créé dès le départ (le changer plus tard est très coûteux).

    Droits : un rôle global (`role_global`, pour tout le groupe) et/ou des rôles par société
    (`affectations`). Les règles d'accès sont appliquées dans `comptes/acces.py`.
    """

    class RoleGlobal(models.TextChoices):
        AUCUN = "", "Aucun (accès par société uniquement)"
        ADMIN_GROUPE = "admin_groupe", "Administrateur groupe"
        DIRECTION = "direction", "Direction (lecture de tout le groupe)"

    email = models.EmailField("adresse e-mail", unique=True)
    telephone = models.CharField("téléphone", max_length=30, blank=True)
    role_global = models.CharField("rôle groupe", max_length=20, choices=RoleGlobal.choices, blank=True, default="")

    class Meta:
        verbose_name = "utilisateur"
        verbose_name_plural = "utilisateurs"

    def __str__(self):
        return self.get_full_name() or self.username

    def save(self, *args, **kwargs):
        # L'accès à l'admin Django est réservé à l'admin groupe (et aux superutilisateurs).
        self.is_staff = self.is_superuser or self.role_global == self.RoleGlobal.ADMIN_GROUPE
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "role_global" in update_fields:
            kwargs["update_fields"] = {*update_fields, "is_staff"}
        super().save(*args, **kwargs)


class Affectation(TimestampMixin, models.Model):
    """Rôle d'un utilisateur sur une société du groupe."""

    class Role(models.TextChoices):
        RESPONSABLE = "responsable", "Responsable société"
        SAISIE = "saisie", "Saisie"
        LECTURE = "lecture", "Lecture seule"

    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="affectations",
                                    verbose_name="utilisateur")
    societe = models.ForeignKey("societes.Societe", on_delete=models.CASCADE, related_name="affectations",
                                verbose_name="société")
    role = models.CharField("rôle", max_length=20, choices=Role.choices)
    actif = models.BooleanField("active", default=True)

    class Meta:
        ordering = ["societe__ordre", "utilisateur__last_name"]
        verbose_name = "affectation"
        verbose_name_plural = "affectations"
        constraints = [
            models.UniqueConstraint(fields=["utilisateur", "societe"], name="affectation_unique",
                                    violation_error_message="Cet utilisateur a déjà un rôle sur cette société."),
        ]

    def __str__(self):
        return f"{self.utilisateur} – {self.societe.code} ({self.get_role_display()})"
