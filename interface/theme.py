"""Couleurs de marque : thème de chaque société et thème neutre de la Vue Groupe."""
from django.contrib.staticfiles import finders
from django.templatetags.static import static

THEME_GROUPE = {"principale": "#004B2F", "foncee": "#063B29", "accent": "#C69214"}

# Palette fixe des postes de répartition (validée pour les daltoniens : ne pas modifier).
COULEURS_POSTES = {
    "charges": "#2F6FB0",
    "africa_commodities": "#E8720C",
    "risques": "#8E5BB5",
    "provision": "#B8A21E",
    "comptes": "#1B7A2E",
}
EXTENSIONS_LOGO = ("png", "jpg", "jpeg", "webp")


def couleur_claire(couleur: str, part_blanc: float = 0.9) -> str:
    """Mélange une couleur #RRGGBB avec du blanc : `part_blanc`=0.9 donne un fond très clair."""
    couleur = couleur.lstrip("#")
    if len(couleur) != 6:
        raise ValueError(f"Couleur invalide : #{couleur}")
    composantes = [int(couleur[i:i + 2], 16) for i in (0, 2, 4)]
    melange = [int(c + (255 - c) * part_blanc + 0.5) for c in composantes]  # arrondi « au plus proche »
    return "#" + "".join(f"{c:02X}" for c in melange)


def variables_theme(principale: str, foncee: str, accent: str) -> str:
    return (f":root{{--c-principale:{principale};--c-foncee:{foncee};"
            f"--c-claire:{couleur_claire(principale)};--c-accent:{accent}}}")


def css_theme(societe=None, societes=()) -> str:
    """Feuille de style : variables du thème actif + une classe `.serie-<code>` par société (couleur de série)."""
    if societe is None:
        lignes = [variables_theme(**THEME_GROUPE)]
    else:
        lignes = [variables_theme(societe.couleur_principale, societe.couleur_foncee, societe.couleur_accent)]
    lignes += [f".serie-{s.code}{{--c-serie:{s.couleur_serie}}}" for s in societes]
    return "\n".join(lignes) + "\n"


def url_logo(societe) -> str | None:
    """Logo téléversé, sinon logo fourni avec l'application (static/img/logos/<code>.*), sinon None."""
    if societe is None:
        chemin_groupe = "img/logos/africa-group-logo.png"
        if finders.find(chemin_groupe):
            return static(chemin_groupe)
        return None
    if societe.logo:
        return societe.logo.url
    for extension in EXTENSIONS_LOGO:
        chemin = f"img/logos/{societe.code}.{extension}"
        if finders.find(chemin):
            return static(chemin)
    return None
