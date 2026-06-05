# IBC Ensino Backend — Setup Replit

## 🚀 Passo 1: Criar novo Replit

1. Acesse https://replit.com
2. Clique em **"+ Create"**
3. Template: **Python**
4. Nome: `ibc-ensino-backend` (ou similar)
5. Clique em **"Create Replit"**

## 📥 Passo 2: Fazer Upload dos Arquivos

Clone ou upload os arquivos deste projeto para o Replit:

```bash
# Se quiser clonar do GitHub (depois que subir lá):
git clone https://github.com/samirhamdan75/ibc-ensino-backend.git

# Ou faça upload manual dos arquivos no Replit
```

Estrutura esperada:
```
ibc-ensino-backend/
├── app.py
├── models.py
├── config.py
├── requirements.txt
├── index.html
├── index_atual.html
├── BRIEFING.md
├── README.md
├── Logo-IBC-Horizontal.png     ← USAR ESTA
└── (ESCOLA_DA_IBC.png removida)
```

## ⚙️ Passo 3: Instalar Dependências

No terminal do Replit, execute:

```bash
pip install -r requirements.txt
```

## 🗄️ Passo 4: Criar Banco de Dados

```bash
python
>>> from app import db, create_app
>>> app = create_app()
>>> with app.app_context():
...     db.create_all()
...     print("✅ Banco criado!")
>>> exit()
```

## ▶️ Passo 5: Rodar a Aplicação

```bash
python app.py
```

Você verá algo como:
```
 * Running on http://0.0.0.0:5000
 * Press CTRL+C to quit
```

Clique no link ou acesse: `https://seu-usuario-ibc-ensino-backend.replit.dev`

---

## 🧪 Testando a API

Depois que a app está rodando:

### Login (criar conta):
```bash
curl -X POST http://localhost:5000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Admin Test",
    "email": "admin@test.com",
    "password": "teste123",
    "role": "admin"
  }'
```

### Login:
```bash
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@test.com",
    "password": "teste123"
  }' \
  -c cookies.txt
```

### Ver dados do usuário logado:
```bash
curl http://localhost:5000/api/user -b cookies.txt
```

---

## 📝 Estrutura de Pastas (criadas automaticamente)

```
instance/
└── ibc_ensino.db          # Banco SQLite (criado automaticamente)
```

---

## 🔧 Variáveis de Ambiente

Se precisar, crie um arquivo `.env`:

```
FLASK_ENV=development
SECRET_KEY=sua-chave-secreta-aqui
DATABASE_URL=sqlite:///ibc_ensino.db
```

(Opcional — app.py tem defaults)

---

## ✅ Checklist antes de começar

- [ ] Novo Replit criado
- [ ] Arquivos do projeto uploaded
- [ ] `pip install -r requirements.txt` executado
- [ ] Banco criado com `db.create_all()`
- [ ] App rodando em `python app.py`
- [ ] URL do Replit funciona (`https://...replit.dev`)
- [ ] Consegue fazer curl para `/api/auth/login`

Se tudo passou ✅, estamos prontos para Claude Code!

---

## 📞 Contato
Samir Hamdan  
samirhamdan75@gmail.com  
Alessio Soluções em Serviços e Segurança  
Campo Grande, MS
