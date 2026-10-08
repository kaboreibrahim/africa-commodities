"""Journal de sécurité : enregistrement des événements sensibles."""
import logging

logger = logging.getLogger("securite")


def journaliser_refus(user, action: str, **details) -> None:
    identifiant = getattr(user, "email", "") or "anonyme"
    logger.warning("Accès refusé : %s (utilisateur %s) %s", action, identifiant,
                   {cle: str(valeur) for cle, valeur in details.items()})
