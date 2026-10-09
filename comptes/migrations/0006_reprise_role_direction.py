"""
Le rôle global « Direction » disparaît au profit de l'habilitation Vue Groupe.

Chaque utilisateur Direction ACTIF reçoit une habilitation « toutes les sociétés, avec détail », pour que
personne ne perde d'accès le jour de la mise à jour ; puis le rôle global est remis à vide.

Annulation (`migrate comptes 0005`) : les utilisateurs repris automatiquement (motif ci-dessous) retrouvent
le rôle « direction » et leur habilitation est supprimée.
"""
from django.db import migrations

MOTIF = "Reprise automatique du rôle Direction"


def direction_vers_habilitation(apps, schema_editor):
    Utilisateur = apps.get_model("comptes", "Utilisateur")
    Habilitation = apps.get_model("comptes", "HabilitationVueGroupe")
    for user in Utilisateur.objects.filter(role_global="direction"):
        if user.is_active:
            Habilitation.objects.get_or_create(
                utilisateur=user,
                defaults={"portee": "toutes", "detail_autorise": True, "actif": True, "motif": MOTIF},
            )
    Utilisateur.objects.filter(role_global="direction").update(role_global="")


def habilitation_vers_direction(apps, schema_editor):
    Utilisateur = apps.get_model("comptes", "Utilisateur")
    Habilitation = apps.get_model("comptes", "HabilitationVueGroupe")
    repris = Habilitation.objects.filter(motif=MOTIF)
    Utilisateur.objects.filter(pk__in=repris.values("utilisateur_id"), role_global="").update(role_global="direction")
    repris.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("comptes", "0005_habilitations"),
    ]

    operations = [
        migrations.RunPython(direction_vers_habilitation, habilitation_vers_direction),
    ]
