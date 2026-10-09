from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.utils import timezone
from simple_history.models import HistoricalRecords

from core.models import TimestampMixin


class Utilisateur(AbstractUser):
    """
    Modèle utilisateur personnalisé, créé dès le départ (le changer plus tard est très coûteux).

    Droits : un rôle global (`role_global` : administrateur groupe ou rien), des rôles par société
    (`affectations`) et, éventuellement, une habilitation à la Vue Groupe (`habilitation_groupe`).
    Les règles d'accès sont appliquées dans `comptes/acces.py` ; elles sont accordées et retirées
    par l'administrateur groupe via `comptes/services.py`.
    """

    class RoleGlobal(models.TextChoices):
        AUCUN = "", "Aucun (accès par habilitations uniquement)"
        ADMIN_GROUPE = "admin_groupe", "Administrateur groupe"

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


class EnVigueurQuerySet(models.QuerySet):
    """Habilitations accordées (`actif`) dont la période de validité couvre la date `le` (aujourd'hui par défaut)."""

    def en_vigueur(self, le=None):
        le = le or timezone.localdate()
        return (self.filter(actif=True)
                .filter(Q(date_debut__isnull=True) | Q(date_debut__lte=le))
                .filter(Q(date_fin__isnull=True) | Q(date_fin__gte=le)))


class PeriodeMixin:
    """Méthode commune aux habilitations à durée limitée (`actif`, `date_debut`, `date_fin`)."""

    def est_en_vigueur(self, le=None) -> bool:
        le = le or timezone.localdate()
        return bool(self.actif and (self.date_debut is None or self.date_debut <= le)
                    and (self.date_fin is None or self.date_fin >= le))


class Affectation(PeriodeMixin, TimestampMixin, models.Model):
    """Rôle d'un utilisateur sur une société du groupe, éventuellement limité dans le temps."""

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
    date_debut = models.DateField("valable à partir du", null=True, blank=True, help_text="Vide : immédiatement.")
    date_fin = models.DateField("valable jusqu'au", null=True, blank=True,
                                help_text="Vide : sans limite. Le dernier jour est inclus.")
    motif = models.CharField("motif", max_length=255, blank=True)
    accorde_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="affectations_accordees", editable=False,
                                    verbose_name="accordée par")

    objects = EnVigueurQuerySet.as_manager()
    history = HistoricalRecords()

    class Meta:
        ordering = ["societe__ordre", "utilisateur__last_name"]
        verbose_name = "affectation"
        verbose_name_plural = "affectations"
        constraints = [
            models.UniqueConstraint(fields=["utilisateur", "societe"], name="affectation_unique",
                                    violation_error_message="Cet utilisateur a déjà un rôle sur cette société."),
            models.CheckConstraint(
                condition=Q(date_debut__isnull=True) | Q(date_fin__isnull=True) | Q(date_fin__gte=models.F("date_debut")),
                name="affectation_dates_coherentes",
                violation_error_message="La date de fin doit être postérieure ou égale à la date de début."),
        ]

    def __str__(self):
        return f"{self.utilisateur} – {self.societe.code} ({self.get_role_display()})"


class HabilitationVueGroupe(PeriodeMixin, TimestampMixin, models.Model):
    """
    Droit de voir la Vue Groupe (chiffres consolidés), sur toutes les sociétés ou sur une sélection.
    Accordé et retiré par l'administrateur groupe (`comptes/services.py`). Une seule par utilisateur.
    """

    class Portee(models.TextChoices):
        TOUTES = "toutes", "Toutes les sociétés (y compris les futures)"
        SELECTION = "selection", "Sociétés sélectionnées"

    utilisateur = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                       related_name="habilitation_groupe", verbose_name="utilisateur")
    portee = models.CharField("portée", max_length=10, choices=Portee.choices, default=Portee.SELECTION)
    societes = models.ManyToManyField("societes.Societe", blank=True, related_name="habilitations_groupe",
                                      verbose_name="sociétés")
    detail_autorise = models.BooleanField(
        "accès au détail", default=False,
        help_text="Si coché : depuis la Vue Groupe, la personne peut ouvrir le tableau de bord et la liste des lignes "
                  "des sociétés de sa portée (lecture seule). Sinon : uniquement les chiffres consolidés.")
    actif = models.BooleanField("active", default=True)
    date_debut = models.DateField("valable à partir du", null=True, blank=True, help_text="Vide : immédiatement.")
    date_fin = models.DateField("valable jusqu'au", null=True, blank=True,
                                help_text="Vide : sans limite. Le dernier jour est inclus.")
    motif = models.CharField("motif", max_length=255, blank=True)
    accorde_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="habilitations_groupe_accordees", editable=False,
                                    verbose_name="accordée par")

    objects = EnVigueurQuerySet.as_manager()
    history = HistoricalRecords(m2m_fields=[societes])

    class Meta:
        verbose_name = "habilitation Vue Groupe"
        verbose_name_plural = "habilitations Vue Groupe"
        constraints = [
            models.CheckConstraint(
                condition=Q(date_debut__isnull=True) | Q(date_fin__isnull=True) | Q(date_fin__gte=models.F("date_debut")),
                name="habilitation_groupe_dates_coherentes",
                violation_error_message="La date de fin doit être postérieure ou égale à la date de début."),
        ]

    def __str__(self):
        return f"{self.utilisateur} – Vue Groupe ({self.get_portee_display()})"


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
        ACCES_SOCIETE_ACCORDE = "acces_societe_accorde", "Accès société accordé"
        ACCES_SOCIETE_MODIFIE = "acces_societe_modifie", "Accès société modifié"
        ACCES_SOCIETE_RETIRE = "acces_societe_retire", "Accès société retiré"
        VUE_GROUPE_ACCORDEE = "vue_groupe_accordee", "Vue Groupe accordée"
        VUE_GROUPE_MODIFIEE = "vue_groupe_modifiee", "Vue Groupe modifiée"
        VUE_GROUPE_RETIREE = "vue_groupe_retiree", "Vue Groupe retirée"
        ROLE_GLOBAL_MODIFIE = "role_global_modifie", "Rôle groupe modifié"
        COMPTE_CREE = "compte_cree", "Compte créé"
        COMPTE_ACTIVE = "compte_active", "Compte activé"
        COMPTE_DESACTIVE = "compte_desactive", "Compte désactivé"
        HABILITATION_EXPIREE = "habilitation_expiree", "Habilitation expirée"

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
