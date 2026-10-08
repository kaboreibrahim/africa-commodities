from django.urls import path

from . import views

app_name = "interface"

urlpatterns = [
    path("", views.AccueilView.as_view(), name="accueil"),
    path("onglets/", views.OngletsView.as_view(), name="onglets"),
    path("theme/<slug:code>.css", views.theme_css, name="theme"),
    path("groupe/", views.VueGroupeView.as_view(), name="groupe"),
    path("regle/", views.RegleView.as_view(), name="regle"),
    path("s/<slug:code_societe>/", views.TableauDeBordView.as_view(), name="tableau"),
    path("s/<slug:code_societe>/objectif/", views.ObjectifView.as_view(), name="objectif"),
    path("s/<slug:code_societe>/lignes/", views.PageAVenirView.as_view(section="lignes"), name="lignes"),
    path("s/<slug:code_societe>/clients/", views.PageAVenirView.as_view(section="clients"), name="clients"),
    path("s/<slug:code_societe>/corbeille/", views.PageAVenirView.as_view(section="corbeille"), name="corbeille"),
]
