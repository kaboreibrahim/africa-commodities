from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models.functions import Lower
from simple_history.models import HistoricalRecords

from core.models import ActifQuerySet, SuppressionDouceMixin, TimestampMixin
from core.validators import taille_max_2_mo, valider_extension_image, valider_image_reelle

couleur_hex = RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Couleur au format #RRGGBB.")


def premier_du_mois(d: date) -> date:
    return d.replace(day=1)


class FiltreSocieteMixin:
    """Ajoute `pour_utilisateur(user)` aux querysets de modèles rattachés à une société."""

    def pour_utilisateur(self, user):
        from comptes.acces import societes_accessibles  # import tardif : comptes dépend de societes

        return self.filter(societe__in=societes_accessibles(user))


class SocieteQuerySet(models.QuerySet):
    def pour_utilisateur(self, user):
        from comptes.acces import societes_accessibles

        return self.filter(pk__in=societes_accessibles(user).values("pk"))


class Societe(TimestampMixin, models.Model):
    """Une société du groupe (OOA, ANL, OTL, ALON Properties, Mon Livreur Pro)."""

    class TypeChampExtra(models.TextChoices):
        AUCUN = "", "Aucun"
        TEXTE = "texte", "Texte libre"
        CHOIX = "choix", "Liste de choix"

    code = models.SlugField("code", max_length=10, unique=True)
    nom = models.CharField("nom", max_length=120, unique=True)
    actif = models.BooleanField("active", default=True)
    ordre = models.PositiveSmallIntegerField("ordre d'affichage", default=0)

    # Libellés propres à l'activité de la société
    libelle_ligne = models.CharField("une ligne =", max_length=40, default="dossier")
    libelle_ligne_pluriel = models.CharField("pluriel", max_length=40, default="dossiers")
    libelle_reference = models.CharField("libellé référence", max_length=60, default="N° conteneur / référence")
    libelle_quantite = models.CharField("libellé quantité", max_length=60, default="Nb de conteneurs")
    libelle_marge = models.CharField("libellé marge unitaire", max_length=60, default="Marge par conteneur")
    unite = models.CharField("unité", max_length=30, default="conteneur")

    # Champ spécifique optionnel (Type pour ALON, Zone pour Mon Livreur Pro)
    champ_extra_libelle = models.CharField("champ spécifique : libellé", max_length=40, blank=True)
    champ_extra_type = models.CharField(
        "champ spécifique : type", max_length=10, choices=TypeChampExtra.choices, blank=True, default=""
    )
    champ_extra_choix = models.CharField(
        "champ spécifique : choix", max_length=255, blank=True, help_text="Valeurs séparées par des virgules."
    )

    marge_defaut = models.DecimalField(
        "marge unitaire par défaut (FCFA)", max_digits=14, decimal_places=0, default=100000,
        validators=[MinValueValidator(0)],
    )
    objectif_defaut = models.DecimalField(
        "objectif mensuel par défaut (FCFA)", max_digits=16, decimal_places=0, default=1000000,
        validators=[MinValueValidator(0)],
    )

    # Charte graphique
    couleur_principale = models.CharField(max_length=7, default="#1B7A2E", validators=[couleur_hex])
    couleur_foncee = models.CharField(max_length=7, default="#0E5A1E", validators=[couleur_hex])
    couleur_accent = models.CharField(max_length=7, default="#E8720C", validators=[couleur_hex])
    couleur_serie = models.CharField("couleur dans les graphiques groupe", max_length=7, default="#1B7A2E", validators=[couleur_hex])
    logo = models.ImageField(upload_to="logos/", blank=True, help_text="PNG, JPEG ou WEBP, 2 Mo maximum.",
                             validators=[valider_extension_image, taille_max_2_mo, valider_image_reelle])

    objects = SocieteQuerySet.as_manager()
    history = HistoricalRecords()

    class Meta:
        ordering = ["ordre", "nom"]
        verbose_name = "société"
        verbose_name_plural = "sociétés"

    def __str__(self):
        return self.nom

    @property
    def choix_extra(self) -> list[str]:
        return [c.strip() for c in self.champ_extra_choix.split(",") if c.strip()]

    def clean(self):
        if self.champ_extra_type == self.TypeChampExtra.CHOIX and not self.choix_extra:
            raise ValidationError({"champ_extra_choix": "Indique au moins un choix."})
        if self.champ_extra_type and not self.champ_extra_libelle:
            raise ValidationError({"champ_extra_libelle": "Donne un libellé au champ spécifique."})

    def objectif_pour(self, mois: date):
        """
        Objectif du mois : la valeur saisie pour ce mois, sinon celle du dernier mois
        renseigné avant, sinon l'objectif par défaut de la société.
        """
        mois = premier_du_mois(mois)
        obj = self.objectifs.filter(mois__lte=mois).order_by("-mois").values_list("montant", flat=True).first()
        return obj if obj is not None else self.objectif_defaut


class ClientQuerySet(FiltreSocieteMixin, ActifQuerySet):
    pass


class ClientManager(models.Manager.from_queryset(ClientQuerySet)):
    """Manager par défaut : clients actifs uniquement (suppression douce)."""

    def get_queryset(self):
        return super().get_queryset().filter(supprime_le__isnull=True)


class Client(TimestampMixin, SuppressionDouceMixin, models.Model):
    """Client rattaché à une société (chaque société a sa propre liste)."""

    societe = models.ForeignKey(Societe, on_delete=models.PROTECT, related_name="clients")
    nom = models.CharField("nom", max_length=150)
    telephone = models.CharField("téléphone", max_length=30, blank=True)
    email = models.EmailField("e-mail", blank=True)

    objects = ClientManager()
    tous = ClientQuerySet.as_manager()
    history = HistoricalRecords()

    class Meta:
        ordering = ["nom"]
        verbose_name = "client"
        verbose_name_plural = "clients"
        constraints = [
            # Pas deux fois le même client (majuscules/minuscules ignorées) dans une société
            models.UniqueConstraint(
                Lower("nom"), "societe",
                condition=models.Q(supprime_le__isnull=True),
                name="client_unique_par_societe",
                violation_error_message="Ce client existe déjà pour cette société.",
            ),
        ]

    def __str__(self):
        return self.nom

    def save(self, *args, **kwargs):
        self.nom = " ".join(self.nom.split())  # espaces superflus
        super().save(*args, **kwargs)


class ObjectifMensuelQuerySet(FiltreSocieteMixin, models.QuerySet):
    pass


class ObjectifMensuel(TimestampMixin, models.Model):
    """Objectif de marge fixé pour une société et un mois donnés."""

    societe = models.ForeignKey(Societe, on_delete=models.CASCADE, related_name="objectifs")
    mois = models.DateField("mois", help_text="Toujours enregistré au 1er du mois.")
    montant = models.DecimalField("objectif (FCFA)", max_digits=16, decimal_places=0, validators=[MinValueValidator(0)])

    objects = ObjectifMensuelQuerySet.as_manager()
    history = HistoricalRecords()

    class Meta:
        ordering = ["-mois"]
        verbose_name = "objectif mensuel"
        verbose_name_plural = "objectifs mensuels"
        constraints = [
            models.UniqueConstraint(fields=["societe", "mois"], name="objectif_unique_par_mois"),
            models.CheckConstraint(condition=models.Q(montant__gte=0), name="objectif_positif"),
        ]

    def __str__(self):
        return f"{self.societe.code} – {self.mois:%m/%Y}"

    def save(self, *args, **kwargs):
        self.mois = premier_du_mois(self.mois)
        super().save(*args, **kwargs)


class DepenseMensuelleQuerySet(FiltreSocieteMixin, models.QuerySet):
    pass


class DepenseMensuelle(TimestampMixin, models.Model):
    """
    Dépenses réelles d'une société pour un mois (montant global : loyer, salaires, carburant…).

    Contrairement à l'objectif, il n'y a PAS de report d'un mois sur l'autre : les dépenses sont
    un constat, pas une cible. Un mois sans saisie a des dépenses nulles (« dépenses non saisies »).
    """

    societe = models.ForeignKey(Societe, on_delete=models.CASCADE, related_name="depenses", verbose_name="société")
    mois = models.DateField("mois", help_text="Toujours enregistré au 1er du mois.")
    montant = models.DecimalField("dépenses du mois (FCFA)", max_digits=16, decimal_places=0,
                                  validators=[MinValueValidator(0)])
    note = models.CharField("note", max_length=255, blank=True)
    saisi_par = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  editable=False, related_name="depenses_saisies", verbose_name="saisi par")

    objects = DepenseMensuelleQuerySet.as_manager()
    history = HistoricalRecords()

    class Meta:
        ordering = ["-mois"]
        verbose_name = "dépenses mensuelles"
        verbose_name_plural = "dépenses mensuelles"
        constraints = [
            models.UniqueConstraint(fields=["societe", "mois"], name="depense_unique_par_mois",
                                    violation_error_message="Les dépenses de ce mois sont déjà saisies pour cette société."),
            models.CheckConstraint(condition=models.Q(montant__gte=0), name="depense_positive"),
        ]

    def __str__(self):
        return f"{self.societe.code} – dépenses {self.mois:%m/%Y}"

    def save(self, *args, **kwargs):
        self.mois = premier_du_mois(self.mois)
        super().save(*args, **kwargs)
