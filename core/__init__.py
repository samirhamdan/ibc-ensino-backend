# Pacote core (doc 02 §3). Vive na raiz como `core/` (e não `app/core/`)
# porque o módulo legado `app.py` ainda existe — um pacote `app/` sombrearia
# o import `app:create_app` usado pelo gunicorn. Move para `app/core/` na
# reestruturação da Release 0.9/1.0.
