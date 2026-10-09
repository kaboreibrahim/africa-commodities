"""
Journal de sécurité : enregistrement des événements sensibles (modèle `JournalSecurite`).

Pendant une requête HTTP, les entrées sont mises en attente puis écrites par
`JournalSecuriteMiddleware` APRÈS la vue. Avec ATOMIC_REQUESTS, une vue qui lève
PermissionDenied voit sa transaction annulée : l'entrée « accès refusé » serait perdue
si elle était écrite pendant la vue. Hors requête (commandes, tests), l'écriture est immédiate.
"""
import contextvars
import logging
import re

from axes.helpers import get_client_ip_address

logger = logging.getLogger("securite")

_en_cours = contextvars.ContextVar("journal_securite", default=None)

# Clés jamais enregistrées dans `details` (mots de passe, codes TOTP, jetons, codes de récupération…).
CLES_INTERDITES = re.compile(r"pass|mdp|mot_de_passe|code|token|jeton|secret|cle|key|otp|recovery|recuperation",
                             re.IGNORECASE)


class _Contexte:
    def __init__(self, request):
        self.request = request
        self.en_attente: list[dict] = []


def _nettoyer_valeur(valeur):
    if isinstance(valeur, (int, float, bool)) or valeur is None:
        return valeur
    if isinstance(valeur, dict):
        return _nettoyer(valeur)
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return [_nettoyer_valeur(v) for v in (sorted(valeur, key=str) if isinstance(valeur, (set, frozenset)) else valeur)]
    return str(valeur)


def _nettoyer(details: dict) -> dict:
    """Garde les valeurs simples, listes et dictionnaires (avant/après d'une habilitation) ; filtre les clés sensibles."""
    return {cle: _nettoyer_valeur(valeur) for cle, valeur in details.items() if not CLES_INTERDITES.search(cle)}


# Vrai pendant une opération de `comptes/services.py` : elle écrit elle-même une entrée détaillée
# (auteur, avant/après, motif), les signaux de modèle n'en ajoutent alors pas une seconde.
par_service = contextvars.ContextVar("journal_par_service", default=False)


def _ecrire(entree: dict) -> None:
    from comptes.models import JournalSecurite, Utilisateur

    utilisateur = entree.pop("utilisateur", None)
    if utilisateur is not None and not Utilisateur.objects.filter(pk=utilisateur.pk).exists():
        # Compte supprimé entre-temps : on garde son identifiant, pas la clé étrangère.
        entree["identifiant_saisi"] = entree.get("identifiant_saisi") or utilisateur.email
        utilisateur = None
    JournalSecurite.objects.create(utilisateur=utilisateur, **entree)


def journaliser(evenement: str, utilisateur=None, request=None, identifiant_saisi: str = "", **details) -> None:
    """Ajoute une entrée au journal de sécurité (`evenement` : valeur de JournalSecurite.Evenement)."""
    contexte = _en_cours.get()
    request = request or (contexte.request if contexte else None)
    if utilisateur is not None and not getattr(utilisateur, "is_authenticated", False):
        utilisateur = None  # utilisateur anonyme
    entree = {
        "evenement": evenement,
        "utilisateur": utilisateur,
        "identifiant_saisi": (identifiant_saisi or "")[:150],
        "ip": get_client_ip_address(request) if request is not None else None,
        "user_agent": request.META.get("HTTP_USER_AGENT", "")[:255] if request is not None else "",
        "details": _nettoyer(details),
    }
    if contexte is not None:
        contexte.en_attente.append(entree)
    else:
        _ecrire(entree)


def journaliser_refus(user, action: str, **details) -> None:
    """Accès refusé (service, vue, admin) : journal de sécurité + logger « securite »."""
    from comptes.models import JournalSecurite

    identifiant = getattr(user, "email", "") or "anonyme"
    logger.warning("Accès refusé : %s (utilisateur %s) %s", action, identifiant, _nettoyer(details))
    journaliser(JournalSecurite.Evenement.ACCES_REFUSE, utilisateur=user, action=action, **details)


class JournalSecuriteMiddleware:
    """Écrit les entrées du journal en attente une fois la réponse produite (hors transaction de la vue)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        contexte = _Contexte(request)
        jeton = _en_cours.set(contexte)
        try:
            return self.get_response(request)
        finally:
            _en_cours.reset(jeton)
            for entree in contexte.en_attente:
                try:
                    _ecrire(entree)
                except Exception:  # le journal ne doit jamais faire échouer la réponse
                    logger.exception("Écriture du journal de sécurité impossible : %s", entree.get("evenement"))
