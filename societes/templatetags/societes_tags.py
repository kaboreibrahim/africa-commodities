from django import template

from societes.models import Societe

register = template.Library()


@register.simple_tag
def societes_actives():
    """Noms des sociétés actives, dans l'ordre d'affichage (page de connexion)."""
    return list(Societe.objects.filter(actif=True).values_list("nom", flat=True))
