from allauth.account.adapter import DefaultAccountAdapter


class AdaptateurCompte(DefaultAccountAdapter):
    """Pas d'inscription publique : les comptes sont créés par l'admin groupe."""

    def is_open_for_signup(self, request):
        return False
