from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from comptes.models import JournalSecurite


class Command(BaseCommand):
    help = "Supprime les entrées du journal de sécurité plus anciennes que la durée de rétention."

    def add_arguments(self, parser):
        parser.add_argument("--jours", type=int, default=365, help="Durée de rétention en jours (défaut : 365).")

    def handle(self, *args, **options):
        jours = options["jours"]
        if jours < 30:
            raise CommandError("La rétention doit être d'au moins 30 jours.")
        limite = timezone.now() - timedelta(days=jours)
        nombre, _ = JournalSecurite.objects.filter(date__lt=limite).delete()
        self.stdout.write(self.style.SUCCESS(
            f"{nombre} entrée(s) antérieure(s) au {timezone.localtime(limite):%d/%m/%Y} supprimée(s)."))
