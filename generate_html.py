"""
generate_html.py — BriefToDeal mobile HTML generator.

Genera un documento HTML self-contained, mobile-responsive e stampabile.
Nessuna dipendenza esterna — tutto inline.

Uso:
    from generate_html import genera_html
    html_str = genera_html(dati, tipo_documento='contratto')
"""

from datetime import datetime

# ── Costanti brand ─────────────────────────────────────────────────────────────
PURPLE      = '#7C3AED'
PURPLE_LIGHT = '#EDE9FE'
PURPLE_TEXT  = '#5B21B6'
DARK        = '#111827'
GRAY        = '#6B7280'
LIGHT_BG    = '#F9FAFB'
BORDER      = '#E5E7EB'
GREEN       = '#059669'
GREEN_BG    = '#ECFDF5'


# ── Entry point ────────────────────────────────────────────────────────────────
def genera_html(dati: dict, tipo_documento: str = 'contratto') -> str:
    """
    Genera HTML mobile-responsive per il documento.

    Args:
        dati: dict con i campi estratti (nome_cliente, azienda, tipo_servizio,
              importo_mensile, durata_mesi, data_inizio)
        tipo_documento: 'contratto' | 'preventivo' | 'onboarding'

    Returns:
        str: documento HTML completo
    """
    TIPO_INFO = {
        'contratto':  ('Contratto di Fornitura Servizi', 'CTR'),
        'preventivo': ('Preventivo Commerciale',          'PRV'),
        'onboarding': ('Documento di Onboarding',         'ONB'),
    }
    titolo_doc, codice = TIPO_INFO.get(tipo_documento, ('Documento', 'DOC'))

    nome     = dati.get('nome_cliente', 'Cliente')
    azienda  = dati.get('azienda', '')
    servizio = dati.get('tipo_servizio', '')
    inizio   = dati.get('data_inizio', '')
    oggi     = datetime.now().strftime('%d/%m/%Y')
    ref      = f"{codice}-{datetime.now().strftime('%Y%m%d')}"

    try:
        importo = float(dati.get('importo_mensile', 0))
        durata  = int(dati.get('durata_mesi', 0))
        totale  = importo * durata
        importo_fmt = f"EUR {importo:,.2f}"
        totale_fmt  = f"EUR {totale:,.2f}"
    except (ValueError, TypeError):
        importo = durata = totale = 0
        importo_fmt = totale_fmt = 'N/D'

    # Sezioni specifiche per tipo
    if tipo_documento == 'preventivo':
        body = _body_preventivo(nome, azienda, servizio, inizio, importo,
                                durata, importo_fmt, totale_fmt)
    elif tipo_documento == 'onboarding':
        body = _body_onboarding(nome, azienda, servizio, inizio)
    else:
        body = _body_contratto(nome, azienda, servizio, inizio, importo,
                               durata, importo_fmt, totale_fmt)

    return _wrap(titolo_doc, codice, nome, azienda, oggi, ref, body)


# ── Wrapper HTML base ──────────────────────────────────────────────────────────
def _wrap(titolo_doc, codice, nome, azienda, oggi, ref, body_html):
    return f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{titolo_doc} — {nome}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
                   Helvetica, Arial, sans-serif;
      background: {LIGHT_BG};
      color: {DARK};
      min-height: 100vh;
      padding: 0 0 48px;
    }}

    /* ── Header ── */
    .doc-header {{
      background: #fff;
      border-bottom: 3px solid {PURPLE};
      padding: 20px 24px 16px;
    }}
    .brand {{
      font-size: 1.25rem;
      font-weight: 800;
      color: {PURPLE};
      letter-spacing: -.02em;
    }}
    .doc-title {{
      font-size: .75rem;
      font-weight: 700;
      color: {GRAY};
      letter-spacing: .08em;
      text-transform: uppercase;
      margin-top: 6px;
    }}
    .doc-meta {{
      font-size: .7rem;
      color: {GRAY};
      margin-top: 2px;
    }}

    /* ── Layout ── */
    .container {{
      max-width: 680px;
      margin: 0 auto;
      padding: 24px 16px 0;
    }}

    /* ── Cards ── */
    .card {{
      background: #fff;
      border: 1px solid {BORDER};
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 16px;
    }}
    .card-title {{
      font-size: .65rem;
      font-weight: 700;
      color: {PURPLE};
      letter-spacing: .1em;
      text-transform: uppercase;
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .card-title::after {{
      content: '';
      flex: 1;
      height: 1px;
      background: {PURPLE_LIGHT};
    }}

    /* ── Righe dati ── */
    .row {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      padding: 8px 0;
      border-bottom: 1px solid {LIGHT_BG};
      font-size: .875rem;
      gap: 12px;
    }}
    .row:last-child {{ border-bottom: none; }}
    .row-label {{ color: {GRAY}; flex-shrink: 0; }}
    .row-value {{ font-weight: 500; text-align: right; }}

    /* ── Totale highlight ── */
    .totale-row {{
      background: {PURPLE_LIGHT};
      border-radius: 8px;
      padding: 12px 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: 12px;
    }}
    .totale-label {{
      font-size: .875rem;
      font-weight: 700;
      color: {PURPLE_TEXT};
    }}
    .totale-value {{
      font-size: 1.125rem;
      font-weight: 800;
      color: {PURPLE};
    }}

    /* ── Badge ── */
    .badge {{
      display: inline-block;
      font-size: .65rem;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 99px;
      background: {PURPLE_LIGHT};
      color: {PURPLE_TEXT};
      letter-spacing: .04em;
    }}

    /* ── Tabella roadmap ── */
    .table-wrap {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: .8rem;
      margin-top: 8px;
    }}
    th {{
      background: {PURPLE};
      color: #fff;
      font-weight: 700;
      padding: 8px 10px;
      text-align: left;
      font-size: .7rem;
      letter-spacing: .04em;
      text-transform: uppercase;
    }}
    td {{
      padding: 8px 10px;
      border-bottom: 1px solid {BORDER};
      vertical-align: top;
    }}
    tr:last-child td {{ border-bottom: none; }}
    tr:nth-child(even) td {{ background: {LIGHT_BG}; }}

    /* ── Firma ── */
    .firma-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 24px;
      margin-top: 8px;
    }}
    .firma-box {{
      border-top: 2px solid {BORDER};
      padding-top: 8px;
    }}
    .firma-label {{
      font-size: .7rem;
      color: {GRAY};
      text-transform: uppercase;
      letter-spacing: .06em;
    }}
    .firma-line {{
      height: 40px;
      border-bottom: 1px dashed {BORDER};
      margin-top: 4px;
    }}

    /* ── Testo corpo ── */
    .body-text {{
      font-size: .875rem;
      color: #374151;
      line-height: 1.6;
    }}
    .body-text + .body-text {{ margin-top: 8px; }}

    ul.lista {{
      padding-left: 16px;
      font-size: .875rem;
      color: #374151;
      line-height: 1.8;
    }}

    /* ── Footer watermark ── */
    .footer {{
      max-width: 680px;
      margin: 28px auto 0;
      padding: 0 16px;
      text-align: center;
      font-size: .7rem;
      color: {GRAY};
    }}
    .footer strong {{ color: {PURPLE}; font-weight: 700; }}

    /* ── Print ── */
    @media print {{
      body {{ background: #fff; padding: 0; }}
      .doc-header {{ border-bottom: 2px solid {PURPLE}; }}
      .card {{ break-inside: avoid; border: 1px solid #ddd; }}
      .footer {{ margin-top: 16px; }}
    }}

    @media (max-width: 400px) {{
      .firma-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>

  <header class="doc-header">
    <div class="brand">BriefToDeal</div>
    <div class="doc-title">{titolo_doc}</div>
    <div class="doc-meta">Rif. {ref} &middot; {oggi}</div>
  </header>

  <div class="container">
    {body_html}
  </div>

  <footer class="footer">
    Documento generato con <strong>BriefToDeal</strong> &mdash;
    dal brief al contratto in 10 secondi.
  </footer>

</body>
</html>"""


# ── Corpo CONTRATTO ────────────────────────────────────────────────────────────
def _body_contratto(nome, azienda, servizio, inizio,
                    importo, durata, importo_fmt, totale_fmt):
    return f"""
    <!-- Dati Cliente -->
    <div class="card">
      <div class="card-title">Dati Cliente</div>
      <div class="row">
        <span class="row-label">Nome</span>
        <span class="row-value">{nome}</span>
      </div>
      <div class="row">
        <span class="row-label">Azienda</span>
        <span class="row-value">{azienda or '—'}</span>
      </div>
    </div>

    <!-- Oggetto -->
    <div class="card">
      <div class="card-title">Oggetto del Contratto</div>
      <p class="body-text">
        Il presente contratto disciplina la fornitura del servizio di
        <strong>{servizio}</strong> da parte di BriefToDeal al Cliente
        {nome} ({azienda}).
      </p>
    </div>

    <!-- Condizioni Economiche -->
    <div class="card">
      <div class="card-title">Condizioni Economiche</div>
      <div class="row">
        <span class="row-label">Servizio</span>
        <span class="row-value">{servizio}</span>
      </div>
      <div class="row">
        <span class="row-label">Importo mensile</span>
        <span class="row-value">{importo_fmt}</span>
      </div>
      <div class="row">
        <span class="row-label">Durata</span>
        <span class="row-value">{durata} mesi</span>
      </div>
      <div class="row">
        <span class="row-label">Data inizio</span>
        <span class="row-value">{inizio or '—'}</span>
      </div>
      <div class="totale-row">
        <span class="totale-label">Valore totale contratto</span>
        <span class="totale-value">{totale_fmt}</span>
      </div>
    </div>

    <!-- Termini -->
    <div class="card">
      <div class="card-title">Termini e Condizioni</div>
      <ul class="lista">
        <li>Il contratto si intende perfezionato con la firma di entrambe le parti.</li>
        <li>Il pagamento mensile è dovuto entro il 5 di ogni mese.</li>
        <li>Ciascuna parte può recedere con preavviso scritto di 30 giorni.</li>
        <li>Foro competente: Tribunale della sede del Fornitore.</li>
        <li>Per quanto non previsto si applicano le norme del Codice Civile italiano.</li>
      </ul>
    </div>

    <!-- Firme -->
    <div class="card">
      <div class="card-title">Firme</div>
      <div class="firma-grid">
        <div class="firma-box">
          <div class="firma-label">Fornitore</div>
          <div class="firma-line"></div>
          <div style="font-size:.75rem;color:{GRAY};margin-top:4px;">BriefToDeal</div>
        </div>
        <div class="firma-box">
          <div class="firma-label">Cliente</div>
          <div class="firma-line"></div>
          <div style="font-size:.75rem;color:{GRAY};margin-top:4px;">{nome}</div>
        </div>
      </div>
      <p style="font-size:.7rem;color:{GRAY};margin-top:16px;text-align:center;">
        Luogo e data: _________________________
      </p>
    </div>
"""


# ── Corpo PREVENTIVO ───────────────────────────────────────────────────────────
def _body_preventivo(nome, azienda, servizio, inizio,
                     importo, durata, importo_fmt, totale_fmt):
    rows = ''
    if importo and durata:
        for i in range(1, min(durata + 1, 4)):
            rows += f"""
          <tr>
            <td>{i}</td>
            <td>{servizio}</td>
            <td style="text-align:right">{importo_fmt}</td>
            <td style="text-align:right">{importo_fmt}</td>
          </tr>"""
        if durata > 3:
            remaining = durata - 3
            rows += f"""
          <tr>
            <td>4–{durata}</td>
            <td>{servizio} (mesi rimanenti × {remaining})</td>
            <td style="text-align:right">{importo_fmt}</td>
            <td style="text-align:right">EUR {importo * remaining:,.2f}</td>
          </tr>"""

    return f"""
    <!-- Dati Cliente -->
    <div class="card">
      <div class="card-title">Dati Cliente</div>
      <div class="row">
        <span class="row-label">Nome</span>
        <span class="row-value">{nome}</span>
      </div>
      <div class="row">
        <span class="row-label">Azienda</span>
        <span class="row-value">{azienda or '—'}</span>
      </div>
    </div>

    <!-- Descrizione Servizi -->
    <div class="card">
      <div class="card-title">Descrizione Servizi</div>
      <p class="body-text">
        Il presente preventivo include la fornitura del servizio
        <strong>{servizio}</strong> per la durata di {durata} mesi,
        con decorrenza {inizio or 'da definire'}.
      </p>
    </div>

    <!-- Dettaglio Costi -->
    <div class="card">
      <div class="card-title">Dettaglio Costi</div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Descrizione</th>
              <th style="text-align:right">Importo/mese</th>
              <th style="text-align:right">Subtotale</th>
            </tr>
          </thead>
          <tbody>
            {rows}
          </tbody>
        </table>
      </div>
      <div class="totale-row">
        <span class="totale-label">Totale preventivo</span>
        <span class="totale-value">{totale_fmt}</span>
      </div>
    </div>

    <!-- Validità e pagamento -->
    <div class="card">
      <div class="card-title">Condizioni</div>
      <div class="row">
        <span class="row-label">Validità offerta</span>
        <span class="row-value"><span class="badge">30 giorni</span></span>
      </div>
      <div class="row">
        <span class="row-label">Modalità pagamento</span>
        <span class="row-value">Bonifico bancario entro 30 gg fattura</span>
      </div>
      <div class="row">
        <span class="row-label">Data inizio prevista</span>
        <span class="row-value">{inizio or '—'}</span>
      </div>
    </div>

    <!-- Firma -->
    <div class="card">
      <div class="card-title">Accettazione</div>
      <p class="body-text" style="margin-bottom:16px;">
        Firmando il presente preventivo, il Cliente accetta le condizioni
        economiche e contrattuali sopra indicate.
      </p>
      <div class="firma-grid">
        <div class="firma-box">
          <div class="firma-label">Fornitore</div>
          <div class="firma-line"></div>
          <div style="font-size:.75rem;color:{GRAY};margin-top:4px;">BriefToDeal</div>
        </div>
        <div class="firma-box">
          <div class="firma-label">Cliente</div>
          <div class="firma-line"></div>
          <div style="font-size:.75rem;color:{GRAY};margin-top:4px;">{nome}</div>
        </div>
      </div>
    </div>
"""


# ── Corpo ONBOARDING ───────────────────────────────────────────────────────────
def _body_onboarding(nome, azienda, servizio, inizio):
    return f"""
    <!-- Benvenuto -->
    <div class="card">
      <div class="card-title">Benvenuto</div>
      <p class="body-text">
        Caro/a <strong>{nome}</strong>, benvenuto/a in BriefToDeal.
      </p>
      <p class="body-text">
        Siamo felici di iniziare questa collaborazione con {azienda or 'la tua azienda'}
        per il servizio <strong>{servizio}</strong>.
        Questo documento ti guiderà nei primi passi del nostro percorso insieme.
      </p>
      {f'<p class="body-text">Data di inizio: <strong>{inizio}</strong></p>' if inizio else ''}
    </div>

    <!-- Credenziali -->
    <div class="card">
      <div class="card-title">Credenziali e Accessi</div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>Strumento</th><th>Accesso</th><th>Note</th></tr>
          </thead>
          <tbody>
            <tr><td>Piattaforma principale</td><td>Email fornita</td><td>Invio entro 24h</td></tr>
            <tr><td>Area clienti</td><td>Autogenerata</td><td>Reset al primo accesso</td></tr>
            <tr><td>Comunicazioni</td><td>Email dedicata</td><td>Risposta entro 1 giorno lavorativo</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Roadmap -->
    <div class="card">
      <div class="card-title">Roadmap Primo Mese</div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>Settimana</th><th>Attività</th><th>Output</th></tr>
          </thead>
          <tbody>
            <tr>
              <td><span class="badge">Sett. 1</span></td>
              <td>Kickoff e raccolta materiali</td>
              <td>Brief condiviso</td>
            </tr>
            <tr>
              <td><span class="badge">Sett. 2</span></td>
              <td>Setup e configurazione</td>
              <td>Accessi attivi</td>
            </tr>
            <tr>
              <td><span class="badge">Sett. 3</span></td>
              <td>Prima erogazione del servizio</td>
              <td>Report preliminare</td>
            </tr>
            <tr>
              <td><span class="badge">Sett. 4</span></td>
              <td>Review e ottimizzazione</td>
              <td>Piano mese 2</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Referente -->
    <div class="card">
      <div class="card-title">Referente Dedicato</div>
      <p class="body-text">
        Per qualsiasi necessità puoi contattare il tuo referente BriefToDeal.
        Ti risponderemo entro 1 giorno lavorativo.
      </p>
      <div class="row" style="margin-top:12px;">
        <span class="row-label">Email</span>
        <span class="row-value">clienti@brieftodeal.com</span>
      </div>
      <div class="row">
        <span class="row-label">Disponibilità</span>
        <span class="row-value">Lun–Ven 09:00–18:00</span>
      </div>
    </div>
"""


# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import json
    import sys

    if len(sys.argv) < 2:
        print('Uso: python generate_html.py dati.json [contratto|preventivo|onboarding]')
        sys.exit(1)

    with open(sys.argv[1], encoding='utf-8-sig') as f:
        dati_test = json.load(f)

    tipo = sys.argv[2] if len(sys.argv) > 2 else 'contratto'
    html = genera_html(dati_test, tipo)

    out = sys.argv[1].replace('.json', f'_{tipo}.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'HTML generato: {out}')
