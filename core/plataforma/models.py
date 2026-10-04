"""Operadores da plataforma (XR) — papel GLOBAL, fora de qualquer tenant.

Nunca é atribuível pelo painel de um tenant: só por CLI (make_operator.py)
ou por outro operador. Não herda TenantScopedModel de propósito: o operador
não pertence a tenant nenhum.
"""
from datetime import datetime

from extensions import db


class OperadorPlataforma(db.Model):
    __tablename__ = 'operadores_plataforma'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False)
    totp_segredo = db.Column(db.String(64), nullable=True)
    totp_ativo = db.Column(db.Boolean, nullable=False, default=False)
    totp_ultimo_contador = db.Column(db.BigInteger, nullable=True)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    criado_por = db.Column(db.Integer, nullable=True)
