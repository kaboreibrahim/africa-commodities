from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from comptes import acces


@login_required
def accueil(request):
    """Page d'accueil provisoire (les tableaux de bord arrivent à l'étape 3)."""
    return render(request, "accueil.html", {
        "societes": acces.societes_accessibles(request.user),
        "peut_administrer": acces.peut_administrer(request.user),
    })


def page_introuvable(request, *args, **kwargs):
    raise Http404()
