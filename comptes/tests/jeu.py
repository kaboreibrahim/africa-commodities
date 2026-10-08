"""Jeu d'utilisateurs commun aux tests de sécurité (un par rôle)."""
from datetime import date

from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
from axes.utils import reset as reinitialiser_axes
from django.core.cache import cache
from django.utils import timezone

from comptes.models import Affectation, Utilisateur
from operations.models import Ligne
from repartition.models import RegleRepartition
from societes.models import Societe

MOT_DE_PASSE = "Tr3s-Secret-Pour-Les-Tests!"

R = Affectation.Role


def mois_decale(n: int) -> date:
    """Le 1er du mois, `n` mois avant le mois en cours (n=0 : mois en cours)."""
    jour = timezone.localdate()
    total = jour.year * 12 + jour.month - 1 - n
    return date(total // 12, total % 12 + 1, 1)


def creer_utilisateur(identifiant, role_global="", affectations=(), **extra):
    user = Utilisateur.objects.create_user(identifiant, f"{identifiant}@exemple.ci", MOT_DE_PASSE,
                                           role_global=role_global, **extra)
    for societe, role, *actif in affectations:
        Affectation.objects.create(utilisateur=user, societe=societe, role=role, actif=actif[0] if actif else True)
    return user


def activer_totp(user) -> str:
    """Active la 2FA (TOTP) d'un utilisateur ; renvoie le secret."""
    secret = generate_totp_secret()
    TOTP.activate(user, secret)
    return secret


class ReinitialiserAxesMixin:
    """Remet à zéro les compteurs d'axes et les limites d'allauth (cache) avant chaque test."""

    def setUp(self):
        super().setUp()
        reinitialiser_axes()
        cache.clear()


def creer_ligne(societe, cree_par=None, **kw):
    """Création directe (hors services) pour préparer les données des tests."""
    data = dict(date=timezone.localdate(), reference="REF", quantite=1, marge_unitaire=100_000)
    data.update(kw)
    return Ligne.objects.create(societe=societe, cree_par=cree_par, **data)


class JeuUtilisateursMixin:
    """À combiner avec TestCase : crée les sociétés, les utilisateurs de chaque rôle et quelques lignes."""

    @classmethod
    def setUpTestData(cls):
        # Une règle ancienne pour que les lignes « vieilles de 3 mois » soient toujours valides.
        RegleRepartition.objects.get_or_create(date_debut=date(2000, 1, 1))
        cls.ooa = Societe.objects.get(code="ooa")
        cls.anl = Societe.objects.get(code="anl")
        cls.admin_groupe = creer_utilisateur("admin", Utilisateur.RoleGlobal.ADMIN_GROUPE)
        cls.direction = creer_utilisateur("direction", Utilisateur.RoleGlobal.DIRECTION)
        cls.responsable_ooa = creer_utilisateur("resp_ooa", affectations=[(cls.ooa, R.RESPONSABLE)])
        cls.saisie_ooa = creer_utilisateur("saisie_ooa", affectations=[(cls.ooa, R.SAISIE)])
        cls.collegue_ooa = creer_utilisateur("collegue_ooa", affectations=[(cls.ooa, R.SAISIE)])
        cls.lecture_ooa = creer_utilisateur("lecture_ooa", affectations=[(cls.ooa, R.LECTURE)])
        cls.saisie_anl = creer_utilisateur("saisie_anl", affectations=[(cls.anl, R.SAISIE)])
        cls.inactif = creer_utilisateur("inactif", affectations=[(cls.ooa, R.RESPONSABLE)], is_active=False)
        cls.affectation_inactive = creer_utilisateur("aff_inactive", affectations=[(cls.ooa, R.RESPONSABLE, False)])

        cls.ligne_saisie_ooa = creer_ligne(cls.ooa, cls.saisie_ooa, reference="SAISIE-OOA")
        cls.ligne_collegue = creer_ligne(cls.ooa, cls.collegue_ooa, reference="COLLEGUE-OOA")
        cls.ligne_ancienne = creer_ligne(cls.ooa, cls.saisie_ooa, reference="ANCIENNE", date=mois_decale(3))
        cls.ligne_anl = creer_ligne(cls.anl, cls.saisie_anl, reference="ANL")
