"""
Liste toutes les habilitations EN VIGUEUR, par utilisateur (revue d'accès trimestrielle).

    python manage.py rapport_habilitations                 # tableau lisible
    python manage.py rapport_habilitations --format csv > habilitations.csv
"""
import csv

from django.core.management.base import BaseCommand
from django.utils import timezone

from comptes.models import Affectation, HabilitationVueGroupe, Utilisateur

COLONNES = ["email", "nom", "compte_actif", "role_groupe", "type", "perimetre", "droit", "detail_vue_groupe",
            "valable_du", "valable_jusqu_au", "motif", "accorde_par"]


def lignes_du_rapport(le=None) -> list[list[str]]:
    """Une ligne par habilitation en vigueur (accès société ou Vue Groupe), triées par e-mail."""
    le = le or timezone.localdate()
    lignes = []

    def base(user):
        return [user.email, user.get_full_name(), "oui" if user.is_active else "non",
                user.get_role_global_display() if user.role_global else ""]

    def periode(h):
        return [h.date_debut.isoformat() if h.date_debut else "", h.date_fin.isoformat() if h.date_fin else "",
                h.motif, h.accorde_par.email if h.accorde_par else ""]

    for a in (Affectation.objects.en_vigueur(le).select_related("utilisateur", "societe", "accorde_par")):
        lignes.append(base(a.utilisateur) + ["accès société", a.societe.code, a.get_role_display(), ""] + periode(a))
    for h in (HabilitationVueGroupe.objects.en_vigueur(le).select_related("utilisateur", "accorde_par")
              .prefetch_related("societes")):
        perimetre = "toutes les sociétés" if h.portee == h.Portee.TOUTES else ", ".join(sorted(s.code for s in h.societes.all()))
        lignes.append(base(h.utilisateur) + ["Vue Groupe", perimetre, "consolidé", "oui" if h.detail_autorise else "non"]
                      + periode(h))
    for admin in Utilisateur.objects.filter(is_active=True, role_global=Utilisateur.RoleGlobal.ADMIN_GROUPE):
        lignes.append(base(admin) + ["administrateur groupe", "toutes les sociétés", "tous les droits", "oui", "", "", "", ""])
    return sorted(lignes, key=lambda ligne: (ligne[0], ligne[4], ligne[5]))


class Command(BaseCommand):
    help = "Rapport des habilitations en vigueur (accès société et Vue Groupe), pour les revues d'accès."

    def add_arguments(self, parser):
        parser.add_argument("--format", choices=["texte", "csv"], default="texte")

    def handle(self, *args, **options):
        lignes = lignes_du_rapport()
        if options["format"] == "csv":
            ecrivain = csv.writer(self.stdout, delimiter=";", lineterminator="\n")
            ecrivain.writerow(COLONNES)
            ecrivain.writerows(lignes)
            return
        if not lignes:
            self.stdout.write("Aucune habilitation en vigueur.")
            return
        precedent = None
        for ligne in lignes:
            if ligne[0] != precedent:
                precedent = ligne[0]
                etat = "" if ligne[2] == "oui" else "  [COMPTE DÉSACTIVÉ]"
                self.stdout.write(self.style.MIGRATE_HEADING(f"\n{ligne[1] or ligne[0]} <{ligne[0]}>{etat}"))
            fin = f" jusqu'au {ligne[9]}" if ligne[9] else ""
            detail = " (avec détail)" if ligne[7] == "oui" and ligne[4] == "Vue Groupe" else ""
            self.stdout.write(f"  - {ligne[4]} : {ligne[5]} — {ligne[6]}{detail}{fin}"
                              + (f"  « {ligne[10]} »" if ligne[10] else ""))
        self.stdout.write(f"\n{len(lignes)} habilitation(s) en vigueur au {timezone.localdate():%d/%m/%Y}.")
