"""
Filtres de mise en forme à la française : montants FCFA, pourcentages, mois.

    {% load format_fr %}
    {{ 1250000|fcfa }}         -> 1 250 000 F
    {{ 4800000|fcfa_court }}   -> 4,8 M
    {{ 2.5|pct }}              -> 2,5 %
    {{ mois|mois_long }}       -> octobre 2026
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import template

register = template.Library()

ESPACE_MILLIERS = " "  # espace insécable fine
ESPACE_INSECABLE = " "  # avant « F » et « % »

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]
MOIS_COURTS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def _decimal(valeur) -> Decimal | None:
    if valeur is None or valeur == "":
        return None
    try:
        return Decimal(str(valeur))
    except (InvalidOperation, ValueError, TypeError):
        return None


def entier_fr(valeur) -> str:
    """1250000 -> « 1 250 000 » (arrondi à l'unité, espace fine insécable)."""
    nombre = _decimal(valeur)
    if nombre is None:
        return ""
    entier = int(nombre.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return f"{entier:,}".replace(",", ESPACE_MILLIERS)


def decimal_fr(nombre: Decimal, chiffres: int = 1) -> str:
    """2.5 -> « 2,5 » ; 25.0 -> « 25 » (zéros inutiles retirés)."""
    arrondi = nombre.quantize(Decimal(1).scaleb(-chiffres), rounding=ROUND_HALF_UP)
    texte = f"{arrondi:f}"
    if "." in texte:
        texte = texte.rstrip("0").rstrip(".")
    entier, _, decimales = texte.partition(".")
    signe = "-" if entier.startswith("-") else ""
    entier = f"{int(entier.lstrip('-') or 0):,}".replace(",", ESPACE_MILLIERS)
    return f"{signe}{entier},{decimales}" if decimales else f"{signe}{entier}"


@register.filter
def nombre(valeur) -> str:
    """Nombre entier avec séparateur des milliers, sans unité (tableaux)."""
    return entier_fr(valeur)


@register.filter
def fcfa(valeur) -> str:
    texte = entier_fr(valeur)
    return f"{texte}{ESPACE_INSECABLE}F" if texte else ""


@register.filter
def fcfa_court(valeur) -> str:
    """4 800 000 -> « 4,8 M » ; 250 000 -> « 250 k » ; 800 -> « 800 »."""
    montant = _decimal(valeur)
    if montant is None:
        return ""
    absolu = abs(montant)
    if absolu >= 1_000_000:
        return f"{decimal_fr(montant / 1_000_000)}{ESPACE_INSECABLE}M"
    if absolu >= 1_000:
        return f"{entier_fr(montant / 1_000)}{ESPACE_INSECABLE}k"
    return entier_fr(montant)


@register.filter
def pct(valeur) -> str:
    """2.5 -> « 2,5 % » ; 25.0 -> « 25 % »."""
    nombre_ = _decimal(valeur)
    if nombre_ is None:
        return ""
    return f"{decimal_fr(nombre_)}{ESPACE_INSECABLE}%"


@register.filter
def mois_long(valeur) -> str:
    """date(2026, 10, 1) -> « octobre 2026 »."""
    if not isinstance(valeur, date):
        return ""
    return f"{MOIS[valeur.month - 1]} {valeur.year}"


@register.filter
def mois_court(valeur) -> str:
    """date(2026, 10, 1) -> « oct. »."""
    return MOIS_COURTS[valeur.month - 1] if isinstance(valeur, date) else ""


@register.filter
def iso_mois(valeur) -> str:
    """date(2026, 10, 1) -> « 2026-10 » (valeur d'un <input type="month">)."""
    return valeur.strftime("%Y-%m") if isinstance(valeur, date) else ""


@register.filter
def majuscule_initiale(valeur) -> str:
    texte = str(valeur or "")
    return texte[:1].upper() + texte[1:]
