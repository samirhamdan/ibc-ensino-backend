# 📚 HISTÓRICO COMPLETO — IBC Ensino

## 🎯 Objetivo Geral
Plataforma EAD (educação a distância) para Igreja Batista Central de Campo Grande, MS.
- Cursos com módulos, materiais (PDF/links), quizzes e perguntas
- 4 perfis: Admin, Professor/Tutor, Aluno Interno, Aluno Externo
- Dashboard com estatísticas e relatórios
- **Agora:** Migrar para autenticação real (Flask + SQLite)

---

## ✅ FASE 1 — MVP HTML/JS (CONCLUÍDO — vercel.app)

### Funcionalidades Implementadas:

#### 🔐 Autenticação & Perfis
- 4 tipos de usuário:
  - **Admin**: Acesso total (cursos, usuários, dashboard, categorias)
  - **Professor/Tutor**: Edita cursos vinculados, responde perguntas, vê progresso alunos
  - **Aluno Interno (✝️)**: Membro da igreja, acesso a TODOS os cursos
  - **Aluno Externo (👤)**: Visitante, acesso apenas cursos "públicos"
- Menu lateral se adapta por perfil
- Topbar mostra nome + perfil do usuário logado
- Dados em localStorage (INSEGURO — será corrigido na Fase 2)

#### 📚 Gestão de Cursos
- 3 cursos de exemplo com dados estruturados
- Cada curso tem:
  - **Resumo**: descrição, duração, ícone emoji
  - **4 Módulos**: nome + duração estimada
  - **Materiais**: PDFs e links de vídeo (upload by tutor)
  - **Quiz**: 3-4 questões com múltipla escolha, feedback automático
  - **Perguntas**: alunos perguntam, tutor responde
- Filtro por categoria (Teologia, Crescimento, Bíblia, etc)
- Visibilidade: "Interno" ou "Público"
- Tutor responsável aparece no resumo

#### 📊 Dashboard (Admin)
- 6 cards KPI:
  - Total de alunos internos
  - Total de alunos externos
  - Total de professores
  - Cursos ativos
  - Alunos com atividade
  - Cursos concluídos
- Tabela de progresso por aluno (iniciados/concluídos/progresso%)
- Tabela de desempenho por curso (quantos iniciaram/concluíram)
- Mostra tutor responsável por cada curso

#### 🗂️ Catálogo de Cursos
- Alunos: visualizar todos cursos (filtra por perfil)
- Cards com ícone, nome, categoria, duração, materiais, questões
- Barra de progresso individual por curso
- Filtro por categoria
- Admin vê versão especial com editar/remover

#### 📖 Página do Curso (5 abas)
1. **Resumo**: Descrição, duração, estatísticas, editar (tutor)
2. **Módulos**: Lista numerada com duração, adicionar (tutor)
3. **Material**: PDFs + links, visualizador nativo, upload (tutor)
4. **Exercícios**: Quiz com gabarito, feedback por questão, pontuação (60% min)
5. **Perguntas**: Fórum texto. Aluno pergunta → Tutor responde. Badges "Pendente/Respondida"

#### 👥 Gerenciamento de Usuários
- Tabela com nome, e-mail, perfil, ação
- Cadastrar novo usuário (seletar perfil)
- Cards explicando cada perfil com permissões
- **Novo:** Botão "Vincular Cursos" para tutor
  - Dialog com checkboxes: seleciona quais cursos tutor gerencia
  - Salva vinculação

#### 🏷️ Categorias
- Lista de categorias padrão (Teologia, Crescimento, etc)
- Admin pode criar/remover categorias
- Novo curso seleciona categoria de dropdown

#### 📊 Identidade Visual
- Cor principal: `#008ea8` (azul teal IBC)
- Logo: ESCOLA_DA_IBC.png + Logo-IBC-Horizontal.png
- Fonte: Playfair Display (títulos) + DM Sans (corpo)
- Design limpo, institucional, branco/gelo com azul

---

## 🚀 FASE 2 — AUTENTICAÇÃO REAL (COMEÇANDO AGORA)

### Objetivo:
Migrar de localStorage para **Flask + SQLite** com:
- ✅ Senhas criptografadas (bcrypt)
- ✅ Sessão server-side segura
- ✅ API REST com permissões no backend
- ✅ Sincronização entre dispositivos
- ✅ Escalável para múltiplos usuários

### Stack:
```
Backend:
- Flask 2.3 (framework web)
- SQLAlchemy (ORM para banco de dados)
- bcrypt (criptografia de senha)
- Flask-Session (sessão server-side)
- Flask-CORS (requisições cross-origin)

Database:
- SQLite (dev/MVP)
- PostgreSQL (produção, depois)

Frontend:
- Mesmo index.html
- Requisições fetch() → API
- Sem mudança visual
```

### Arquivos a Criar:
```
ibc-ensino-backend/
├── app.py                 ← Flask app + factory + config
├── models.py              ← SQLAlchemy models (User, Course, etc)
├── config.py              ← Configurações
├── requirements.txt       ← Dependências pip
├── routes/
│   ├── auth.py           ← /api/auth/signup, login, logout, reset
│   ├── courses.py        ← /api/courses (CRUD + permissões)
│   ├── progress.py       ← /api/progress (salvar avanço)
│   └── questions.py      ← /api/questions (perguntas/respostas)
├── index.html            ← Adaptado para fetch() → API
├── index_atual.html      ← Backup versão localStorage
├── ESCOLA_DA_IBC.png     ← Logo
├── Logo-IBC-Horizontal.png ← Logo
├── README.md             ← Setup Replit
├── BRIEFING.md           ← Contexto técnico
└── instance/
    └── ibc_ensino.db     ← Criado automaticamente
```

### Tabelas SQLite:

#### users
```sql
id INTEGER PRIMARY KEY
name VARCHAR(255) NOT NULL
email VARCHAR(255) UNIQUE NOT NULL
password_hash VARCHAR(255) NOT NULL -- bcrypt
role ENUM('admin', 'tutor', 'aluno-interno', 'aluno-externo')
cursos JSON -- tutores: quais cursos gerenciam
created_at TIMESTAMP
```

#### courses
```sql
id INTEGER PRIMARY KEY
name VARCHAR(255) NOT NULL
tag VARCHAR(100) -- categoria
icon VARCHAR(10) -- emoji
acesso VARCHAR(20) -- 'interno' ou 'publico'
resumo TEXT
duracao VARCHAR(100)
modules JSON -- [{nome, dur}, ...]
materiais JSON -- [{name, url, tipo, size}, ...]
quiz JSON -- [{q, opts, ans, exp}, ...]
perguntas JSON -- [{texto, autor, data, resposta}, ...]
created_by INTEGER FK users(id)
created_at TIMESTAMP
```

#### progress
```sql
id INTEGER PRIMARY KEY
user_id INTEGER FK users(id)
course_id INTEGER FK courses(id)
material_done BOOLEAN
quiz_score INTEGER
quiz_submitted_at TIMESTAMP
UNIQUE(user_id, course_id)
```

#### questions
```sql
id INTEGER PRIMARY KEY
course_id INTEGER FK courses(id)
user_id INTEGER FK users(id)
texto TEXT NOT NULL
resposta TEXT
respondido_por INTEGER FK users(id)
created_at TIMESTAMP
respondido_at TIMESTAMP
```

### Dados Migrados (da versão localStorage):

**Usuários:**
- `admin@ibc.com` / `admin123` → Admin
- `tutor@ibc.com` / `ibc2024` → Tutor (vinculado a cursos)
- `joao@ibc.com` / `ibc2024` → Aluno Interno
- `pedro@email.com` / `ibc2024` → Aluno Externo

**Cursos (3 de exemplo):**
1. Fundamentos da Fé (Teologia, Interno)
2. Discipulado Cristão (Crescimento, Interno)
3. Estudo Bíblico — Salmos (Bíblia, Público)

---

## 📋 Endpoints API (a implementar)

### Auth
- `POST /api/auth/signup` → Cadastrar (name, email, password, role)
- `POST /api/auth/login` → Login (email, password) → sessionid
- `POST /api/auth/logout` → Limpar sessão
- `POST /api/auth/reset-password` → Enviar link reset por email
- `GET /api/user` → Dados usuário logado

### Courses
- `GET /api/courses` → Listar (filtrado por perfil)
- `POST /api/courses` → Criar (admin/tutor)
- `GET /api/courses/<id>` → Detalhes
- `PUT /api/courses/<id>` → Editar (tutor do curso)
- `DELETE /api/courses/<id>` → Remover (admin)
- `POST /api/courses/<id>/modulos` → Adicionar módulo
- `POST /api/courses/<id>/materiais` → Upload PDF/link
- `DELETE /api/courses/<id>/materiais/<mat_id>` → Remover

### Progress
- `GET /api/progress/<courseId>` → Progress do aluno
- `POST /api/progress/<courseId>` → Salvar (material_done, quiz_score)

### Questions
- `GET /api/questions/<courseId>` → Listar perguntas curso
- `POST /api/questions/<courseId>` → Nova pergunta
- `POST /api/questions/<id>/responder` → Tutor responde (tutor only)

---

## 🎯 Cronograma (Estimado)

| Dia | Atividade | Tempo |
|-----|-----------|-------|
| 1 | Setup Flask, models.py, migrations | 4h |
| 2 | Endpoints auth (signup, login, logout) | 4h |
| 3-4 | Endpoints courses, materiais, módulos | 6h |
| 5 | Endpoints quiz, progress, questions | 4h |
| 6 | Adaptar frontend (index.html fetch → API) | 4h |
| 7 | Testes, bugfixes, deploy | 4h |
| **TOTAL** | | **30h** |

---

## 🔍 Checklist de Implementação

### Dia 1 — Setup
- [ ] app.py com Flask factory
- [ ] config.py com settings
- [ ] models.py com 5 tabelas (User, Course, Material, Progress, Question)
- [ ] requirements.txt com dependências
- [ ] Criar banco com `db.create_all()`
- [ ] Health check `/health` funcionando

### Dia 2 — Autenticação
- [ ] `POST /api/auth/signup` com validação
- [ ] `POST /api/auth/login` com bcrypt
- [ ] `POST /api/auth/logout`
- [ ] `GET /api/user` (require login)
- [ ] Session storage no servidor

### Dia 3-4 — Cursos
- [ ] `GET /api/courses` (filtrado por perfil)
- [ ] `POST /api/courses` (admin only)
- [ ] `PUT /api/courses/<id>` (tutor do curso)
- [ ] `DELETE /api/courses/<id>` (admin)
- [ ] Endpoints de módulos e materiais
- [ ] Validar permissões tutor

### Dia 5 — Quiz e Perguntas
- [ ] `POST /api/progress/<id>` (submit quiz)
- [ ] `GET /api/questions/<id>` (listar)
- [ ] `POST /api/questions/<id>` (nova pergunta)
- [ ] `POST /api/questions/<id>/responder` (tutor)

### Dia 6 — Frontend
- [ ] Remover localStorage
- [ ] Adaptar doLogin para fetch `/api/auth/login`
- [ ] Adaptar renderCourseList para fetch `/api/courses`
- [ ] Adaptar salvar (save()) para fetch `/api/progress`
- [ ] Testar fluxo completo

### Dia 7 — Deploy & QA
- [ ] Deploy no Replit
- [ ] Testar todos endpoints com curl
- [ ] Testar fluxos de usuário (login → curso → quiz → pergunta)
- [ ] Verificar permissões (tutor não acessa curso de outro)
- [ ] Verificar externo não vê curso interno

---

## 🎨 Frontend (index.html) — Mudanças Mínimas

**Remover:**
```javascript
let users = JSON.parse(localStorage.getItem('ibc_users')||'null') || USERS_DEFAULT;
let courses = JSON.parse(localStorage.getItem('ibc_courses')||'null') || COURSES_DEFAULT;
let progress = JSON.parse(localStorage.getItem('ibc_progress')||'null') || {};
function save() { localStorage.setItem(...) }
```

**Adicionar:**
```javascript
const API = '/api'; // ou window.location.origin + '/api'

async function doLogin(email, pass) {
  const res = await fetch(API + '/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include', // importante: envia cookie de sessão
    body: JSON.stringify({ email, password: pass })
  });
  if (res.ok) {
    const user = await res.json();
    currentUser = user;
    renderCourseList();
    show('main');
  } else {
    alert('Login falhou: ' + (await res.text()));
  }
}

async function loadCourses() {
  const res = await fetch(API + '/courses', { credentials: 'include' });
  if (res.ok) courses = await res.json();
  else if (res.status === 401) { /* redirecionar login */ }
}

async function saveProgress() {
  await fetch(API + '/progress/' + currentCourse.id, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(progress[`${currentUser.id}_${currentCourse.id}`])
  });
}
```

**Tudo mais:** Mantém igual (HTML, CSS, lógica de UX)

---

## 🔐 Segurança Implementada

✅ Senhas: bcrypt (10+ rounds)  
✅ Sessão: server-side, httpOnly cookie  
✅ CSRF: SameSite=Lax  
✅ Permissões: validadas no backend (não confia cliente)  
✅ HTTPS: obrigatório em produção  
✅ CORS: apenas origins autorizados  

---

## 🚢 Deployment

**MVP (Replit):**
- PostgreSQL em Supabase (free tier)
- Redis para sessão (Replit built-in)
- Domínio: `https://seu-usuario-ibc-ensino-backend.replit.dev`

**Produção (depois):**
- VPS (Heroku, Railway, PythonAnywhere)
- PostgreSQL gerenciado
- Email service (SendGrid) para reset de senha
- CDN para ativos (Cloudflare)

---

## 📞 Contato & Notas

**Desenvolvedor:** Samir Hamdan (samirhamdan75@gmail.com)  
**Cliente:** Igreja Batista Central, Campo Grande, MS  
**Stack:** Flask + SQLAlchemy + SQLite → PostgreSQL  
**Status:** Fase 2 em andamento (Claude Code)

---

## 📌 Próximos Passos Após Fase 2

1. 📺 **Player de vídeo integrado** (2 dias)
2. 🎓 **Certificado de conclusão** (2 dias)
3. 📈 **Relatório tutor** (2-3 dias)
4. 💬 **Notificações** (1 dia)
5. 🎁 **Badges/gamificação** (2 dias)
6. 💳 **Pagamento** (Stripe, 4-5 dias)
7. 📱 **App mobile** (Flutter, 2-3 semanas)

---

**Última atualização:** Janeiro 2025  
**Versão:** Fase 2.0-beta (Claude Code)
