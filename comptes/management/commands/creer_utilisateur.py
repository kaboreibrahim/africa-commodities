"""
Crée un compte avec un mot de passe provisoire fort, affiché une seule fois.

    python manage.py creer_utilisateur --email awa@exemple.ci --nom Kone --prenom Awa \\
        --societe ooa:responsable --societe anl:lecture
    python manage.py creer_utilisateur --email dg@exemple.ci --nom Diallo --prenom Moussa --role-global direction
"""
import secrets
import string

from allauth.account.models import EmailAddress
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from comptes.models import Affectation, Utilisateur
from societes.models import Societe

ALPHABET = string.ascii_letters + string.digits + "-_.!@#%+="


def mot_de_passe_aleatoire(longueur: int = 20) -> str:
    """Mot de passe aléatoire (module `secrets`) contenant minuscule, majuscule, chiffre et symbole."""
    while True:
        mdp = "".join(secrets.choice(ALPHABET) for _ in range(longueur))
        if (any(c.islower() for c in mdp) and any(c.isupper() for c in mdp)
                and any(c.isdigit() for c in mdp) and any(not c.isalnum() for c in mdp)):
            return mdp


class Command(BaseCommand):
    help = "Crée un utilisateur avec un mot de passe provisoire (à changer à la première connexion)."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--nom", required=True)
        parser.add_argument("--prenom", required=True)
        parser.add_argument("--telephone", default="")
        parser.add_argument("--role-global", choices=[r for r in Utilisateur.RoleGlobal.values if r], default="")
        parser.add_argument("--societe", action="append", default=[], metavar="CODE:ROLE",
                            help=f"Affectation, ex. ooa:responsable. Rôles : {', '.join(Affectation.Role.values)}. "
                                 "Option répétable.")

    def handle(self, *args, **options):
        email = Utilisateur.objects.normalize_email(options["email"]).lower()
        if Utilisateur.objects.filter(email__iexact=email).exists():
            raise CommandError(f"Un compte existe déjà pour {email}.")
        affectations = [self.lire_affectation(valeur) for valeur in options["societe"]]
        if not options["role_global"] and not affectations:
            raise CommandError("Indiquez --role-global et/ou au moins une --societe CODE:ROLE.")

        mot_de_passe = mot_de_passe_aleatoire()
        user = Utilisateur(username=email, email=email, first_name=options["prenom"], last_name=options["nom"],
                           telephone=options["telephone"], role_global=options["role_global"],
                           doit_changer_mot_de_passe=True)
        try:
            user.full_clean(exclude=["password"])
            validate_password(mot_de_passe, user)
        except ValidationError as erreur:
            raise CommandError("; ".join(erreur.messages)) from erreur

        with transaction.atomic():
            user.set_password(mot_de_passe)
            user.save()
            EmailAddress.objects.create(user=user, email=email, primary=True, verified=True)
            for societe, role in affectations:
                Affectation.objects.create(utilisateur=user, societe=societe, role=role)

        self.stdout.write(self.style.SUCCESS(f"Compte créé : {user.get_full_name()} <{email}>"))
        for societe, role in affectations:
            self.stdout.write(f"  - {societe.nom} : {Affectation.Role(role).label}")
        self.stdout.write("Mot de passe provisoire (affiché UNE SEULE FOIS, à transmettre par un canal sûr) :")
        self.stdout.write(f"  {mot_de_passe}")
        self.stdout.write("Il devra être changé à la première connexion.")

    @staticmethod
    def lire_affectation(valeur: str):
        code, _, role = valeur.partition(":")
        if role not in Affectation.Role.values:
            raise CommandError(f"Rôle inconnu dans « {valeur} » (attendu : {', '.join(Affectation.Role.values)}).")
        societe = Societe.objects.filter(code=code.strip().lower()).first()
        if societe is None:
            raise CommandError(f"Société inconnue : « {code} ».")
        return societe, role
