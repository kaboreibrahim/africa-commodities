from django.contrib.auth.backends import BaseBackend

from comptes import acces


class PermissionsAdminGroupe(BaseBackend):
    """
    Donne toutes les permissions de modèle à l'admin groupe, pour qu'il puisse utiliser l'admin
    sans être superutilisateur. N'authentifie personne.
    """

    def has_perm(self, user_obj, perm, obj=None):
        return acces.est_admin_groupe(user_obj)

    def has_module_perms(self, user_obj, app_label):
        return acces.est_admin_groupe(user_obj)
