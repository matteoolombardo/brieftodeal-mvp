"""
server.py — Flask backend BriefToDeal v2.

Novità v2:
  - SQLite/PostgreSQL via SQLAlchemy (models.py)
  - Ogni documento generato viene persistito (Document)
  - Ogni documento ottiene un link condivisibile (SharedLink)
  - GET /p/<token>   → pagina pubblica mobile con watermark
  - GET /api/doc/<id>→ metadati documento (JSON)
  - Header X-Doc-Id e X-Share-Token su ogni risposta /genera

Sviluppo:  cp .env.example .env && python server.py
Produzione: gunicorn server:app (vedi Procfile)
"""

import hashlib
import io
import json
import os
import re
import tempfile
from datetime import datetime

import anthropic
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template_string, request, send_file
from flask_cors import CORS

from generate_html import genera_html
from generate_pdf import genera_pdf
from models import Document, SharedLink, UsageQuota, WaitlistEntry, db

# ── Configurazione ─────────────────────────────────────────────────────────────
load_dotenv()

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
ALLOWED_ORIGIN    = os.environ.get('ALLOWED_ORIGIN', '*')
DATABASE_URL      = os.environ.get('DATABASE_URL', 'sqlite:///brieftodeal.db')
BASE_URL          = os.environ.get('BASE_URL', 'http://localhost:5000')

# Railway usa postgres://, SQLAlchemy richiede postgresql://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

# ── App factory ────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder='.', static_url_path='')
app.config['SQLALCHEMY_DATABASE_URI']        = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS']      = {'pool_pre_ping': True}

db.init_app(app)
CORS(app,
     origins=ALLOWED_ORIGIN,
     expose_headers=['X-Doc-Id', 'X-Share-Token', 'X-Share-Url',
                     'X-Cache', 'X-Html-Url', 'X-Remaining',
                     'X-Quota-Limit', 'Content-Disposition'])

# ── Piano Free ─────────────────────────────────────────────────────────────────
FREE_LIMIT = 3   # documenti gratuiti al mese per IP

with app.app_context():
    db.create_all()

# ── Prompt Claude ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "Sei un estrattore di dati. Dal testo ricevuto estrai in formato JSON: "
    "nome_cliente, azienda, tipo_servizio, importo_mensile, durata_mesi, data_inizio. "
    "Rispondi SOLO con il JSON, nessun testo extra."
)


# ── Helpers ────────────────────────────────────────────────────────────────────
def _hash_brief(testo: str) -> str:
    """SHA-256 del brief normalizzato — usato per il caching semantico (Step 2)."""
    normalizzato = ' '.join(testo.lower().strip().split())
    return hashlib.sha256(normalizzato.encode()).hexdigest()


def _chiama_claude(brief: str) -> str:
    """Chiama Claude e ritorna il testo grezzo della risposta."""
    client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': brief}],
    )
    return message.content[0].text.strip()


def _parse_json_claude(raw: str) -> dict:
    """Rimuove eventuali backtick markdown e fa il parse JSON."""
    clean = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw, flags=re.DOTALL).strip()
    return json.loads(clean)


def _get_ip_hash(req) -> str:
    """SHA-256 dell'IP del client — privacy-safe, non reversibile."""
    ip = req.headers.get('X-Forwarded-For', req.remote_addr or '')
    ip = ip.split(',')[0].strip()
    return hashlib.sha256(ip.encode()).hexdigest()


def _quota_check_and_increment(ip_hash: str) -> tuple:
    """
    Verifica la quota mensile e incrementa il contatore se consentito.
    Returns: (allowed: bool, remaining: int, count_after: int)
    """
    month = datetime.utcnow().strftime('%Y-%m')
    try:
        quota = db.session.get(UsageQuota, (ip_hash, month))
        if quota is None:
            quota = UsageQuota(ip_hash=ip_hash, month=month, count=0)
            db.session.add(quota)

        if quota.count >= FREE_LIMIT:
            db.session.rollback()
            return False, 0, quota.count

        quota.count += 1
        db.session.commit()
        remaining = FREE_LIMIT - quota.count
        return True, remaining, quota.count
    except Exception as e:
        app.logger.error(f'Quota check error: {e}')
        db.session.rollback()
        return True, FREE_LIMIT, 0   # fail-open: non bloccare se DB è giù


# ── Template pagina pubblica /p/<token> ────────────────────────────────────────
SHARE_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{{ titolo }} — {{ dati.nome_cliente }}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body { background: #F9FAFB; }
    .brand { color: #7C3AED; }
    .badge { background: #EDE9FE; color: #7C3AED; }
  </style>
</head>
<body class="min-h-screen font-sans">

  <!-- Header -->
  <header class="bg-white border-b border-gray-200 px-5 py-4 flex items-center justify-between">
    <span class="text-xl font-extrabold brand">BriefToDeal</span>
    <span class="badge text-xs font-semibold px-2 py-1 rounded-full">{{ tipo_label }}</span>
  </header>

  <!-- Card documento -->
  <main class="max-w-lg mx-auto px-4 py-8 flex flex-col gap-5">

    <div class="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
      <h1 class="text-2xl font-bold text-gray-900 mb-1">{{ dati.nome_cliente }}</h1>
      <p class="text-gray-500 text-sm mb-6">{{ dati.azienda }}</p>

      <div class="divide-y divide-gray-100">
        <div class="flex justify-between py-3">
          <span class="text-gray-500 text-sm">Servizio</span>
          <span class="text-gray-900 text-sm font-medium">{{ dati.tipo_servizio }}</span>
        </div>
        <div class="flex justify-between py-3">
          <span class="text-gray-500 text-sm">Importo mensile</span>
          <span class="text-gray-900 text-sm font-medium">EUR {{ importo_fmt }}</span>
        </div>
        <div class="flex justify-between py-3">
          <span class="text-gray-500 text-sm">Durata</span>
          <span class="text-gray-900 text-sm font-medium">{{ dati.durata_mesi }} mesi</span>
        </div>
        <div class="flex justify-between py-3">
          <span class="text-gray-500 text-sm">Inizio</span>
          <span class="text-gray-900 text-sm font-medium">{{ dati.data_inizio }}</span>
        </div>
        <div class="flex justify-between py-3">
          <span class="text-gray-500 text-sm font-semibold">Totale</span>
          <span class="font-bold brand text-base">EUR {{ totale_fmt }}</span>
        </div>
      </div>
    </div>

    <!-- CTA watermark -->
    {% if watermark %}
    <div class="bg-white rounded-2xl border border-purple-200 p-5 text-center">
      <p class="text-gray-600 text-sm mb-3">
        Documento creato con <strong class="brand">BriefToDeal</strong> —
        dal brief al contratto in 10 secondi.
      </p>
      <a href="{{ base_url }}"
         class="inline-block bg-purple-600 hover:bg-purple-700 text-white
                font-semibold text-sm px-6 py-2.5 rounded-xl transition-colors">
        Prova gratis &rarr;
      </a>
    </div>
    {% endif %}

    <p class="text-center text-gray-400 text-xs">
      Generato il {{ created_at }} &middot; Visualizzazioni: {{ view_count }}
    </p>

  </main>
</body>
</html>
"""


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_file('index.html')


@app.route('/health')
def health():
    try:
        doc_count = Document.query.count()
        db_ok = True
    except Exception:
        doc_count = -1
        db_ok = False
    return jsonify({
        'status':        'ok',
        'api_key_set':   bool(ANTHROPIC_API_KEY),
        'db_ok':         db_ok,
        'doc_count':     doc_count,
    })


@app.route('/genera', methods=['POST'])
def genera():
    # ── Guardie ───────────────────────────────────────────────────────────────
    if not ANTHROPIC_API_KEY:
        return jsonify({'error': 'ANTHROPIC_API_KEY non configurata sul server.'}), 503

    body           = request.get_json(silent=True) or {}
    brief          = (body.get('brief') or '').strip()
    tipo_documento = (body.get('tipo_documento') or 'contratto').strip().lower()

    if not brief:
        return jsonify({'error': 'Brief vuoto.'}), 400
    if tipo_documento not in ('contratto', 'preventivo', 'onboarding'):
        return jsonify({'error': f'tipo_documento non valido: {tipo_documento}'}), 400

    # ── 1. Quota check (Free tier) ────────────────────────────────────────────
    ip_hash = _get_ip_hash(request)
    allowed, remaining, _ = _quota_check_and_increment(ip_hash)
    if not allowed:
        return jsonify({
            'error':   f'Hai raggiunto il limite di {FREE_LIMIT} documenti gratuiti questo mese.',
            'upgrade': True,
            'limit':   FREE_LIMIT,
        }), 429

    # ── 2. Hash brief ─────────────────────────────────────────────────────────
    brief_hash = _hash_brief(brief)

    # ── 2. Cache hit? Cerca nel DB per hash + tipo ────────────────────────────
    cached_doc = Document.query.filter_by(
        brief_hash=brief_hash,
        tipo_documento=tipo_documento,
    ).first()

    if cached_doc and cached_doc.pdf_blob:
        # Cache HIT — restituisci il PDF salvato senza chiamare Claude
        app.logger.info(f'Cache HIT doc={cached_doc.id[:8]}')
        cached_doc.download_count += 1

        # Recupera o crea il link condivisibile
        link = cached_doc.shared_links.first()
        if not link:
            link = SharedLink(document_id=cached_doc.id, watermark=True)
            db.session.add(link)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            link = None

        j        = cached_doc.extracted_json or {}
        filename = f"{tipo_documento}_{j.get('nome_cliente','doc').replace(' ', '_')}.pdf"
        response = send_file(
            io.BytesIO(cached_doc.pdf_blob),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename,
        )
        response.headers['X-Cache']        = 'HIT'
        response.headers['X-Remaining']    = str(remaining)
        response.headers['X-Quota-Limit']  = str(FREE_LIMIT)
        response.headers['X-Doc-Id']       = cached_doc.id
        if link:
            response.headers['X-Share-Token'] = link.token
            response.headers['X-Share-Url']   = link.share_url(BASE_URL)
        if cached_doc.html_summary:
            response.headers['X-Html-Url'] = f"{BASE_URL}/doc/{cached_doc.id}/view"
        return response

    # Cache MISS — procedi con Claude
    app.logger.info(f'Cache MISS hash={brief_hash[:12]}')

    # ── 3. Chiamata Claude ────────────────────────────────────────────────────
    try:
        raw_text = _chiama_claude(brief)
    except anthropic.AuthenticationError:
        return jsonify({'error': 'API key Anthropic non valida.'}), 401
    except anthropic.APIError as e:
        return jsonify({'error': f'Errore API Anthropic: {e}'}), 502

    # ── 4. Parse JSON estratto ────────────────────────────────────────────────
    try:
        dati = _parse_json_claude(raw_text)
    except json.JSONDecodeError as e:
        return jsonify({'error': f'JSON non valido da Claude: {e}', 'raw': raw_text}), 422

    # ── 5. Genera PDF in memoria ──────────────────────────────────────────────
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = genera_pdf(dati, tipo_documento=tipo_documento, output_dir=tmpdir)
            with open(pdf_path, 'rb') as f:
                pdf_bytes_data = f.read()
    except ValueError as e:
        return jsonify({'error': str(e)}), 422
    except Exception as e:
        return jsonify({'error': f'Errore generazione PDF: {e}'}), 500

    # ── 6. Genera HTML mobile ─────────────────────────────────────────────────
    try:
        html_summary = genera_html(dati, tipo_documento=tipo_documento)
    except Exception as e:
        app.logger.warning(f'HTML generation failed (non-critical): {e}')
        html_summary = None

    # ── 7. Salva Document nel DB ──────────────────────────────────────────────
    try:
        import uuid as _uuid
        doc_id = str(_uuid.uuid4())
        doc = Document(
            id             = doc_id,
            brief_hash     = brief_hash,
            brief_text     = brief,
            extracted_json = dati,
            tipo_documento = tipo_documento,
            pdf_blob       = pdf_bytes_data,
            html_summary   = html_summary,
        )
        db.session.add(doc)

        # Crea link condivisibile (document_id noto prima del flush)
        link = SharedLink(document_id=doc_id, watermark=True)
        db.session.add(link)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'DB save error: {e}')
        doc  = None
        link = None

    # ── 8. Risposta PDF + headers ─────────────────────────────────────────────
    filename = f"{tipo_documento}_{dati['nome_cliente'].replace(' ', '_')}.pdf"
    response = send_file(
        io.BytesIO(pdf_bytes_data),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename,
    )
    response.headers['X-Cache']       = 'MISS'
    response.headers['X-Remaining']   = str(remaining)
    response.headers['X-Quota-Limit'] = str(FREE_LIMIT)
    if doc and link:
        response.headers['X-Doc-Id']      = doc.id
        response.headers['X-Share-Token'] = link.token
        response.headers['X-Share-Url']   = link.share_url(BASE_URL)
        response.headers['X-Html-Url']    = f"{BASE_URL}/doc/{doc.id}/view"
    return response


@app.route('/p/<token>')
def pagina_pubblica(token: str):
    """Pagina pubblica mobile-first con watermark BriefToDeal."""
    link = SharedLink.query.get_or_404(token)
    doc  = link.document

    # Incrementa view count
    link.view_count += 1
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    j = doc.extracted_json or {}
    TIPO_LABEL = {
        'contratto':  'Contratto',
        'preventivo': 'Preventivo',
        'onboarding': 'Onboarding',
    }
    try:
        importo = float(j.get('importo_mensile', 0))
        durata  = int(j.get('durata_mesi', 0))
        importo_fmt = f"{importo:,.2f}"
        totale_fmt  = f"{importo * durata:,.2f}"
    except (ValueError, TypeError):
        importo_fmt = totale_fmt = 'N/D'

    from types import SimpleNamespace
    dati_ns = SimpleNamespace(**j)

    return render_template_string(
        SHARE_PAGE_TEMPLATE,
        dati       = dati_ns,
        titolo     = TIPO_LABEL.get(doc.tipo_documento, 'Documento'),
        tipo_label = TIPO_LABEL.get(doc.tipo_documento, 'Documento'),
        importo_fmt= importo_fmt,
        totale_fmt = totale_fmt,
        watermark  = link.watermark,
        base_url   = BASE_URL,
        created_at = doc.created_at.strftime('%d/%m/%Y'),
        view_count = link.view_count,
    )


@app.route('/api/doc/<doc_id>')
def api_documento(doc_id: str):
    """Metadati di un documento (senza il blob PDF)."""
    doc = Document.query.get_or_404(doc_id)
    preview = doc.to_preview()
    preview['share_links'] = [
        {'token': l.token, 'url': l.share_url(BASE_URL), 'views': l.view_count}
        for l in doc.shared_links
    ]
    return jsonify(preview)


@app.route('/doc/<doc_id>/view')
def visualizza_html(doc_id: str):
    """Serve la versione HTML mobile del documento."""
    doc = Document.query.get_or_404(doc_id)
    if not doc.html_summary:
        # Genera al volo se non ancora salvato (retrocompatibilità)
        try:
            html = genera_html(doc.extracted_json or {}, doc.tipo_documento)
        except Exception:
            return jsonify({'error': 'HTML non disponibile'}), 404
        return html, 200, {'Content-Type': 'text/html; charset=utf-8'}
    return doc.html_summary, 200, {'Content-Type': 'text/html; charset=utf-8'}


@app.route('/api/email', methods=['POST'])
def salva_email():
    """Salva l'email dell'utente sul documento (lead capture)."""
    body   = request.get_json(silent=True) or {}
    doc_id = (body.get('doc_id') or '').strip()
    email  = (body.get('email')  or '').strip()

    if not doc_id or not email:
        return jsonify({'error': 'doc_id e email sono richiesti'}), 400

    # Validazione email minima
    if '@' not in email or '.' not in email.split('@')[-1]:
        return jsonify({'error': 'Email non valida'}), 400

    doc = Document.query.get_or_404(doc_id)
    doc.user_email = email
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Email save error: {e}')
        return jsonify({'error': 'Errore salvataggio'}), 500

    return jsonify({'ok': True})


@app.route('/api/waitlist', methods=['POST'])
def waitlist():
    """Aggiunge un'email alla lista d'attesa piano Pro."""
    body  = request.get_json(silent=True) or {}
    email = (body.get('email') or '').strip().lower()

    if not email or '@' not in email or '.' not in email.split('@')[-1]:
        return jsonify({'error': 'Email non valida'}), 400

    # Già presente → ok idempotente
    existing = WaitlistEntry.query.filter_by(email=email).first()
    if existing:
        return jsonify({'ok': True, 'already': True})

    entry = WaitlistEntry(email=email)
    db.session.add(entry)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Waitlist save error: {e}')
        return jsonify({'error': 'Errore salvataggio'}), 500

    return jsonify({'ok': True}), 201


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    if not ANTHROPIC_API_KEY:
        print('[WARN] ANTHROPIC_API_KEY non impostata — crea un file .env')
    print(f'BriefToDeal server: http://localhost:{port}')
    app.run(debug=False, port=port)
