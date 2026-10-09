from django.urls import path

from . import views, views_clients, views_habilitations, views_lignes

app_name = "interface"

urlpatterns = [
    path("", views.AccueilView.as_view(), name="accueil"),
    path("onglets/", views.OngletsView.as_view(), name="onglets"),
    path("theme/<slug:code>.css", views.theme_css, name="theme"),
    path("groupe/", views.VueGroupeView.as_view(), name="groupe"),
    path("groupe/recap.pdf", views.VueGroupePdfView.as_view(), name="groupe_pdf"),
    path("regle/", views.RegleView.as_view(), name="regle"),
    path("administration/habilitations/", views_habilitations.UtilisateursView.as_view(), name="habilitations"),
    path("administration/habilitations/matrice/", views_habilitations.MatriceView.as_view(), name="habilitations_matrice"),
    path("administration/habilitations/nouveau/", views_habilitations.NouvelUtilisateurView.as_view(),
         name="habilitation_nouveau"),
    path("administration/habilitations/<int:pk>/", views_habilitations.FicheView.as_view(), name="habilitation_fiche"),
    path("s/<slug:code_societe>/", views.TableauDeBordView.as_view(), name="tableau"),
    path("s/<slug:code_societe>/objectif/", views.ObjectifView.as_view(), name="objectif"),
    path("s/<slug:code_societe>/depenses/", views.DepensesView.as_view(), name="depenses"),
    path("s/<slug:code_societe>/lignes/", views_lignes.LignesView.as_view(), name="lignes"),
    path("s/<slug:code_societe>/lignes/apercu/", views_lignes.ApercuView.as_view(), name="apercu"),
    path("s/<slug:code_societe>/lignes/recap.pdf", views_lignes.LignesPdfView.as_view(), name="lignes_pdf"),
    path("s/<slug:code_societe>/lignes/<int:pk>/", views_lignes.LigneDetailView.as_view(), name="ligne_detail"),
    path("s/<slug:code_societe>/lignes/<int:pk>/recap.pdf", views_lignes.LignePdfView.as_view(), name="ligne_pdf"),
    path("s/<slug:code_societe>/lignes/<int:pk>/modifier/", views_lignes.LigneModifierView.as_view(),
         name="ligne_modifier"),
    path("s/<slug:code_societe>/lignes/<int:pk>/supprimer/", views_lignes.LigneSupprimerView.as_view(),
         name="ligne_supprimer"),
    path("s/<slug:code_societe>/lignes/<int:pk>/restaurer/", views_lignes.LigneRestaurerView.as_view(),
         name="ligne_restaurer"),
    path("s/<slug:code_societe>/lignes/champ-client/", views_clients.ChampClientView.as_view(), name="champ_client"),
    path("s/<slug:code_societe>/clients/", views_clients.ClientsView.as_view(), name="clients"),
    path("s/<slug:code_societe>/clients/<int:pk>/modifier/", views_clients.ClientModifierView.as_view(),
         name="client_modifier"),
    path("s/<slug:code_societe>/clients/<int:pk>/retirer/", views_clients.ClientRetirerView.as_view(),
         name="client_retirer"),
    path("s/<slug:code_societe>/corbeille/", views_lignes.CorbeilleView.as_view(), name="corbeille"),
]
