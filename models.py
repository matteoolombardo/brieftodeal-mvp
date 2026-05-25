"""
models.py — BriefToDeal database models.

Due tabelle:
  Document    → ogni documento generato (brief, JSON estratto, PDF, HTML)
  SharedLink  → link pubblico per condivisione con watermark
"""

import secrets
import uuid
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Document(db.Model):
    __tablename__ = 'documents'

    # ── Identità ──────────────────────────────────────────────────────────────
    id             = db.Column(db.String(36), primary_key=True,
                               default=lambda: str(uuid.uuid4()))

    # ── Dati sorgente ─────────────────────────────────────────────────────────
    brief_hash     = db.Column(db.String(64), index=True, nullable=True)
    brief_text     = db.Column(db.Text, nullable=False)
    extracted_json = db.Column(db.JSON, nullable=False)
    tipo_documento = db.Column(db.String(20), nullable=False)

    # ── Output generati ───────────────────────────────────────────────────────
    pdf_blob       = db.Column(db.LargeBinary, nullable=True)   # PDF bytes
    html_summary   = db.Column(db.Text, nullable=True)          # mobile HTML

    # ── Utente ───────────────────────────────────────────────────────────────
    user_email     = db.Column(db.String(255), nullable=True, index=True)

    # ── Metriche ─────────────────────────────────────────────────────────────
    created_at     = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    download_count = db.Column(db.Integer, default=0, nullable=False)

    # ── Relazione ─────────────────────────────────────────────────────────────
    shared_links   = db.relationship('SharedLink', backref='document',
                                      lazy='dynamic', cascade='all, delete-orphan')

    def to_preview(self) -> dict:
        """Dati minimi per la preview card nel frontend (mai il PDF blob)."""
        j = self.extracted_json or {}
        try:
            importo = float(j.get('importo_mensile', 0))
            durata  = int(j.get('durata_mesi', 0))
            totale  = f"EUR {importo * durata:,.2f}"
        except (ValueError, TypeError):
            totale = 'N/D'

        return {
            'doc_id':          self.id,
            'tipo_documento':  self.tipo_documento,
            'nome_cliente':    j.get('nome_cliente', ''),
            'azienda':         j.get('azienda', ''),
            'tipo_servizio':   j.get('tipo_servizio', ''),
            'importo_mensile': j.get('importo_mensile', 0),
            'durata_mesi':     j.get('durata_mesi', 0),
            'data_inizio':     j.get('data_inizio', ''),
            'totale':          totale,
            'created_at':      self.created_at.strftime('%d/%m/%Y %H:%M'),
            'download_count':  self.download_count,
        }

    def __repr__(self):
        return f'<Document {self.id[:8]} {self.tipo_documento} {self.user_email}>'


class SharedLink(db.Model):
    __tablename__ = 'shared_links'

    # ── Identità ──────────────────────────────────────────────────────────────
    token       = db.Column(db.String(16), primary_key=True,
                            default=lambda: secrets.token_urlsafe(8))

    # ── Relazione ─────────────────────────────────────────────────────────────
    document_id = db.Column(db.String(36),
                            db.ForeignKey('documents.id', ondelete='CASCADE'),
                            nullable=False, index=True)

    # ── Configurazione ────────────────────────────────────────────────────────
    watermark   = db.Column(db.Boolean, default=True, nullable=False)

    # ── Metriche ─────────────────────────────────────────────────────────────
    view_count  = db.Column(db.Integer, default=0, nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def share_url(self, base_url: str = '') -> str:
        return f"{base_url}/p/{self.token}"

    def __repr__(self):
        return f'<SharedLink {self.token} doc={self.document_id[:8]}>'
