"""
Signaux du module comptes : alimentation du journal de sécurité et fin du mot de passe provisoire.

Les refus d'accès sont journalisés directement par `comptes.acces.refuser` / `signaler_refus`.
"""
from allauth.account.signals import password_changed, password_set
from allauth.mfa.models import Authenticator
from axes.signals import user_locked_out
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .axes import identifiant_tentative
from .journal import journaliser
from .models import Affectation, JournalSecurite, Utilisateur

E = JournalSecurite.Evenement
TYPES_MFA = (Authenticator.Type.TOTP, Authenticator.Type.WEBAUTHN)


# --- Connexion / déconnexion / blocage --------------------------------------------------------

@receiver(user_logged_in)
def connexion(sender, request, user, **kwargs):
    journaliser(E.CONNEXION, utilisateur=user, request=request)


@receiver(user_logged_out)
def deconnexion(sender, request, user, **kwargs):
    journaliser(E.DECONNEXION, utilisateur=user, request=request)


@receiver(user_login_failed)
def echec_connexion(sender, credentials, request=None, **kwargs):
    # `credentials` a déjà le mot de passe masqué par Django : on ne garde que l'identifiant.
    identifiant = identifiant_tentative(None, credentials) or ""
    journaliser(E.ECHEC_CONNEXION, request=request, identifiant_saisi=identifiant,
                bloque=bool(getattr(request, "axes_locked_out", False)))


@receiver(user_locked_out)
def compte_bloque(sender, request, username=None, ip_address=None, **kwargs):
    utilisateur = Utilisateur.objects.filter(email__iexact=username).first() if username else None
    journaliser(E.COMPTE_BLOQUE, utilisateur=utilisateur, request=request, identifiant_saisi=username or "")


# --- Double authentification ------------------------------------------------------------------
# Signaux de modèle plutôt que ceux d'allauth : ils couvrent aussi la réinitialisation
# d'une 2FA par l'admin groupe (suppression de l'authentificateur dans l'admin).

@receiver(post_save, sender=Authenticator)
def mfa_activee(sender, instance, created, **kwargs):
    if created and instance.type in TYPES_MFA:
        journaliser(E.MFA_ACTIVEE, utilisateur=instance.user, type=instance.type)


@receiver(post_delete, sender=Authenticator)
def mfa_desactivee(sender, instance, **kwargs):
    if instance.type in TYPES_MFA:
        journaliser(E.MFA_DESACTIVEE, utilisateur=instance.user, type=instance.type)


# --- Mot de passe et rôle global --------------------------------------------------------------

@receiver(pre_save, sender=Utilisateur)
def memoriser_changements(sender, instance, update_fields=None, raw=False, **kwargs):
    """Repère, avant l'enregistrement, un changement de mot de passe ou de rôle global."""
    instance._changements_securite = {}
    if raw or instance._state.adding or not instance.pk:
        return
    champs = {"password", "role_global"} if update_fields is None else {"password", "role_global"} & set(update_fields)
    if not champs:
        return
    ancien = Utilisateur.objects.filter(pk=instance.pk).values(*champs).first() or {}
    if "password" in ancien and ancien["password"] != instance.password:
        instance._changements_securite["password"] = True
    if "role_global" in ancien and ancien["role_global"] != instance.role_global:
        instance._changements_securite["role_global"] = (ancien["role_global"], instance.role_global)


@receiver(post_save, sender=Utilisateur)
def journaliser_changements(sender, instance, created, **kwargs):
    changements = instance.__dict__.pop("_changements_securite", {})
    if changements.get("password"):
        journaliser(E.MOT_DE_PASSE_CHANGE, utilisateur=instance)
    if "role_global" in changements:
        avant, apres = changements["role_global"]
        journaliser(E.ROLE_MODIFIE, utilisateur=instance, role_global_avant=avant or "aucun",
                    role_global_apres=apres or "aucun", par=_auteur())
    if created and instance.role_global:
        journaliser(E.ROLE_MODIFIE, utilisateur=instance, role_global_avant="aucun",
                    role_global_apres=instance.role_global, par=_auteur())


@receiver(password_changed)
@receiver(password_set)
def mot_de_passe_definitif(sender, request, user, **kwargs):
    """Le mot de passe provisoire a été remplacé : on lève l'obligation de le changer."""
    if user.doit_changer_mot_de_passe:
        user.doit_changer_mot_de_passe = False
        user.save(update_fields=["doit_changer_mot_de_passe"])


# --- Affectations -----------------------------------------------------------------------------

@receiver(post_save, sender=Affectation)
def affectation_enregistree(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    journaliser(E.ROLE_MODIFIE, utilisateur=instance.utilisateur, action="creee" if created else "modifiee",
                societe=instance.societe.code, role=instance.role, active=instance.actif, par=_auteur())


@receiver(post_delete, sender=Affectation)
def affectation_supprimee(sender, instance, **kwargs):
    # L'utilisateur est peut-être en cours de suppression (cascade) : on garde son e-mail, pas la clé.
    journaliser(E.ROLE_MODIFIE, identifiant_saisi=instance.utilisateur.email, action="supprimee",
                utilisateur_id=instance.utilisateur_id, societe=instance.societe.code, role=instance.role,
                par=_auteur())


def _auteur() -> str:
    """E-mail de l'utilisateur connecté qui fait la modification (s'il y a une requête en cours)."""
    from .journal import _en_cours

    contexte = _en_cours.get()
    user = getattr(contexte.request, "user", None) if contexte else None
    return user.email if user is not None and user.is_authenticated else ""
