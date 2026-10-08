"""Mois de suivi : lu dans `?mois=AAAA-MM`, mémorisé en session, mois courant par défaut."""
import re
from datetime import date

from django.utils import timezone

CLE_SESSION = "mois_suivi"
FORMAT = re.compile(r"^(\d{4})-(\d{2})$")


def lire_mois(valeur) -> date | None:
    """« 2026-10 » -> date(2026, 10, 1) ; None si la valeur est absente ou invalide."""
    correspondance = FORMAT.match(str(valeur or "").strip())
    if not correspondance:
        return None
    annee, mois = int(correspondance[1]), int(correspondance[2])
    if not (2000 <= annee <= 2100 and 1 <= mois <= 12):
        return None
    return date(annee, mois, 1)


def mois_courant() -> date:
    return timezone.localdate().replace(day=1)


def mois_depuis_requete(request) -> date:
    """
    Mois de suivi de la requête. Une valeur `?mois=` valide est mémorisée en session ;
    une valeur invalide donne le mois courant (jamais d'erreur 500).
    """
    session = getattr(request, "session", None)
    if "mois" in request.GET:
        mois = lire_mois(request.GET["mois"]) or mois_courant()
        if session is not None:
            session[CLE_SESSION] = mois.strftime("%Y-%m")
        return mois
    return (lire_mois(session.get(CLE_SESSION)) if session is not None else None) or mois_courant()


def decaler(mois: date, n: int) -> date:
    """Le 1er du mois, `n` mois après (n négatif : avant)."""
    total = mois.year * 12 + mois.month - 1 + n
    return date(total // 12, total % 12 + 1, 1)
