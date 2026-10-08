"""Validateurs de fichiers envoyés (logos des sociétés)."""
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.utils.deconstruct import deconstructible
from PIL import Image, UnidentifiedImageError

EXTENSIONS_IMAGE = ["png", "jpg", "jpeg", "webp"]
FORMATS_IMAGE = {"PNG", "JPEG", "WEBP"}

valider_extension_image = FileExtensionValidator(
    EXTENSIONS_IMAGE, message="Formats acceptés : PNG, JPEG ou WEBP."
)


@deconstructible
class TailleMaximale:
    """Refuse un fichier plus lourd que `octets`."""

    def __init__(self, octets: int):
        self.octets = octets

    def __call__(self, fichier):
        if fichier.size > self.octets:
            raise ValidationError(f"Fichier trop lourd : {self.octets // (1024 * 1024)} Mo maximum.",
                                  code="fichier_trop_lourd")

    def __eq__(self, autre):
        return isinstance(autre, TailleMaximale) and autre.octets == self.octets


def valider_image_reelle(fichier):
    """Vérifie avec Pillow que le contenu est bien une image PNG, JPEG ou WEBP (pas un fichier renommé)."""
    position = fichier.tell() if hasattr(fichier, "tell") else 0
    try:
        fichier.seek(0)
        with Image.open(fichier) as image:
            format_detecte = image.format
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as erreur:
        raise ValidationError("Ce fichier n'est pas une image valide.", code="image_invalide") from erreur
    finally:
        fichier.seek(position)
    if format_detecte not in FORMATS_IMAGE:
        raise ValidationError("Formats acceptés : PNG, JPEG ou WEBP.", code="format_image")


taille_max_2_mo = TailleMaximale(2 * 1024 * 1024)
