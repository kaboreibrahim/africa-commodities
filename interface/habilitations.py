"""
Logique de l'écran « Habilitations » : plan des changements (aperçu avant confirmation), application via
`comptes/services.py`, aperçu « Ce que voit cette personne » (calculé avec `comptes/acces.py`), badges et matrice.
Aucune règle d'accès n'est recalculée ici.
"""
from dataclasses import dataclass
from datetime import date, timedelta

from django.conf import settings
from django.utils import timezone

from comptes import acces, services
from comptes.models import Affectation, HabilitationVueGroupe, Utilisateur
from societes.models import Societe

ROLES_COURTS = {"responsable": "Responsable", "saisie": "Saisie", "lecture": "Lecture"}
LETTRES = {acces.ADMIN_GROUPE: "A", acces.RESPONSABLE: "R", acces.SAISIE: "S", acces.LECTURE: "L", acces.LECTURE_GROUPE: "G"}
LIBELLES_LETTRES = {"A": "Administrateur groupe", "R": "Responsable", "S": "Saisie", "L": "Lecture",
                    "G": "Lecture via la Vue Groupe", "—": "Aucun accès"}
PORTEE = HabilitationVueGroupe.Portee


def etat_periode(h, aujourd_hui: date | None = None) -> str:
    """« vigueur », « expiree » ou « future » pour une habilitation active (Affectation ou HabilitationVueGroupe)."""
    jour = aujourd_hui or timezone.localdate()
    if h.date_fin and h.date_fin < jour:
        return "expiree"
    if h.date_debut and h.date_debut > jour:
        return "future"
    return "vigueur"


def _periode_texte(debut, fin) -> str:
    morceaux = []
    if debut:
        morceaux.append(f"à partir du {debut:%d/%m/%Y}")
    if fin:
        morceaux.append(f"jusqu'au {fin:%d/%m/%Y}")
    return f" ({', '.join(morceaux)})" if morceaux else ""


# --- Liste ----------------------------------------------------------------------------------

def badges_acces(utilisateur, aujourd_hui=None) -> list[dict]:
    """Un badge par accès société actif (les affectations doivent être préchargées : actif=True)."""
    badges = []
    for a in utilisateur.affectations.all():
        etat = etat_periode(a, aujourd_hui)
        badges.append({"code": a.societe.code, "libelle": f"{a.societe.code.upper()} · {ROLES_COURTS[a.role]}", "etat": etat,
                       "date_debut": a.date_debut, "date_fin": a.date_fin})
    return badges


def resume_vue_groupe(utilisateur, aujourd_hui=None) -> dict | None:
    """Résumé de la Vue Groupe d'une ligne de la liste (None si aucune habilitation active)."""
    h = getattr(utilisateur, "habilitation_groupe", None)
    if h is None or not h.actif:
        return None
    texte = "Toutes" if h.portee == PORTEE.TOUTES else ", ".join(s.code.upper() for s in sorted(h.societes.all(), key=lambda s: s.ordre))
    return {"texte": texte, "detail": h.detail_autorise, "etat": etat_periode(h, aujourd_hui), "date_fin": h.date_fin,
            "date_debut": h.date_debut}


# --- Plan et application des changements ---------------------------------------------------------

@dataclass
class Changement:
    genre: str  # « accorder », « modifier », « retirer »
    societe: Societe
    texte: str
    role: str = ""
    date_debut: date | None = None
    date_fin: date | None = None
    affectation: Affectation | None = None


def plan_acces(cible, demandes: dict) -> list[Changement]:
    """Compare les demandes du formulaire aux affectations existantes ; renvoie les changements à confirmer."""
    existantes = {a.societe_id: a for a in Affectation.objects.filter(utilisateur=cible).select_related("societe")}
    plan = []
    for d in demandes.values():
        s, role = d["societe"], d["role"]
        a = existantes.get(s.pk)
        code = s.code.upper()
        if a is not None and a.actif:
            if not role:
                plan.append(Changement("retirer", s, f"retirer l'accès {code} ({ROLES_COURTS[a.role]})", affectation=a))
            elif (role, d["date_debut"], d["date_fin"]) != (a.role, a.date_debut, a.date_fin):
                if role != a.role:
                    texte = f"passer {code} de {ROLES_COURTS[a.role]} à {ROLES_COURTS[role]}"
                else:
                    texte = f"modifier les dates de {code}"
                plan.append(Changement("modifier", s, texte + _periode_texte(d["date_debut"], d["date_fin"]), role,
                                       d["date_debut"], d["date_fin"], a))
        elif role:
            plan.append(Changement("accorder", s, f"donner {ROLES_COURTS[role]} sur {code}"
                                   + _periode_texte(d["date_debut"], d["date_fin"]), role, d["date_debut"], d["date_fin"], a))
    return plan


def appliquer_acces(admin, cible, plan: list[Changement], motif: str) -> None:
    """Applique le plan par les services (la transaction englobante de la vue annule tout en cas d'erreur)."""
    for c in plan:
        if c.genre == "retirer":
            services.retirer_acces_societe(admin, c.affectation, motif=motif)
        elif c.genre == "modifier":
            services.modifier_acces_societe(admin, c.affectation, role=c.role, date_debut=c.date_debut,
                                            date_fin=c.date_fin, motif=motif)
        else:
            services.accorder_acces_societe(admin, cible, c.societe, c.role, date_debut=c.date_debut,
                                            date_fin=c.date_fin, motif=motif)


@dataclass
class ChangementGroupe:
    genre: str  # « accorder », « modifier », « retirer »
    texte: str
    donnees: dict


def _decrire_groupe(portee, societes, detail, debut, fin) -> str:
    if portee == PORTEE.TOUTES:
        perimetre = "toutes les sociétés (y compris les futures)"
    else:
        perimetre = "sociétés " + ", ".join(s.code.upper() for s in societes)
    return f"{perimetre}, détail {'autorisé (lecture seule)' if detail else 'non autorisé'}{_periode_texte(debut, fin)}"


def plan_vue_groupe(cible, nettoye: dict) -> ChangementGroupe | None:
    """Changement de Vue Groupe demandé par le formulaire (None si rien ne change)."""
    h = HabilitationVueGroupe.objects.filter(utilisateur=cible).first()
    if not nettoye.get("autoriser"):
        if h is not None and h.actif:
            return ChangementGroupe("retirer", "retirer la Vue Groupe", {})
        return None
    portee = nettoye.get("portee") or PORTEE.TOUTES
    societes = [] if portee == PORTEE.TOUTES else list(nettoye.get("societes") or [])
    donnees = {"portee": portee, "societes": societes, "detail_autorise": bool(nettoye.get("detail_autorise")),
               "date_debut": nettoye.get("date_debut"), "date_fin": nettoye.get("date_fin")}
    description = _decrire_groupe(portee, societes, donnees["detail_autorise"], donnees["date_debut"], donnees["date_fin"])
    if h is None or not h.actif:
        return ChangementGroupe("accorder", f"accorder la Vue Groupe : {description}", donnees)
    actuel = (h.portee, {s.pk for s in h.societes.all()}, h.detail_autorise, h.date_debut, h.date_fin)
    demande = (portee, {s.pk for s in societes}, donnees["detail_autorise"], donnees["date_debut"], donnees["date_fin"])
    if actuel == demande:
        return None
    return ChangementGroupe("modifier", f"modifier la Vue Groupe : {description}", donnees)


def appliquer_vue_groupe(admin, cible, changement: ChangementGroupe, motif: str) -> None:
    if changement.genre == "retirer":
        services.retirer_vue_groupe(admin, cible, motif=motif)
    elif changement.genre == "accorder":
        services.accorder_vue_groupe(admin, cible, motif=motif, **changement.donnees)
    else:
        h = HabilitationVueGroupe.objects.get(utilisateur=cible)
        services.modifier_vue_groupe(admin, h, motif=motif, **changement.donnees)


# --- Aperçu « Ce que voit cette personne » --------------------------------------------------------

def apercu_droits(cible) -> dict:
    """Droits effectifs de `cible`, calculés par comptes/acces.py sur un objet utilisateur neuf (sans cache)."""
    u = Utilisateur.objects.get(pk=cible.pk)
    societes = list(Societe.objects.filter(actif=True))
    lignes = []
    for s in societes:
        role = acces.role_sur(u, s)
        if role is None:
            actions = "Aucun accès"
        elif acces.peut_gerer_societe(u, s):
            actions = "Lire, saisir, gérer (clients, objectifs, corbeille)"
        elif acces.peut_saisir(u, s):
            actions = "Lire et saisir"
        else:
            actions = "Lire seulement"
        lignes.append({"societe": s, "role": LETTRES.get(role, "—"), "actions": actions, "acces": role is not None})
    groupe = acces.habilitation_groupe(u)
    voit_groupe = acces.voit_vue_groupe(u)
    onglets = [l["societe"].nom for l in lignes if l["acces"]]
    pages = list(onglets)
    if voit_groupe:
        pages.append("Vue Groupe")
    pages.append("Règle de répartition")
    if acces.peut_administrer(u):
        pages.append("Habilitations (administration)")
    expirations = []
    for a in Affectation.objects.en_vigueur().filter(utilisateur=u, date_fin__isnull=False).select_related("societe"):
        expirations.append(f"Accès {a.societe.code.upper()} : jusqu'au {a.date_fin:%d/%m/%Y}")
    if groupe is not None and groupe.date_fin:
        expirations.append(f"Vue Groupe : jusqu'au {groupe.date_fin:%d/%m/%Y}")
    return {
        "compte_actif": u.is_active, "admin": acces.est_admin_groupe(u), "pages": pages, "lignes": lignes,
        "voit_groupe": voit_groupe,
        "portee_toutes": acces.portee_vue_groupe(u) == acces.TOUTES,
        "societes_groupe": list(acces.societes_vue_groupe(u)) if voit_groupe else [],
        "detail_groupe": bool(groupe and groupe.detail_autorise) and not acces.est_admin_groupe(u),
        "expirations": expirations,
        "mfa_obligatoire": bool(acces.roles_de(u) & set(settings.MFA_ROLES_OBLIGATOIRES)),
    }


# --- Matrice -------------------------------------------------------------------------------------

def matrice(utilisateurs) -> tuple[list[Societe], list[dict]]:
    """Utilisateurs en lignes, sociétés en colonnes (+ Vue Groupe). Cellule : lettre R/S/L/G/A ou « — »."""
    societes = list(Societe.objects.filter(actif=True))
    lignes = []
    for u in utilisateurs:
        cellules = []
        for s in societes:
            lettre = LETTRES.get(acces.role_sur(u, s), "—")
            cellules.append({"lettre": lettre, "libelle": LIBELLES_LETTRES[lettre]})
        portee = acces.portee_vue_groupe(u)
        if acces.est_admin_groupe(u):
            groupe = {"lettre": "T", "libelle": "Toutes les sociétés (administrateur)"}
        elif portee == PORTEE.TOUTES:
            groupe = {"lettre": "T", "libelle": "Vue Groupe : toutes les sociétés"}
        elif portee:
            n = acces.societes_vue_groupe(u).count()
            groupe = {"lettre": "S", "libelle": f"Vue Groupe : {n} sociétés sélectionnées"}
        else:
            groupe = {"lettre": "—", "libelle": "Pas de Vue Groupe"}
        lignes.append({"utilisateur": u, "cellules": cellules, "groupe": groupe})
    return societes, lignes


def expire_dans(jours: int = 30) -> tuple[date, date]:
    aujourd_hui = timezone.localdate()
    return aujourd_hui, aujourd_hui + timedelta(days=jours)
