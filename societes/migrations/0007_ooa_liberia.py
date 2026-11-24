"""
Noms courts des sociétés existantes (graphiques du groupe) et création d'Oils of Africa
Corporation Liberia : même activité et mêmes libellés qu'Oils of Africa, pour le Liberia.
"""
from django.db import migrations

NOMS_COURTS = {"alon": "ALON Prop.", "mlp": "Mon Livreur Pro"}

OOA_LIBERIA = dict(
    nom="Oils of Africa Corporation Liberia",
    nom_court="OOA Liberia",
    ordre=1,  # juste après Oils of Africa (même ordre, puis tri par nom)
    libelle_ligne="dossier", libelle_ligne_pluriel="dossiers",
    libelle_reference="N° conteneur / référence",
    libelle_quantite="Nb de conteneurs", libelle_marge="Marge par conteneur",
    unite="conteneur", marge_defaut=100000, objectif_defaut=1000000,
    couleur_principale="#1B7A2E", couleur_foncee="#0E5A1E", couleur_accent="#E8720C",
    couleur_serie="#2BA88C",  # teinte distincte d'OOA dans les graphiques du groupe
)


def creer(apps, schema_editor):
    Societe = apps.get_model("societes", "Societe")
    for code, nom_court in NOMS_COURTS.items():
        Societe.objects.filter(code=code, nom_court="").update(nom_court=nom_court)
    Societe.objects.get_or_create(code="ooa-lr", defaults=OOA_LIBERIA)


def supprimer(apps, schema_editor):
    Societe = apps.get_model("societes", "Societe")
    Societe.objects.filter(code="ooa-lr").delete()


class Migration(migrations.Migration):
    dependencies = [("societes", "0006_nom_court")]
    operations = [migrations.RunPython(creer, supprimer)]
