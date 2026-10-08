from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from simple_history.models import HistoricalRecords

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
    doit_changer_mot_de_passe = models.BooleanField(
        "doit changer son mot de passe", default=False,
        help_text="Le mot de passe est provisoire : son changement est imposé à la prochaine connexion.",
    )

    # Le mot de passe (même haché) n'est JAMAIS historisé.
    history = HistoricalRecords(excluded_fields=["password", "last_login"])

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
        # La mise à jour de last_login à chaque connexion ne crée pas d'entrée d'historique.
        if update_fields is not None and set(update_fields) == {"last_login"}:
            self.skip_history_when_saving = True
        try:
            super().save(*args, **kwargs)
        finally:
            self.__dict__.pop("skip_history_when_saving", None)


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

    history = HistoricalRecords()

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


class JournalSecurite(models.Model):
    """
    Événements de sécurité (connexions, blocages, 2FA, rôles, accès refusés).
    Ne contient JAMAIS de mot de passe, de code TOTP, de jeton ni de code de récupération.
    """

    class Evenement(models.TextChoices):
        CONNEXION = "connexion", "Connexion"
        ECHEC_CONNEXION = "echec_connexion", "Échec de connexion"
        DECONNEXION = "deconnexion", "Déconnexion"
        COMPTE_BLOQUE = "compte_bloque", "Compte bloqué"
        MFA_ACTIVEE = "mfa_activee", "2FA activée"
        MFA_DESACTIVEE = "mfa_desactivee", "2FA désactivée"
        MOT_DE_PASSE_CHANGE = "mdp_change", "Mot de passe changé"
        ROLE_MODIFIE = "role_modifie", "Rôle modifié"
        ACCES_REFUSE = "acces_refuse", "Accès refusé"

    date = models.DateTimeField("date", auto_now_add=True, db_index=True)
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="journal_securite", verbose_name="utilisateur")
    identifiant_saisi = models.CharField("identifiant saisi", max_length=150, blank=True)
    evenement = models.CharField("événement", max_length=30, choices=Evenement.choices, db_index=True)
    ip = models.GenericIPAddressField("adresse IP", null=True, blank=True)
    user_agent = models.CharField("navigateur", max_length=255, blank=True)
    details = models.JSONField("détails", default=dict, blank=True)

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name = "entrée du journal de sécurité"
        verbose_name_plural = "journal de sécurité"

    def __str__(self):
        return f"{self.date:%d/%m/%Y %H:%M} – {self.get_evenement_display()} – {self.utilisateur or self.identifiant_saisi}"
