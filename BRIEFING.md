# IBC Ensino — Briefing Completo

## 📋 Projeto
**Igreja Batista Central (IBC) de Campo Grande, MS**  
Plataforma EAD (educação a distância) para estudos, cursos e treinamentos.

---

## 🎯 Fase 1 — MVP em HTML/JS (CONCLUÍDO)
**Status:** Publicado em `ibc-ead.vercel.app` (Vercel)

### O que foi feito:
✅ Login com 4 perfis (Admin, Professor/Tutor, Aluno Interno, Aluno Externo)  
✅ 5 abas por curso (Resumo, Módulos, Material, Exercícios, Perguntas)  
✅ Dashboard com estatísticas e relatórios  
✅ Catálogo de cursos com filtro por categoria  
✅ Quiz com correção automática  
✅ Progresso do aluno (%)  
✅ Upload de PDFs e links de vídeo  
✅ Perguntas/respostas (aluno ↔ tutor)  
✅ Painel admin para gerenciar usuários, cursos, categorias  
✅ Identidade visual: 🏛️ Logo-IBC-Horizontal.png (Igreja), cor #008ea8, fonte Playfair Display  

### Limitações atuais (localStorage):
❌ Senhas em texto plano  
❌ Dados vulneráveis (localStorage = inseguro)  
❌ Sem sincronização entre dispositivos  
❌ Não escala para múltiplos servidores  

---

## 🚀 Fase 2 — Autenticação Real (COMEÇANDO AGORA)
**Objetivo:** Migrar para Flask + SQLite com autenticação segura

### Arquitetura Nova:
```
Backend (Flask):
├── app.py (main)
├── models.py (SQLAlchemy ORM)
├── routes/ (endpoints API)
│   ├── auth.py (login, signup, logout)
│   ├── courses.py (CRUD cursos)
│   ├── progress.py (salvar progresso)
│   └── questions.py (perguntas/respostas)
├── config.py (configurações)
└── requirements.txt (dependências)

Frontend (mesmo HTML/JS, mas com fetch() para API):
├── index.html (adaptado)
├── Logo-IBC-Horizontal.png     ← USAR ESTA
└── (ESCOLA_DA_IBC.png removida)

Banco de Dados:
└── instance/ibc_ensino.db (SQLite)
```

### Stack:
- **Backend:** Flask 2.3 + SQLAlchemy + bcrypt
- **Banco:** SQLite (depois migra para PostgreSQL)
- **Sessão:** Flask-Session + Redis (Replit tem grátis)
- **Hospedagem:** Replit (novo)

---

## 📊 Dados Atuais (para migrar)

### Usuários (4 perfis):
1. **Admin** — Acesso total
   - `admin@ibc.com` / `admin123`
   
2. **Professor/Tutor** — Edita cursos vinculados
   - `tutor@ibc.com` / `ibc2024`
   - Cursos: (vinculados na tabela)
   
3. **Aluno Interno** — Acesso a todos os cursos
   - `joao@ibc.com` / `ibc2024`
   
4. **Aluno Externo** — Cursos públicos apenas
   - `pedro@email.com` / `ibc2024`

### Cursos (3 de exemplo):
1. **Fundamentos da Fé** (Teologia, Interno)
   - 4 módulos, 0 PDFs, 4 questões
   - Resumo: "Um estudo introdutório sobre os pilares da fé cristã..."
   
2. **Discipulado Cristão** (Crescimento, Interno)
   - 4 módulos, 0 PDFs, 3 questões
   
3. **Estudo Bíblico — Salmos** (Bíblia, Público)
   - 4 módulos, 0 PDFs, 3 questões

### Estrutura de Curso:
```javascript
{
  id: <número>,
  name: "Nome do Curso",
  tag: "Categoria",
  icon: "📖",
  acesso: "interno" | "publico",
  resumo: "Descrição...",
  duracao: "4 semanas",
  modules: [
    { nome: "Módulo 1", dur: "30 min" },
    ...
  ],
  materiais: [
    { name: "PDF", url: "...", tipo: "pdf", size: "2 MB" },
    { name: "Link", url: "https://...", tipo: "link" }
  ],
  pdfs: [], // compatibilidade com versão antiga
  quiz: [
    { q: "Pergunta?", opts: [...], ans: 0, exp: "Explicação" },
    ...
  ],
  perguntas: [
    { texto: "...", autor: "João", data: "01/01 10:00", resposta: "" }
  ]
}
```

### Progresso:
```javascript
progress = {
  "userId_courseId": {
    materialDone: true/false,
    quizScore: 2, // questões acertadas
    respondidoPor: "Prof. Maria"
  }
}
```

---

## 🔌 Endpoints da API (a implementar)

### Autenticação
- `POST /api/auth/signup` → Cadastrar novo usuário
- `POST /api/auth/login` → Login (retorna sessão)
- `POST /api/auth/logout` → Logout
- `POST /api/auth/reset-password` → Recuperar senha
- `GET /api/user` → Dados do usuário logado

### Cursos
- `GET /api/courses` → Listar cursos (filtrado por perfil)
- `POST /api/courses` → Criar novo curso (admin only)
- `GET /api/courses/<id>` → Detalhes do curso
- `PUT /api/courses/<id>` → Editar curso (tutor do curso)
- `DELETE /api/courses/<id>` → Remover curso (admin)

### Materiais
- `POST /api/courses/<id>/materiais` → Upload PDF/link
- `DELETE /api/courses/<id>/materiais/<mat_id>` → Remover material

### Módulos
- `POST /api/courses/<id>/modulos` → Adicionar módulo
- `DELETE /api/courses/<id>/modulos/<idx>` → Remover módulo

### Progresso
- `GET /api/progress/<courseId>` → Progresso do aluno neste curso
- `POST /api/progress/<courseId>` → Salvar progresso

### Quiz
- `POST /api/quiz/<courseId>/submit` → Enviar respostas do quiz
- `GET /api/quiz/<courseId>/resultado` → Ver resultado

### Perguntas
- `GET /api/questions/<courseId>` → Listar perguntas do curso
- `POST /api/questions/<courseId>` → Nova pergunta
- `POST /api/questions/<id>/responder` → Tutor responde

---

## 📱 Frontend — Adaptações Necessárias

O `index.html` atual precisa de mínimas mudanças:
1. Remover `localStorage` → usar `fetch()` para API
2. Remover validação local de login → confiar no servidor
3. Manter 100% da interface visual
4. Manter toda a lógica de UX (abas, filtros, etc)

Exemplo de mudança:
```javascript
// ANTES (localStorage)
let users = JSON.parse(localStorage.getItem('ibc_users')||'null');

// DEPOIS (API)
async function loadUser() {
  const res = await fetch('/api/user', { credentials: 'include' });
  if (res.ok) return res.json();
  else window.location.href = '/'; // redireciona login
}
```

---

## ✅ Próximos Passos

**Dia 1:** Setup Flask + Models + Banco SQLite  
**Dia 2:** Endpoints de Autenticação  
**Dia 3-4:** Endpoints de Cursos, Quiz, Perguntas  
**Dia 5:** Adaptar Frontend para API  
**Dia 6:** Deploy + Testes  

---

## 🔗 Links Importantes

**MVP Atual:** https://ibc-ead.vercel.app  
**GitHub (Vercel):** https://github.com/samirhamdan75/ibc-ead  
**Replit (será criado novo)**

---

**Instruções para Claude Code:**
1. Use esta briefing para contexto completo
2. Implemente dia por dia (commits após cada dia)
3. Teste endpoints com print() e curl enquanto desenvolvem
4. Mantenha compatibilidade com dados atuais do MVP
5. Prioridade: segurança > funcionalidade > beleza
