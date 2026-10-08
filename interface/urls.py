from django.urls import path

from . import views, views_lignes

app_name = "interface"

urlpatterns = [
    path("", views.AccueilView.as_view(), name="accueil"),
    path("onglets/", views.OngletsView.as_view(), name="onglets"),
    path("theme/<slug:code>.css", views.theme_css, name="theme"),
    path("groupe/", views.VueGroupeView.as_view(), name="groupe"),
    path("regle/", views.RegleView.as_view(), name="regle"),
    path("s/<slug:code_societe>/", views.TableauDeBordView.as_view(), name="tableau"),
    path("s/<slug:code_societe>/objectif/", views.ObjectifView.as_view(), name="objectif"),
    path("s/<slug:code_societe>/depenses/", views.DepensesView.as_view(), name="depenses"),
    path("s/<slug:code_societe>/lignes/", views_lignes.LignesView.as_view(), name="lignes"),
    path("s/<slug:code_societe>/lignes/apercu/", views_lignes.ApercuView.as_view(), name="apercu"),
    path("s/<slug:code_societe>/lignes/<int:pk>/modifier/", views_lignes.LigneModifierView.as_view(),
         name="ligne_modifier"),
    path("s/<slug:code_societe>/lignes/<int:pk>/supprimer/", views_lignes.LigneSupprimerView.as_view(),
         name="ligne_supprimer"),
    path("s/<slug:code_societe>/lignes/<int:pk>/restaurer/", views_lignes.LigneRestaurerView.as_view(),
         name="ligne_restaurer"),
    path("s/<slug:code_societe>/clients/", views.PageAVenirView.as_view(section="clients"), name="clients"),
    path("s/<slug:code_societe>/corbeille/", views_lignes.CorbeilleView.as_view(), name="corbeille"),
]
