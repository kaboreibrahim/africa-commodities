from django.conf import settings

_BACKENDS_SANS_ENVOI = ("console", "dummy", "locmem", "filebased")


def envoi_email_configure() -> bool:
    """Vrai si le projet peut réellement envoyer des e-mails (sert à proposer « Mot de passe oublié »)."""
    backend = settings.EMAIL_BACKEND.lower()
    if any(nom in backend for nom in _BACKENDS_SANS_ENVOI):
        return False
    if backend.endswith("smtp.emailbackend"):
        return settings.EMAIL_HOST not in ("", "localhost", "127.0.0.1")
    return True


def authentification(request):
    return {"email_configure": envoi_email_configure()}
