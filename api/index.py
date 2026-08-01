"""
Vercel Serverless Entry Point
Wraps Flask app for Vercel's Python runtime
"""
import os
import sys

# Garante que o diretório raiz do projeto esteja no path para importar app.py
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app

app = create_app('production')
