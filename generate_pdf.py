"""
generate_pdf.py — Genera PDF BriefToDeal (contratto / preventivo / onboarding).

Uso CLI:
  python generate_pdf.py file.json [contratto|preventivo|onboarding]
  python generate_pdf.py -  contratto       # legge JSON da stdin
"""

import io
import json
import os
import sys
from datetime import datetime, timedelta

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

# ── Brand colors ──────────────────────────────────────────────────────────────
PURPLE     = colors.HexColor('#7C3AED')
DARK       = colors.HexColor('#0D0D1A')
GRAY       = colors.HexColor('#6B7280')
LIGHT_GRAY = colors.HexColor('#F3F4F6')
GREEN      = colors.HexColor('#059669')
WHITE      = colors.white

TIPI_DOCUMENTO = {
    'contratto':  ('CONTRATTO DI FORNITURA SERVIZI', 'BTD'),
    'preventivo': ('PREVENTIVO COMMERCIALE',          'PRV'),
    'onboarding': ('DOCUMENTO DI ONBOARDING',         'ONB'),
}


# ── Stili ─────────────────────────────────────────────────────────────────────
def build_styles():
    styles = {
        'brand_title': ParagraphStyle(
            'brand_title', fontSize=32, fontName='Helvetica-Bold',
            textColor=PURPLE, alignment=TA_CENTER, spaceAfter=0,
        ),
        'doc_title': ParagraphStyle(
            'doc_title', fontSize=18, fontName='Helvetica-Bold',
            textColor=colors.black, alignment=TA_CENTER,
            spaceBefore=0, spaceAfter=4,
        ),
        'brand_sub': ParagraphStyle(
            'brand_sub', fontSize=9, fontName='Helvetica',
            textColor=GRAY, alignment=TA_CENTER, spaceAfter=0,
        ),
        'section_heading': ParagraphStyle(
            'section_heading', fontSize=11, fontName='Helvetica-Bold',
            textColor=PURPLE, spaceBefore=14, spaceAfter=6,
        ),
        'body': ParagraphStyle(
            'body', fontSize=9.5, fontName='Helvetica',
            textColor=DARK, leading=14, spaceAfter=4,
        ),
        'body_center': ParagraphStyle(
            'body_center', fontSize=9.5, fontName='Helvetica',
            textColor=DARK, leading=14, alignment=TA_CENTER,
        ),
        'welcome': ParagraphStyle(
            'welcome', fontSize=11, fontName='Helvetica',
            textColor=DARK, leading=17, spaceAfter=6,
        ),
        'label': ParagraphStyle(
            'label', fontSize=9, fontName='Helvetica-Bold', textColor=GRAY,
        ),
        'value': ParagraphStyle(
            'value', fontSize=10, fontName='Helvetica', textColor=DARK,
        ),
        'table_head': ParagraphStyle(
            'table_head', fontSize=9, fontName='Helvetica-Bold',
            textColor=WHITE, alignment=TA_CENTER,
        ),
        'table_cell': ParagraphStyle(
            'table_cell', fontSize=9, fontName='Helvetica',
            textColor=DARK, leading=13,
        ),
        'table_cell_bold': ParagraphStyle(
            'table_cell_bold', fontSize=9, fontName='Helvetica-Bold',
            textColor=DARK,
        ),
        'sign_label': ParagraphStyle(
            'sign_label', fontSize=9, fontName='Helvetica',
            textColor=GRAY, alignment=TA_CENTER,
        ),
        'footer_brand': ParagraphStyle(
            'footer_brand', fontSize=9, fontName='Helvetica-Bold',
            textColor=GRAY, alignment=TA_CENTER,
        ),
        'highlight': ParagraphStyle(
            'highlight', fontSize=10, fontName='Helvetica-Bold',
            textColor=PURPLE, alignment=TA_CENTER,
        ),
        'note': ParagraphStyle(
            'note', fontSize=8.5, fontName='Helvetica',
            textColor=GRAY, leading=12,
        ),
    }
    return styles


# ── Helper: tabella label/valore ──────────────────────────────────────────────
def data_table(rows, styles, col_widths=None):
    col_widths = col_widths or [5 * cm, 11.5 * cm]
    table_data = [
        [Paragraph(lbl, styles['label']), Paragraph(str(val), styles['value'])]
        for lbl, val in rows
    ]
    t = Table(table_data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [LIGHT_GRAY, WHITE]),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#E5E7EB')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
    ]))
    return t


# ── Helper: blocco firme ──────────────────────────────────────────────────────
def signature_table(styles):
    line = '_' * 32
    def col(label):
        inner = Table([[Paragraph(line, styles['body'])],
                        [Spacer(1, 4)],
                        [Paragraph(label, styles['sign_label'])]])
        inner.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
        return inner

    t = Table([[col('Firma del Fornitore'), col('Firma del Cliente')]],
              colWidths=[8.25 * cm, 8.25 * cm])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN',  (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
    ]))
    return t


# ── Helper: totale contratto ──────────────────────────────────────────────────
def calcola_totale(importo_mensile, durata_mesi):
    try:
        return f"EUR {float(importo_mensile) * int(durata_mesi):,.2f}"
    except (ValueError, TypeError):
        return 'N/D'


# ── Helper: header e footer comuni ───────────────────────────────────────────
def aggiungi_header(story, styles, titolo_doc, ref_prefix, nome_cliente):
    story.append(Paragraph('BriefToDeal', styles['brand_title']))
    story.append(Spacer(1, 20))
    story.append(Paragraph(titolo_doc, styles['doc_title']))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Generato il {datetime.today().strftime('%d/%m/%Y')} &nbsp;|&nbsp; "
        f"Rif. {ref_prefix}-{datetime.today().strftime('%Y%m%d')}-{nome_cliente[:3].upper()}",
        styles['brand_sub'],
    ))
    story.append(Spacer(1, 20))


def aggiungi_footer(story, styles, con_firma=True):
    if con_firma:
        story.append(Spacer(1, 30))
        story.append(signature_table(styles))
    story.append(Spacer(1, 15))
    story.append(HRFlowable(width='100%', thickness=0.5, color=GRAY,
                             spaceBefore=0, spaceAfter=0))
    story.append(Spacer(1, 8))
    story.append(Paragraph('BriefToDeal', styles['footer_brand']))


# ══════════════════════════════════════════════════════════════════════════════
# Layout 1 — CONTRATTO
# ══════════════════════════════════════════════════════════════════════════════
def _build_contratto(story, dati, styles):
    story.append(Paragraph('1. DATI DEL CLIENTE', styles['section_heading']))
    story.append(data_table([
        ('Nome e Cognome', dati['nome_cliente']),
        ('Azienda',        dati['azienda']),
    ], styles))

    story.append(Paragraph('2. OGGETTO DEL CONTRATTO', styles['section_heading']))
    story.append(data_table([
        ('Tipo di Servizio', dati['tipo_servizio']),
        ('Data di Inizio',   dati['data_inizio']),
        ('Durata',           f"{dati['durata_mesi']} mesi"),
    ], styles))

    story.append(Paragraph('3. CONDIZIONI ECONOMICHE', styles['section_heading']))
    story.append(data_table([
        ('Importo Mensile',   f"EUR {float(dati['importo_mensile']):,.2f}"),
        ('Durata Contratto',  f"{dati['durata_mesi']} mesi"),
        ('Valore Totale',     calcola_totale(dati['importo_mensile'], dati['durata_mesi'])),
        ('Modalita di Paga.', 'Bonifico bancario entro il 5 del mese'),
    ], styles))

    story.append(Paragraph('4. TERMINI E CONDIZIONI', styles['section_heading']))
    clausole = [
        "Il presente contratto entra in vigore alla data di firma di entrambe le parti e "
        "rimane valido per tutta la durata indicata, salvo disdetta scritta con preavviso di 30 giorni.",
        "Il Fornitore si impegna a erogare i servizi descritti con la massima diligenza "
        "professionale, nel rispetto delle tempistiche concordate.",
        "Il Cliente si impegna a corrispondere il corrispettivo mensile nei termini stabiliti. "
        "In caso di ritardo superiore a 15 giorni si applichera un interesse di mora pari al "
        "tasso BCE maggiorato di 8 punti percentuali.",
        "Eventuali modifiche al presente contratto dovranno essere concordate per iscritto "
        "e firmate da entrambe le parti.",
        "Per qualsiasi controversia le parti eleggono come foro competente quello del "
        "domicilio del Fornitore. Si applica la legge italiana.",
    ]
    for i, testo in enumerate(clausole, 1):
        story.append(Paragraph(f"{i}. {testo}", styles['body']))

    aggiungi_footer(story, styles, con_firma=True)


# ══════════════════════════════════════════════════════════════════════════════
# Layout 2 — PREVENTIVO
# ══════════════════════════════════════════════════════════════════════════════
def _build_preventivo(story, dati, styles):
    scadenza = (datetime.today() + timedelta(days=30)).strftime('%d/%m/%Y')

    # Dati cliente
    story.append(Paragraph('1. DATI DEL CLIENTE', styles['section_heading']))
    story.append(data_table([
        ('Nome e Cognome', dati['nome_cliente']),
        ('Azienda',        dati['azienda']),
    ], styles))

    # Descrizione servizi
    story.append(Paragraph('2. DESCRIZIONE SERVIZI', styles['section_heading']))
    story.append(data_table([
        ('Servizio Proposto', dati['tipo_servizio']),
        ('Data di Avvio',     dati['data_inizio']),
        ('Durata Prevista',   f"{dati['durata_mesi']} mesi"),
        ('Ambito',            'Consulenza e gestione operativa continuativa'),
    ], styles))

    # Dettaglio costi — tabella a 4 colonne con header colorato
    story.append(Paragraph('3. DETTAGLIO COSTI', styles['section_heading']))
    head = [
        Paragraph('Voce', styles['table_head']),
        Paragraph('Importo Mensile', styles['table_head']),
        Paragraph('Mesi', styles['table_head']),
        Paragraph('Totale', styles['table_head']),
    ]
    totale = calcola_totale(dati['importo_mensile'], dati['durata_mesi'])
    row1 = [
        Paragraph(dati['tipo_servizio'], styles['table_cell']),
        Paragraph(f"EUR {float(dati['importo_mensile']):,.2f}", styles['table_cell']),
        Paragraph(str(dati['durata_mesi']), styles['table_cell']),
        Paragraph(totale, styles['table_cell_bold']),
    ]
    row_tot = [
        Paragraph('TOTALE OFFERTA', styles['table_cell_bold']),
        Paragraph('', styles['table_cell']),
        Paragraph('', styles['table_cell']),
        Paragraph(totale, styles['table_cell_bold']),
    ]
    costi_t = Table([head, row1, row_tot],
                    colWidths=[6.5 * cm, 4 * cm, 2 * cm, 4 * cm])
    costi_t.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0),  PURPLE),
        ('BACKGROUND',    (0, 2), (-1, 2),  LIGHT_GRAY),
        ('GRID',          (0, 0), (-1, -1), 0.4, colors.HexColor('#E5E7EB')),
        ('ALIGN',         (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
    ]))
    story.append(costi_t)

    # Validità offerta
    story.append(Paragraph('4. VALIDITA OFFERTA', styles['section_heading']))
    story.append(data_table([
        ('Valida fino al', scadenza),
        ('Durata validita', '30 giorni dalla data di emissione'),
        ('Condizione',      'Soggetta a disponibilita e conferma scritta'),
    ], styles))

    # Condizioni di pagamento
    story.append(Paragraph('5. CONDIZIONI DI PAGAMENTO', styles['section_heading']))
    condizioni = [
        "Il pagamento avviene tramite bonifico bancario entro il 5 di ogni mese di competenza.",
        "In caso di mancato pagamento entro i termini, il Fornitore si riserva di sospendere "
        "l'erogazione del servizio fino a regolarizzazione.",
        "La presente offerta non costituisce un impegno contrattuale fino alla firma di entrambe le parti.",
    ]
    for i, testo in enumerate(condizioni, 1):
        story.append(Paragraph(f"{i}. {testo}", styles['body']))

    aggiungi_footer(story, styles, con_firma=True)


# ══════════════════════════════════════════════════════════════════════════════
# Layout 3 — ONBOARDING
# ══════════════════════════════════════════════════════════════════════════════
def _build_onboarding(story, dati, styles):

    # Benvenuto
    story.append(Paragraph('1. BENVENUTO', styles['section_heading']))
    story.append(Paragraph(
        f"Gentile <b>{dati['nome_cliente']}</b>, a nome di tutto il team BriefToDeal "
        f"siamo lieti di darti il benvenuto. Questo documento raccoglie tutte le informazioni "
        f"necessarie per iniziare al meglio la collaborazione con <b>{dati['azienda']}</b> "
        f"sul servizio di <b>{dati['tipo_servizio']}</b>.",
        styles['welcome'],
    ))
    story.append(data_table([
        ('Cliente',       dati['nome_cliente']),
        ('Azienda',       dati['azienda']),
        ('Servizio',      dati['tipo_servizio']),
        ('Data di Inizio', dati['data_inizio']),
    ], styles))

    # Credenziali e accessi
    story.append(Paragraph('2. CREDENZIALI E ACCESSI', styles['section_heading']))
    story.append(Paragraph(
        "Le credenziali di accesso alle piattaforme di lavoro saranno inviate via email "
        "cifrata entro 24 ore dal kick-off. Di seguito le piattaforme attive per questo progetto:",
        styles['body'],
    ))
    cred_head = [
        Paragraph('Piattaforma', styles['table_head']),
        Paragraph('URL / Riferimento', styles['table_head']),
        Paragraph('Username', styles['table_head']),
        Paragraph('Note', styles['table_head']),
    ]
    piattaforme = [
        ('Project Management', 'app.brieftodeal.com', 'da inviare', 'Accesso entro 24h'),
        ('Reportistica',       'report.brieftodeal.com', 'da inviare', 'Aggiornato settimanalmente'),
        ('Comunicazione',      'Slack / Email dedicata', 'da inviare', 'Risposta entro 4h lavorative'),
    ]
    cred_rows = [cred_head] + [
        [Paragraph(c, styles['table_cell']) for c in row]
        for row in piattaforme
    ]
    cred_t = Table(cred_rows, colWidths=[3.8 * cm, 4.5 * cm, 3 * cm, 5.2 * cm])
    cred_t.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0),  PURPLE),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
        ('GRID',          (0, 0), (-1, -1), 0.4, colors.HexColor('#E5E7EB')),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
    ]))
    story.append(cred_t)

    # Roadmap primo mese
    story.append(Paragraph('3. ROADMAP PRIMO MESE', styles['section_heading']))
    road_head = [
        Paragraph('Periodo', styles['table_head']),
        Paragraph('Attivita principali', styles['table_head']),
        Paragraph('Output atteso', styles['table_head']),
    ]
    road_rows_data = [
        ('Settimana 1',
         'Kick-off meeting, setup account, accesso piattaforme, raccolta materiali',
         'Brief operativo approvato'),
        ('Settimana 2',
         'Avvio operativo, primo ciclo di lavoro, allineamento obiettivi',
         'Primo ciclo completato'),
        ('Settimana 3',
         'Review intermedia, ottimizzazioni, feedback del cliente',
         'Report intermedio'),
        ('Settimana 4',
         'Chiusura primo mese, analisi risultati, pianificazione mese 2',
         'Report mensile + piano'),
    ]
    road_rows = [road_head] + [
        [Paragraph(c, styles['table_cell']) for c in row]
        for row in road_rows_data
    ]
    road_t = Table(road_rows, colWidths=[3.2 * cm, 8.5 * cm, 4.8 * cm])
    road_t.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0),  PURPLE),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
        ('GRID',          (0, 0), (-1, -1), 0.4, colors.HexColor('#E5E7EB')),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
    ]))
    story.append(road_t)

    # Referente dedicato
    story.append(Paragraph('4. REFERENTE DEDICATO', styles['section_heading']))
    story.append(data_table([
        ('Nome Referente',  'Da assegnare al kick-off'),
        ('Email diretta',   'referente@brieftodeal.com'),
        ('Telefono',        'Da comunicare al kick-off'),
        ('Orari',           'Lun-Ven 9:00-18:00 | Risposta entro 4 ore lavorative'),
        ('Canale rapido',   'Slack dedicato al progetto'),
    ], styles))

    aggiungi_footer(story, styles, con_firma=False)


# ══════════════════════════════════════════════════════════════════════════════
# Funzione pubblica
# ══════════════════════════════════════════════════════════════════════════════
def genera_pdf(dati: dict, tipo_documento: str = 'contratto',
               output_dir: str = '.') -> str:

    tipo_documento = tipo_documento.lower().strip()
    if tipo_documento not in TIPI_DOCUMENTO:
        raise ValueError(f"tipo_documento non valido: '{tipo_documento}'. "
                         f"Scegli tra: {list(TIPI_DOCUMENTO)}")

    required = ['nome_cliente', 'azienda', 'tipo_servizio',
                'importo_mensile', 'durata_mesi', 'data_inizio']
    for campo in required:
        if campo not in dati:
            raise ValueError(f"Campo obbligatorio mancante: {campo}")

    titolo_doc, ref_prefix = TIPI_DOCUMENTO[tipo_documento]
    nome_file   = f"{tipo_documento}_{dati['nome_cliente'].replace(' ', '_')}.pdf"
    output_path = os.path.join(output_dir, nome_file)

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2.5 * cm,
        title=f"{titolo_doc} - {dati['nome_cliente']}",
        author='BriefToDeal',
    )

    styles = build_styles()
    story  = []

    aggiungi_header(story, styles, titolo_doc, ref_prefix, dati['nome_cliente'])

    builders = {
        'contratto':  _build_contratto,
        'preventivo': _build_preventivo,
        'onboarding': _build_onboarding,
    }
    builders[tipo_documento](story, dati, styles)

    doc.build(story)
    return output_path


# ── Entry point CLI ───────────────────────────────────────────────────────────
if __name__ == '__main__':
    raw  = None
    tipo = 'contratto'

    args = sys.argv[1:]
    for a in args:
        if a in TIPI_DOCUMENTO:
            tipo = a
        elif a == '-':
            raw = sys.stdin.read()
        elif os.path.isfile(a):
            with open(a, 'r', encoding='utf-8-sig') as f:
                raw = f.read()
        else:
            raw = a

    if raw is None:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
        else:
            print("Uso: python generate_pdf.py file.json [contratto|preventivo|onboarding]")
            sys.exit(1)

    dati   = json.loads(raw.strip())
    output = genera_pdf(dati, tipo_documento=tipo,
                        output_dir=os.path.dirname(os.path.abspath(__file__)))
    print(f"PDF generato: {output}")
