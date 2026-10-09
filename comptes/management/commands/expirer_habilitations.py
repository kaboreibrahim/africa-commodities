"""
Désactive les habilitations dont la date de fin est dépassée et journalise ces expirations.

    python manage.py expirer_habilitations

À planifier chaque jour (cron / minuteur systemd, voir l'étape 5). Les droits sont DÉJÀ refusés à la lecture
grâce aux dates (`comptes/acces.py`) : cette commande ne sert qu'à garder une base propre et un journal complet.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from comptes.journal import journaliser, par_service
from comptes.models import Affectation, HabilitationVueGroupe, JournalSecurite


class Command(BaseCommand):
    help = "Passe actif=False sur les habilitations expirées et journalise l'expiration."

    def handle(self, *args, **options):
        aujourd_hui = timezone.localdate()
        nombre = 0
        jeton = par_service.set(True)  # l'entrée détaillée est écrite ici : pas de doublon par les signaux
        try:
            with transaction.atomic():
                for a in Affectation.objects.filter(actif=True, date_fin__lt=aujourd_hui).select_related("utilisateur", "societe"):
                    a.actif = False
                    a.save()
                    journaliser(JournalSecurite.Evenement.HABILITATION_EXPIREE, type="acces_societe",
                                cible_id=a.utilisateur_id, cible_email=a.utilisateur.email, societe=a.societe.code,
                                role=a.role, date_fin=a.date_fin)
                    nombre += 1
                for h in HabilitationVueGroupe.objects.filter(actif=True, date_fin__lt=aujourd_hui).select_related("utilisateur"):
                    h.actif = False
                    h.save()
                    journaliser(JournalSecurite.Evenement.HABILITATION_EXPIREE, type="vue_groupe",
                                cible_id=h.utilisateur_id, cible_email=h.utilisateur.email, portee=h.portee,
                                date_fin=h.date_fin)
                    nombre += 1
        finally:
            par_service.reset(jeton)
        self.stdout.write(f"{nombre} habilitation(s) expirée(s) désactivée(s).")
