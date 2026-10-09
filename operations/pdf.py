"""
Récapitulatifs PDF (une ligne, ou une liste de lignes). Aucune règle de calcul ici : les montants viennent des lignes
(répartition figée à l'enregistrement) et des totaux calculés par `operations.selectors.totaux`.
Polices intégrées de ReportLab (Helvetica) : pas de fichier de police à déployer.
"""
from decimal import Decimal
from io import BytesIO

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

VERT = colors.HexColor("#0B3D24")
OR = colors.HexColor("#B8861C")
CLAIR = colors.HexColor("#E6EDEA")
BORD = colors.HexColor("#C9D3CD")
GRIS = colors.HexColor("#5F6B63")

POSTES = (("part_charges", "Charges"), ("part_africa_commodities", "Africa Commodities"), ("part_risques", "Risques"),
          ("part_provision", "Provision"), ("part_comptes", "Comptes"))


def montant(valeur) -> str:
    """1250000 -> « 1 250 000 » (espace ordinaire : Helvetica n'a pas l'espace fine insécable)."""
    return f"{Decimal(valeur or 0):,.0f}".replace(",", " ")


def fcfa(valeur) -> str:
    return f"{montant(valeur)} F"


def _styles():
    base = getSampleStyleSheet()
    return {
        "titre": ParagraphStyle("titre", parent=base["Title"], fontName="Helvetica-Bold", fontSize=17, textColor=VERT,
                                alignment=0, spaceAfter=2),
        "sous": ParagraphStyle("sous", parent=base["Normal"], fontSize=9.5, textColor=GRIS, spaceAfter=10),
        "texte": ParagraphStyle("texte", parent=base["Normal"], fontSize=9.5, leading=12),
        "petit": ParagraphStyle("petit", parent=base["Normal"], fontSize=8, leading=10, textColor=GRIS),
    }


def _pied(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GRIS)
    largeur, _ = doc.pagesize
    canvas.drawString(doc.leftMargin, 9 * mm, "Africa Commodities & Renewables Group - Pilotage des marges - document confidentiel")
    canvas.drawRightString(largeur - doc.rightMargin, 9 * mm,
                           f"Édité le {timezone.localtime():%d/%m/%Y à %H:%M} - page {doc.page}")
    canvas.setStrokeColor(OR)
    canvas.setLineWidth(1)
    canvas.line(doc.leftMargin, 13 * mm, largeur - doc.rightMargin, 13 * mm)
    canvas.restoreState()


def _document(titre: str, pagesize):
    tampon = BytesIO()
    doc = SimpleDocTemplate(tampon, pagesize=pagesize, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm,
                            bottomMargin=20 * mm, title=titre, author="Pilotage des marges")
    return tampon, doc


def pdf_ligne(ligne, societe) -> bytes:
    """Récapitulatif d'une ligne : informations, répartition figée et règle appliquée."""
    st = _styles()
    titre = f"{societe.libelle_ligne.capitalize()} {ligne.reference}"
    tampon, doc = _document(titre, A4)
    regle = ligne.regle

    elements = [
        Paragraph(titre, st["titre"]),
        Paragraph(f"{societe.nom} ({societe.code.upper()}) - {ligne.date:%d/%m/%Y}", st["sous"]),
    ]
    infos = [
        ["Date", f"{ligne.date:%d/%m/%Y}"],
        [societe.libelle_reference, ligne.reference],
        ["N° de projet", ligne.projet or "-"],
        ["Client", ligne.client.nom if ligne.client else "-"],
    ]
    if societe.champ_extra_type:
        infos.append([societe.champ_extra_libelle, ligne.extra or "-"])
    infos += [
        [societe.libelle_quantite, montant(ligne.quantite)],
        [societe.libelle_marge, fcfa(ligne.marge_unitaire)],
        ["Marge totale", fcfa(ligne.marge_totale)],
        ["Observation", Paragraph(ligne.observation or "-", st["texte"])],
    ]
    tableau = Table(infos, colWidths=[55 * mm, 120 * mm])
    tableau.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), GRIS), ("LINEBELOW", (0, 0), (-1, -1), 0.4, BORD),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("FONTNAME", (1, 7 if societe.champ_extra_type else 6), (1, 7 if societe.champ_extra_type else 6), "Helvetica-Bold"),
    ]))
    elements += [tableau, Spacer(1, 10 * mm), Paragraph("Répartition de la marge", st["titre"])]

    total = Decimal(ligne.marge_totale or 0)
    lignes = [["Poste", "Montant", "Part de la marge"]]
    for champ, nom in POSTES:
        valeur = getattr(ligne, champ)
        part = f"{(Decimal(valeur) / total * 100):.1f} %".replace(".", ",") if total else "-"
        lignes.append([nom, fcfa(valeur), part])
    lignes.append(["TOTAL", fcfa(total), "100 %" if total else "-"])
    repartition = Table(lignes, colWidths=[70 * mm, 55 * mm, 50 * mm])
    repartition.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), VERT), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("LINEBELOW", (0, 1), (-1, -2), 0.4, BORD),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F8FAF7")]),
        ("BACKGROUND", (0, -1), (-1, -1), CLAIR), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 1, VERT),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    elements += [repartition, Spacer(1, 6 * mm), Paragraph(
        f"Règle appliquée (en vigueur au {regle.date_debut:%d/%m/%Y}) : {montant(regle.pct_charges)} % de la marge aux charges ; "
        f"{montant(regle.pct_africa_commodities)} % du reste à Africa Commodities ; solde partagé en "
        f"{regle.parts_risques} / {regle.parts_provision} / {regle.parts_comptes} parts "
        f"(risques / provision / comptes). La répartition est figée à l'enregistrement.", st["petit"])]
    doc.build(elements, onFirstPage=_pied, onLaterPages=_pied)
    return tampon.getvalue()


def pdf_recap(societe, lignes, totaux, periode: str) -> bytes:
    """Récapitulatif d'une liste de lignes (paysage) avec totaux. `periode` : « octobre 2026 », « année 2026 »…"""
    st = _styles()
    titre = f"Récapitulatif - {societe.nom} - {periode}"
    tampon, doc = _document(titre, landscape(A4))
    extra = bool(societe.champ_extra_type)

    entete = ["Date", "Référence", "Projet", "Client"] + ([societe.champ_extra_libelle] if extra else []) + [
        "Qté", "Marge unit.", "Marge totale", "Charges", "Africa Com.", "Risques", "Provision", "Comptes"]
    donnees = [entete]
    for l in lignes:
        donnees.append([f"{l.date:%d/%m/%Y}", l.reference, l.projet or "", (l.client.nom if l.client else "")[:24]]
                       + ([l.extra] if extra else [])
                       + [montant(l.quantite), montant(l.marge_unitaire), montant(l.marge_totale), montant(l.part_charges),
                          montant(l.part_africa_commodities), montant(l.part_risques), montant(l.part_provision),
                          montant(l.part_comptes)])
    nb_texte = 4 + (1 if extra else 0)
    pied = ["TOTAL"] + [""] * (nb_texte - 1) + [montant(totaux["quantite"]), "", montant(totaux["marge"]),
                                                 montant(totaux["charges"]), montant(totaux["africa_commodities"]),
                                                 montant(totaux["risques"]), montant(totaux["provision"]),
                                                 montant(totaux["comptes"])]
    donnees.append(pied)

    tableau = Table(donnees, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), VERT), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (nb_texte, 0), (-1, -1), "RIGHT"), ("LINEBELOW", (0, 1), (-1, -2), 0.3, BORD),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F8FAF7")]),
        ("BACKGROUND", (0, -1), (-1, -1), CLAIR), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 1, VERT), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    tableau.setStyle(TableStyle(style))

    nb = totaux["nb_lignes"]
    elements = [
        Paragraph(f"Récapitulatif des {societe.libelle_ligne_pluriel}", st["titre"]),
        Paragraph(f"{societe.nom} ({societe.code.upper()}) - {periode} - {nb} ligne{'s' if nb > 1 else ''} - "
                  f"marge totale {fcfa(totaux['marge'])}", st["sous"]),
        tableau if nb else Paragraph("Aucun enregistrement pour cette période.", st["texte"]),
    ]
    doc.build(elements, onFirstPage=_pied, onLaterPages=_pied)
    return tampon.getvalue()


def pdf_groupe(synthese, total, mois_texte: str, portee_texte: str) -> bytes:
    """Synthèse de la Vue Groupe pour un mois (paysage) : une ligne par société de la portée, puis le total."""
    st = _styles()
    tampon, doc = _document(f"Vue Groupe - {mois_texte}", landscape(A4))

    def pourcent(valeur) -> str:
        return f"{Decimal(valeur or 0):.1f} %".replace(".", ",")

    def couverture(r) -> str:
        c = r["couverture"]
        if not c.depenses_saisies:
            return "non saisies"
        return f"{'OK' if c.couvert else 'A couvrir'} {pourcent(c.taux)}"

    entete = ["Société", "Quantité", "Marge", "Objectif", "Atteint", "Charges", "Africa Com.", "Risques", "Provision",
              "Comptes", "Dépenses", "Couverture"]
    donnees = [entete]
    for r in synthese:
        s = r["societe"]
        donnees.append([s.nom[:26], f"{montant(r['quantite'])} {s.unite}", montant(r["marge"]), montant(r["objectif"]),
                        pourcent(r["progression"]) + (" (OK)" if r["objectif_atteint"] else ""), montant(r["charges"]),
                        montant(r["africa_commodities"]), montant(r["risques"]), montant(r["provision"]),
                        montant(r["comptes"]), montant(r["depenses"]) if r["couverture"].depenses_saisies else "-",
                        couverture(r)])
    donnees.append(["TOTAL GROUPE", "", montant(total["marge"]), montant(total["objectif"]), pourcent(total["progression"]),
                    montant(total["charges"]), montant(total["africa_commodities"]), montant(total["risques"]),
                    montant(total["provision"]), montant(total["comptes"]), montant(total["depenses"]) if total["depenses"] else "-", ""])
    tableau = Table(donnees, repeatRows=1)
    tableau.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), VERT), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-2, -1), "RIGHT"), ("LINEBELOW", (0, 1), (-1, -2), 0.3, BORD),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F8FAF7")]),
        ("BACKGROUND", (0, -1), (-1, -1), CLAIR), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 1, VERT), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    n = len(synthese)
    elements = [
        Paragraph("Vue Groupe - synthèse du mois", st["titre"]),
        Paragraph(f"{mois_texte} - {portee_texte} - {n} société{'s' if n > 1 else ''} - marge du groupe "
                  f"{fcfa(total['marge'])} - total Africa Commodities {fcfa(total['africa_commodities'])}", st["sous"]),
        tableau,
        Spacer(1, 4 * mm),
        Paragraph("Couverture = part charges / dépenses du mois (OK : charges couvertes). Les totaux ne portent que sur "
                  "les sociétés de votre portée.", st["petit"]),
    ]
    doc.build(elements, onFirstPage=_pied, onLaterPages=_pied)
    return tampon.getvalue()
