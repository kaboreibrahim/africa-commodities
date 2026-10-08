"""Crée les 5 sociétés du groupe avec leurs libellés et leurs couleurs."""
from django.db import migrations

CONTENEUR = dict(libelle_ligne="dossier", libelle_ligne_pluriel="dossiers",
                 libelle_quantite="Nb de conteneurs", libelle_marge="Marge par conteneur",
                 unite="conteneur", marge_defaut=100000)

SOCIETES = [
    dict(code="ooa", nom="Oils of Africa", ordre=1, libelle_reference="N° conteneur / référence",
         couleur_principale="#1B7A2E", couleur_foncee="#0E5A1E", couleur_accent="#E8720C", couleur_serie="#1B7A2E",
         **CONTENEUR),
    dict(code="anl", nom="Africa Newport & Logistics", ordre=2, libelle_reference="N° dossier / BL",
         couleur_principale="#0B3A5C", couleur_foncee="#022F50", couleur_accent="#E8B820", couleur_serie="#2F6FB0",
         **{**CONTENEUR, "libelle_ligne": "dossier transit", "libelle_ligne_pluriel": "dossiers transit"}),
    dict(code="otl", nom="OTL & Bulk Liquid", ordre=3, libelle_reference="N° conteneur / référence",
         couleur_principale="#3F6B1A", couleur_foncee="#2B4D12", couleur_accent="#E3C51B", couleur_serie="#8E5BB5",
         **CONTENEUR),
    dict(code="alon", nom="ALON Properties", ordre=4, libelle_ligne="opération", libelle_ligne_pluriel="opérations",
         libelle_reference="Bien / référence", libelle_quantite="Nb (mois de loyer ou vente)",
         libelle_marge="Marge / commission unitaire", unite="opération", marge_defaut=100000,
         champ_extra_libelle="Type", champ_extra_type="choix", champ_extra_choix="Location, Vente",
         couleur_principale="#1B2540", couleur_foncee="#111827", couleur_accent="#B8892F", couleur_serie="#B8A21E"),
    dict(code="mlp", nom="Mon Livreur Pro", ordre=5, libelle_ligne="lot de livraisons",
         libelle_ligne_pluriel="lots de livraisons", libelle_reference="N° bon / course",
         libelle_quantite="Nb de livraisons", libelle_marge="Marge par livraison", unite="livraison",
         marge_defaut=1000, champ_extra_libelle="Zone", champ_extra_type="texte",
         couleur_principale="#00078A", couleur_foncee="#000566", couleur_accent="#F77B1F", couleur_serie="#E8720C"),
]


def creer(apps, schema_editor):
    Societe = apps.get_model("societes", "Societe")
    for s in SOCIETES:
        Societe.objects.update_or_create(code=s["code"], defaults={**s, "objectif_defaut": 1000000})


def supprimer(apps, schema_editor):
    apps.get_model("societes", "Societe").objects.filter(code__in=[s["code"] for s in SOCIETES]).delete()


class Migration(migrations.Migration):
    dependencies = [("societes", "0001_initial")]
    operations = [migrations.RunPython(creer, supprimer)]
