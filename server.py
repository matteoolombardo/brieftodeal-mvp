"""
server.py — Flask backend BriefToDeal.

Sviluppo locale:
  Crea un file .env con ANTHROPIC_API_KEY=sk-ant-...
  python server.py  →  http://localhost:5000

Produzione (Railway):
  Imposta ANTHROPIC_API_KEY e ALLOWED_ORIGIN nel dashboard Railway.
  Il Procfile avvia: gunicorn server:app
"""

import io
import json
import os
import re
import tempfile

import anthropic
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

from generate_pdf import genera_pdf

# Carica .env in sviluppo (ignorato se le variabili sono già nell'ambiente)
load_dotenv()

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
ALLOWED_ORIGIN    = os.environ.get('ALLOWED_ORIGIN', '*')

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app, origins=ALLOWED_ORIGIN)

SYSTEM_PROMPT = (
    "Sei un estrattore di dati. Dal testo ricevuto estrai in formato JSON: "
    "nome_cliente, azienda, tipo_servizio, importo_mensile, durata_mesi, data_inizio. "
    "Rispondi SOLO con il JSON, nessun testo extra."
)


@app.route('/')
def index():
    return send_file('index.html')


@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'api_key_set': bool(ANTHROPIC_API_KEY)})


@app.route('/genera', methods=['POST'])
def genera():
    # ── Controllo API key configurata ────────────────────────────────────────
    if not ANTHROPIC_API_KEY:
        return jsonify({
            'error': 'ANTHROPIC_API_KEY non configurata sul server. '
                     'Aggiungi la variabile d\'ambiente e riavvia.'
        }), 503

    body           = request.get_json(silent=True) or {}
    brief          = (body.get('brief') or '').strip()
    tipo_documento = (body.get('tipo_documento') or 'contratto').strip().lower()

    if not brief:
        return jsonify({'error': 'Brief vuoto.'}), 400
    if tipo_documento not in ('contratto', 'preventivo', 'onboarding'):
        return jsonify({'error': f'tipo_documento non valido: {tipo_documento}'}), 400

    # ── 1. Chiamata Claude ────────────────────────────────────────────────────
    try:
        client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': brief}],
        )
        raw_text = message.content[0].text.strip()
    except anthropic.AuthenticationError:
        return jsonify({'error': 'API key Anthropic non valida. Controlla ANTHROPIC_API_KEY.'}), 401
    except anthropic.APIError as e:
        return jsonify({'error': f'Errore API Anthropic: {e}'}), 502

    # ── 2. Parse JSON estratto ─────────────────────────────────────────────────
    try:
        clean = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw_text, flags=re.DOTALL).strip()
        dati  = json.loads(clean)
    except json.JSONDecodeError as e:
        return jsonify({'error': f'JSON non valido estratto da Claude: {e}', 'raw': raw_text}), 422

    # ── 3. Genera PDF in memoria ──────────────────────────────────────────────
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = genera_pdf(dati, tipo_documento=tipo_documento, output_dir=tmpdir)
            with open(pdf_path, 'rb') as f:
                pdf_bytes = io.BytesIO(f.read())
    except ValueError as e:
        return jsonify({'error': str(e)}), 422
    except Exception as e:
        return jsonify({'error': f'Errore generazione PDF: {e}'}), 500

    filename = f"{tipo_documento}_{dati['nome_cliente'].replace(' ', '_')}.pdf"
    pdf_bytes.seek(0)
    return send_file(
        pdf_bytes,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename,
    )


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    if not ANTHROPIC_API_KEY:
        print('[WARN] ANTHROPIC_API_KEY non impostata — crea un file .env')
    print(f'BriefToDeal server: http://localhost:{port}')
    app.run(debug=False, port=port)
