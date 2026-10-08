from django.http import Http404


def page_introuvable(request, *args, **kwargs):
    raise Http404()
