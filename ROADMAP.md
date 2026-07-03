# ROADMAP IBC Ensino — Auditoria Técnica, UX/UI e Novas Funcionalidades

> Documento de análise e planejamento. **Nenhuma alteração de código foi feita.**
> Base auditada: branch `claude/zen-hopper-SeRac`, ~5.100 linhas de Python (14 blueprints) + `index.html` monolítico (5.630 linhas) + 27 arquivos CSS.
> Produção ativa: `ibc-ensino.up.railway.app` (Railway + PostgreSQL, gunicorn, Python 3.12).
> Data: 2026-07-02.

---

## SUMÁRIO EXECUTIVO — o que é mais urgente

1. **🔴 Escalada de privilégio trivial no cadastro público.** `POST /api/auth/signup` aceita `role` do corpo da requisição e cria um admin sem nenhuma autenticação. Um único request com `{"role":"admin"}` dá controle total da plataforma. **Corrigir hoje.** (`routes/auth.py:23-50`)

2. **🔴 Dois caminhos silenciosos para takeover de conta.** `SECRET_KEY` tem fallback público hardcoded (`app.py:62`) e o seed recria `admin@ibc.com` / `TrocarSenha123!` a cada deploy se as env vars faltarem (`seed_production.py:21` + `railway.json:7`). Ambos dependem apenas de uma variável ausente no Railway — **verificar o dashboard do Railway em 2 minutos** e travar o boot quando faltarem.

3. **🔴 XSS armazenado por toda a interface.** Não existe nenhuma função de escape de HTML no frontend; nomes de perfil e textos de pergunta (controlados por qualquer aluno) são injetados via `innerHTML` no dashboard de todos os alunos, no painel de tutores/admin e na página **pública** de verificação de certificado. (`index.html:4178`, `:4092`, `:5361`, +~35 pontos)

4. **🟠 Bug de schema que derruba os dashboards do admin.** O código lê `Progress.passed`, coluna que não existe no modelo — assim que houver qualquer linha em `Progress`, o perfil de usuário e a lista de cursos do admin estouram 500. (`routes/admin.py:225,258`, `routes/courses.py:274`)

5. **🟠 Zero migrações de schema + uploads efêmeros.** O app só usa `db.create_all()`, que nunca adiciona colunas a tabelas existentes: a próxima mudança de modelo derruba produção com 500. E PDFs de material são gravados em `/tmp` sem volume — somem a cada deploy. Ambos são pré-requisito de infra antes de hospedar o "Vida em Prática".

**Ordem recomendada de ataque:** Segurança crítica (itens 1-3) → bug do `Progress.passed` (item 4) → Flask-Migrate + volume de uploads (item 5) → suíte de testes mínima + CI → então evoluir UX (Fase 2) e construir o programa por semanas (Fase 3).

---

# FASE 1 — AUDITORIA TÉCNICA

Classificação: **CRÍTICO** (afeta segurança/funcionamento) · **IMPORTANTE** (afeta manutenibilidade) · **DESEJÁVEL** (nice to have).

## 1.1 Segurança

### CRÍTICO

- **`routes/auth.py:23-50` — Escalada de privilégio no signup público.** O endpoint é anônimo, lê `role` do corpo e aceita `admin`/`tutor`, já criando a sessão. → Forçar `role='aluno'` no cadastro público; criação de tutor/admin só via endpoint autenticado de convite.
- **`app.py:62` — `SECRET_KEY` com fallback público.** Se a env var faltar, cookies de sessão são assinados com valor conhecido do repositório → forjar sessão de qualquer `user_id`. → Abortar boot (`raise RuntimeError`) quando `is_production` e sem `SECRET_KEY`.
- **`seed_production.py:21` + `railway.json:7` — Admin default recriado a cada deploy.** `admin@ibc.com` / `TrocarSenha123!` versionados; recriados se as env vars faltarem, inclusive se a conta for deletada. → Exigir `ADMIN_PASSWORD` sem default e falhar o seed se ausente.

### IMPORTANTE

- **`app.py:73-79` — CORS com curinga inseguro.** `https://*.vercel.app` / `https://*.replit.dev` com `supports_credentials=True`. Verificado empiricamente: o Flask-CORS trata a string como regex, então os curingas **não casam** com subdomínios reais mas **aceitam** domínios registráveis por atacante (ex.: `xvercelyapp.com`). Mitigado hoje só por `SameSite=Lax` + frontend same-origin. → Listar origens exatas ou regex correta.
- **`routes/certificates.py:113-125`, `routes/materials.py:140-143`, `app.py:151-158` — Arquivos servidos sem autenticação.** Download de certificado, PDFs de material e `/uploads/<path>` acessíveis por anônimo que souber o código/nome. → Exigir sessão (e posse/matrícula) antes de servir.
- **`routes/courses.py:57-62` — Detalhe de curso vaza para anônimo.** `GET /api/courses/<id>` não checa sessão e retorna módulos/materiais/quiz mesmo de cursos `acesso='interno'`. → Exigir autenticação e respeitar `acesso`.
- **`routes/gamification.py:237-257` — `/add-points` confia no cliente.** Aluno credita 100 pontos a si mesmo com `{'action':'course_completed'}`, ou pontos a terceiros via `question_id`. → Remover atribuição client-side; pontuar apenas server-side nos eventos reais.
- **`routes/certificates.py:34-72` — `/issue` sem validar conclusão.** Qualquer autenticado emite certificado para qualquer `course_id`/`trail_id`. → Validar 100% de conclusão antes de emitir.
- **`routes/questions.py:54-86` — Tutor responde perguntas de cursos alheios.** Só checa `role`, não a posse do curso. → Restringir tutor a cursos com `tutor_id == user.id`.
- **`routes/auth.py:53-79,266-292` — Sem rate limiting em login/forgot-password.** Brute-force de senha e abuso de envio de e-mail. → Flask-Limiter por IP/email.

### DESEJÁVEL

- **`routes/trails.py:152-209` — GET que muta estado.** `GET /api/trails/active` grava `completed_at`, credita XP/badge e faz commit; fragiliza CSRF sob `SameSite=Lax`. → Mover conclusão para POST idempotente.
- **`app.py:67` — Sem token CSRF.** `SameSite=Lax` é aceitável para POST, mas combinado com GETs que mutam e CORS curinga amplia a superfície. → Considerar CSRF token / `SameSite=Strict`.

> **Nota positiva:** sem SQL cru/`text()` (sem SQL injection); `secure_filename` + UUID + `send_from_directory` mitigam path traversal; nenhum `to_dict()` vaza `password_hash`; e-mails não vazam a alunos no feed/rankings.

## 1.2 Bugs e inconsistências

### CRÍTICO

- **`routes/admin.py:225,258`, `routes/courses.py:274` — `Progress.passed` inexistente.** O modelo `Progress` (`models.py:205-226`) só tem `material_done`, `quiz_score`, `quiz_total`. Assim que houver qualquer linha em `Progress`, o perfil de usuário e a lista admin de cursos estouram 500. → Usar `LessonProgress.passed` ou derivar de `quiz_score/quiz_total`.
- **`routes/dashboards.py:182,246-247` — Rota `/aluno/dashboard` registrada duas vezes.** `aluno_dashboard` e `aluno_externo_dashboard` colidem; a segunda vira código morto e `/aluno-externo/dashboard` nunca é chamado pelo frontend. → Remover o decorator duplicado.
- **`routes/lessons.py` × `routes/trails.py:99-121,176` — Dois modelos de progresso divergentes.** As aulas gravam só `LessonProgress`; a conclusão de trilha mede via `Progress`. Concluir todas as aulas de um curso **nunca** marca o curso como concluído dentro da trilha. → Unificar num único modelo de progresso.

### IMPORTANTE

- **`routes/auth.py:182-194` — `delete_user` sem cascade.** Nenhuma FK filha tem `ondelete='CASCADE'`; deletar usuário em Postgres viola FK e estoura 500. → Adicionar cascade ou apagar filhos antes.
- **`routes/admin.py:278-299` — `reset_user_progress` incompleto.** Apaga `Progress` e `UserTrail`, mas não `LessonProgress` (que é o progresso real). → Incluir `LessonProgress`.
- **`routes/gamification.py:305-328,121-131` — Corrida em conquistas/badges.** Checar-depois-inserir sem tratamento; sob concorrência viola `uq_user_achievement`/`uq_user_badge` → 500 sem rollback. → Capturar `IntegrityError` + rollback ou upsert.
- **`routes/gamification.py:37-42` × `models.py:578-594` × `seed.py:8-16` × `routes/trails.py:24-34` — Três cálculos de nível concorrentes.** `calculate_level` (100 pts/nível, teto 7) vs tabela `Level` (limiares não lineares) vs `_add_xp` (`current_level*100`). Níveis exibidos não batem com a tabela editável no admin. → Centralizar na tabela `Level`.

### DESEJÁVEL

- **`routes/certificates.py:224` — URL de verificação errada no PDF.** `APP_URL` nunca é gravado em `app.config`, então cai sempre em `localhost`. → Ler `os.getenv('APP_URL')` ou setar em config.
- **`routes/lessons.py:128-227` — Quiz de aula não dá pontos.** Sem `award_points` server-side; pontos de exercício só vêm do `/add-points` client-side (inseguro). → Pontuar server-side ao passar o quiz.
- **`routes/aluno.py:178-201` — `study-time` aceita `lesson_id` arbitrário** sem validar existência/posse. → Validar que a aula pertence a curso acessível.

## 1.3 Performance

### IMPORTANTE

- **`routes/dashboards.py:99-122,155-165,199-231,265-283` — N+1 severo nos dashboards.** Laços sobre `Course.query.all()` chamando `_completed_pct` (que consulta `Module`+`LessonProgress`) por curso e por aluno; o admin dashboard chega a O(cursos × alunos) queries. → Agregação SQL (`GROUP BY`) + `selectinload`.
- **`routes/gamification.py:101-112` — `_completed_courses_count` recalcula tudo por request.** Itera todos os cursos consultando `Module`+`LessonProgress`; chamado em `/aluno/stats`, `/achievements`, `check_and_grant_achievements`, `check_all_badges`. → Agregação única + cache por request.
- **`routes/admin.py:34-63,187-203`, `routes/trails.py:271-286` — N+1 nas listagens** de tutores/usuários/trilhas. → Joins + `func.count`.

### DESEJÁVEL

- **`models.py` (geral) — Faltam índices** em FKs e colunas de filtro/ordenação: `Question.course_id/user_id`, `Notification.user_id`, `LessonProgress.course_id`, `Progress.course_id`, `ActivityFeed.created_at/user_id`, `StudySession.user_id`, `Certificate.user_id`, `UserTrail.trail_id`, `TutorCourse.course_id`. → `index=True`.
- **`routes/dashboards.py:81-82,119` — Contagem em Python.** `LessonProgress.query.all()` carrega tudo para contar aprovados. → `func.count`/`func.avg` no banco.

## 1.4 Qualidade de código

### IMPORTANTE

- **`routes/*.py` (toda a camada) — Nenhum `rollback()` nos caminhos de falha** e nenhum `try/except` em torno de `commit`; qualquer erro vira 500 com sessão suja. → Wrapper de transação / `@app.errorhandler`.
- **Sistemas duplicados/legados coexistindo** (dívida técnica documentada, não resolver unilateralmente):
  - Badge/UserBadge (`models.py:297-329`) × Achievement/UserAchievement (`models.py:597-645`) — ambos chamados "Conquistas" na UI.
  - Progress (course-level) × LessonProgress (module-level) — critérios divergentes.
  - `calculate_level` legado × tabela `Level`.
  - → Decidir por um de cada par e remover o outro.

### DESEJÁVEL

- **Funções longas com múltiplas responsabilidades:** `submit_aula_quiz` (`lessons.py:128-227`, ~100L), `_generate_pdf` (`certificates.py:128-234`, ~107L), `get_user_profile` (`admin.py:207-275`, ~69L), `admin_dashboard` (`dashboards.py:68-133`), `active_trail` (`trails.py:152-209`). → Extrair helpers.
- **Naming PT/EN misturado:** `Module.nome/dur`, `Question.texto/resposta`, `Course.resumo/duracao/acesso`, `Quiz.q/opts/ans/exp` convivem com `name/status/created_at`; rotas `/modulos`,`/aulas` (PT) vs `/courses`,`/progress` (EN). → Padronizar.
- **Shapes de resposta inconsistentes:** `{'ok':True}` vs `{'success':True}` vs `{'message':...}` vs `{'saved':True}`; status codes divergentes (201 para ações não-criadoras). → Contrato único.
- **`LEVEL_NAMES` duplicado** em `gamification.py:13-16` e `dashboards.py:37-40`. → Centralizar.
- **Imports não usados:** `questions.py:6` (`Progress`), `lessons.py:7` (`UserPoints`,`Badge`,`UserBadge`), `certificates.py:10` (`UserTrail`), `gamification.py:4` (`timedelta`). → Remover.

## 1.5 Infraestrutura / DevOps

### CRÍTICO

- **Sem migrações de schema.** Único mecanismo é `db.create_all()` (`app.py:87`, `seed*.py`), que só cria tabelas ausentes e nunca adiciona colunas. Histórico confirma o risco: Sprint 6.2 adicionou `Question.status`/`resolved_at` e exigiu ALTER TABLE manual no SQLite. Produção só está em sincronia porque o Postgres foi criado do zero. **A próxima mudança de modelo em tabela existente derruba produção com 500.**
  > **Recomendação:** Adotar **Flask-Migrate agora**, enquanto prod e models estão em sincronia (momento mais barato). Passos: (1) `Flask-Migrate` no requirements + `Migrate(app, db)` na factory; (2) local `flask db init` + `flask db migrate -m "baseline"`; (3) em prod, uma vez, `flask db stamp head`; (4) mudar `preDeployCommand` para `flask db upgrade && python seed_production.py`; (5) remover `create_all()` da factory. Esforço: 2-4h.
- **Uploads em filesystem efêmero.** `UPLOAD_FOLDER='/tmp/uploads'` (herança do Vercel) + `materials.py` grava PDF em disco (banco guarda só a URL). No Railway sem volume, **todo PDF de material some no próximo deploy**, deixando `Material` apontando para 404. → Anexar Volume do Railway ou storage externo (S3/R2); curto prazo, usar só materiais tipo "link".

### IMPORTANTE

- **`railway.json:8` — 1 worker gunicorn.** Sem `--workers`/`--threads`, uma requisição por vez; gerar PDF de certificado ou query lenta bloqueia a plataforma inteira. → `gunicorn --workers 2 --threads 4 --access-logfile - ...`.
- **`seed.py:20-21,41-42,66-67` — Seeds que não convergem.** `seed_config/levels/badges` checam "tabela vazia", não por linha: idempotentes contra duplicata, mas um nível/badge novo em sprint futuro **nunca** é inserido em prod. → Converter para check-per-row (padrão já usado em `seed_achievements`).
- **`seed_production.py` — `seed_badges()` nunca é chamado.** Tabela `Badge` vazia em prod → todo o sistema de badges (incl. badges de trilha) está silenciosamente morto em produção. → Adicionar ao `main()`.
- **`requirements.txt:4` — `Flask-Session` é dependência morta** (nunca importada; sessões usam cookie assinado padrão). → Remover.
- **Zero testes / zero CI** para ~5,1k linhas + frontend. Toda regressão é descoberta em produção.
  > **Recomendação:** `pytest` + fixture com SQLite in-memory + ~15-25 testes de fumaça via `test_client` (login ok/errado, guards de role → 403, CRUD de curso, upload rejeitando não-PDF, `/health`) + workflow `.github/workflows/ci.yml` rodando em cada push. Esforço: 1-2 dias.
- **Backup/recovery não verificável no repo.** Sem rotina de `pg_dump`; backups nativos do Railway dependem de config no dashboard. → Habilitar backups no serviço Postgres + cron de `pg_dump` para storage externo.
- **44 `print()` em 17 arquivos, zero `logging`.** Sem access log do gunicorn. → `PYTHONUNBUFFERED=1`, `--access-logfile -`, migrar para `app.logger`.

### DESEJÁVEL

- **Artefatos do Vercel abandonado** (`vercel.json`, `api/index.py`, checagem `os.getenv('VERCEL')`, comentários "Neon"). Não quebram o Railway mas confundem qual é a plataforma. → Remover.
- **`index_atual.html` (114KB)** — backup legado morto, não servido por rota alguma. → Deletar (git preserva).
- **README desatualizado** — ainda descreve setup Replit, anterior aos Sprints 6.x/7. → Reescrever com fluxo Railway.
- **`/health` (`app.py:190`) retorna `'db':'connected'` estático** sem query. → Adicionar `healthcheckPath` no railway.json + `SELECT 1` real.
- **Console do Railway sem venv no PATH** — `python seed_production.py` falha com `ModuleNotFoundError: flask`. → Documentar one-liner `/opt/venv/bin/python make_admin.py <email>` no README.

---

# FASE 2 — UX/UI E DESIGN

Priorização por **esforço** (B/M/A) × **impacto percebido** (B/M/A).

## 2.1 XSS de renderização (segurança + confiabilidade) — **Esforço B / Impacto A**

Já listado na Fase 1 como crítico, mas é também um problema de frontend estrutural: **não existe `escapeHtml()` na base**. A correção é de baixo esforço e altíssimo impacto: criar um helper e aplicá-lo em todos os pontos de `innerHTML` que recebem dados de usuário. Pontos principais: `renderActivityFeed` (`index.html:4178`), dashboard tutor (`:4092`), fila admin de perguntas (`:2933`), `renderPerguntas` (`:1904`), verificação pública de certificado (`:5361`), tabelas admin de usuários (`:3085`,`:1985`). **Prioridade máxima da Fase 2.**

## 2.2 Consistência visual — **Esforço M / Impacto M**

- **Dois `:root` conflitantes** (`app.css:1-7` × `design-system.css:2-98`). O legado define `--gold:#008ea8` (teal) mas o design-system vence com `--gold:#f1c40f` (amarelo) — CSS legado foi escrito assumindo gold=teal, origem de cores erradas. → Unificar tokens num único `:root`.
- **Regras duplicadas e conflitantes:** `.btn-primary` (`app.css:25` × `buttons.css:59`), `.btn-secondary` (`app.css:119` × `buttons.css:74`), `.toast` (`alerts.css:79` × `toast.css:12`), `.question-item` (`dashboard-cards.css:163` × `sprint62.css:162`). → Remover as versões legadas.
- **368 `style=""` inline** no markup gerado + ~40 hex hardcoded burlando tokens. → Migrar para classes/variáveis.

## 2.3 Responsividade — **Esforço M-A / Impacto A**

- **CRÍTICO: sidebar sem colapso mobile.** Não há hamburger/off-canvas (grep=0). O `@media` de sidebar (`app.css:241`) é anulado por `min-width:240px` de `navigation.css:66` (carregado depois, mesma especificidade). No celular a navegação ocupa 240px fixos com `height:100vh`. → Implementar toggle off-canvas real + `min-width` responsivo.
- **Tabelas admin v1 sem scroll horizontal** (`.table-users`, `:2043`). → Wrapper `overflow-x:auto`.
- **`.form-row` do fluxo do aluno não colapsa** (`app.css:134`); só a versão admin colapsa a 768px. → Media query para o fluxo aluno.

## 2.4 Acessibilidade — **Esforço A / Impacto M**

- **Navegação inteira por `<div onclick>`** (37 divs, 224 `onclick`, zero `tabindex`/`role`). Teclado não navega. → `<button>` ou `role="button" tabindex="0"` + keydown.
- **Zero `<label for>`** — leitores de tela não vinculam rótulo↔campo. → Associar todos.
- **Botões só-ícone sem `aria-label`** consistente; **modais sem focus-trap/retorno de foco** (`role="dialog"`/`aria-modal` ausentes).
- **Contraste limítrofe:** `.icon--gold #e9c46a` sobre branco (<3:1, falha AA); cinza `#7f8c8d` sobre branco (~3.5:1, falha para texto pequeno, usado em toda `.stat-label`).

## 2.5 Estados vazios / loading / erro — **Esforço M / Impacto A**

- **CRÍTICO: `api()` (`:362`) não trata nada globalmente** — retorna `res` cru, sem interceptor para 401 (sessão expirada não redireciona ao login) nem 5xx. **Sem error boundary global** (`unhandledrejection`/`window.onerror` = 0) → tela branca em qualquer falha de render fora dos 3 dashboards. → Interceptor central de status + handler global de rejeições.
- Vários renders secundários falham silenciosamente (catálogo mostra "Nenhum curso" indistinguível de erro; `selectCourse`/`loadAula` usam `alert()` sem loading).

## 2.6 Fluxos / fricção — **Esforço B-M / Impacto A**

- **CRÍTICO: painel "Aula concluída" sequestra o usuário** (`:1324-1351`). O `setTimeout(openLesson, 3000)` (`:1348`) só é cancelado pelos botões do próprio painel — nenhuma navegação lateral nem Esc o cancela, e o overlay `position:fixed;inset:0` não fecha no clique-fora. → Cancelar o timeout em qualquer troca de rota + permitir Esc/clique-fora.
- **Double-submit:** login, quiz, pergunta, resposta **não desabilitam o botão** durante o `await` (só 5 handlers no arquivo o fazem). → Desabilitar no início do fetch.
- **~30 `alert()`/`confirm()` nativos** convivendo com `showToast` — UX inconsistente e bloqueante.
- **Funcionalidade morta exposta:** botões de categoria (`:4522`) só mostram `alert('não suportado')`; tour guiado aponta para `#nav-questions` inexistente (`:5468`); "Preview como aluno" (`:2371`) não sandboxa e pode gerar progresso/pontos reais para o admin.

## 2.7 Viabilidade dos itens planejados

### Streaks (dias consecutivos) — **Esforço B**

Os dados já existem: `UserPoints.last_activity_date` (`models.py:430`, tipo Date) é a base; `StudySession`/`LessonProgress.completed_at` dão o histórico. **Backend:** duas colunas em `UserPoints` (`current_streak`, `longest_streak`) + lógica de ~10 linhas no ponto onde pontos são creditados (comparar `date.today()` com `last_activity_date`: ontem→incrementa, hoje→mantém, gap>1→reseta). Expor em `/gamification/user-stats` e `/aluno/stats` (já consumidos). **Frontend:** um chip "🔥 N dias" ao lado de `.hero-level-label` (`:4715`), reusando o estilo de pill do hero. **Riscos:** fuso horário (fixar timezone no backend) e decidir se streak = "qualquer atividade" (usar StudySession) ou "ganhou pontos".

### Cards estilo Netflix — **Esforço B-M**

O `course-card-v2` (`_courseCardV2`, `:4419` + `course-cards.css:200-308`) **já tem** `:hover{transform:translateY(-4px);box-shadow:...}` e `scale(1.12)` no ícone. A repaginação toca: (1) trocar `translateY` por `scale(1.04)` com `z-index` no hover para "saltar" sobre vizinhos; (2) overlay de ação ("Continuar/Começar") revelado no hover; (3) ajustar o grid para o card ampliado não ser cortado. **Riscos:** layout shift (usar `transform`, não `width/height`; talvez `overflow:visible` no grid); mobile/touch não tem `:hover` (fallback sempre-visível <768px); a11y (é a oportunidade de converter o `<div onclick>` em elemento focável).

---

# FASE 3 — NOVAS FUNCIONALIDADES

Contexto: hospedar o **"Vida em Prática"** — programa híbrido de 10 semanas, aplicação da fé em casa/trabalho/igreja. O sistema atual tem **Trilhas** (sequências de cursos), tutores, notificações, avisos e e-mail (via forgot-password), mas **nada disso é orientado a tempo, turmas ou prazos**. As lacunas abaixo são o que falta para suportar um programa estruturado.

Esforço: **P** (pequeno, ~dias) · **M** (médio, ~1-2 semanas) · **G** (grande, ~semanas).

## 3.1 Programa estruturado por semanas com prazos

- **Turmas/Coortes (`Cohort`)** — **G, fundacional.** Hoje não há como matricular um grupo que começa numa data e progride junto. Modelo novo `Cohort` (trilha-base, data de início, data de fim) + `CohortEnrollment` (user↔cohort). Resolve: "a turma de setembro do Vida em Prática". Dependências: modelo de progresso unificado (bug crítico 1.2) antes de construir em cima.
- **Liberação por semana com data (`drip content`)** — **M.** Cada módulo/curso da trilha ganha `unlock_offset_days` (ou `unlock_date` por coorte); o backend esconde/bloqueia conteúdo ainda não liberado. Resolve o formato "semana N abre na segunda-feira". Depende de Cohort.
- **Prazos e status de entrega** — **M.** Cada semana tem `due_date`; aluno vê "em dia / atrasado / concluído". Resolve accountability, central num programa de 10 semanas.

## 3.2 Acompanhamento pastoral / tutoria

Tutores já existem e podem ser designados a cursos e responder perguntas — mas não há visão de acompanhamento de pessoas.

- **Painel do tutor por coorte** — **M.** Lista dos alunos da sua turma com progresso semanal, última atividade, quem está travado/atrasado. Reusa os counters existentes (com as correções de N+1 da Fase 1). Potencializa o papel do tutor de "responde dúvidas" para "pastoreia um grupo".
- **Notas pastorais privadas (`PastoralNote`)** — **P-M.** Tutor registra observações por aluno (visível só a tutor/admin). Resolve continuidade do acompanhamento entre encontros híbridos.
- **Check-in / presença híbrida** — **M.** Marcar presença nos encontros presenciais por semana (o "híbrido" do programa). Modelo `Attendance` (user, cohort, week, present). Alimenta relatórios de engajamento real, não só online.

## 3.3 Comunicação com alunos

- **Lembretes automáticos por e-mail** — **M.** A infra de e-mail já existe (forgot-password). Adicionar jobs: "sua semana N abre hoje", "você está atrasado", "parabéns por concluir". Depende de um agendador (cron do Railway ou tabela de jobs). Alto impacto em retenção num programa longo.
- **Diário de aplicação prática (`ReflectionJournal`)** — **M, muito aderente ao programa.** "Vida em Prática" é sobre *aplicar* a fé — cada semana pede um registro reflexivo ("o que apliquei em casa/trabalho/igreja"). Modelo `Reflection` (user, week, texto, privacidade). Tutor pode ler e comentar. É o coração pedagógico do programa e hoje não existe.
- **Mural da turma / partilha** — **M.** Estender o `ActivityFeed` existente para um feed por coorte com partilhas voluntárias — senso de comunidade num grupo que caminha junto.

## 3.4 Relatórios e analytics para a igreja

- **Relatório de conclusão por coorte** — **M.** Quantos começaram/concluíram cada semana, taxa de retenção, tempo médio. Reusa os dashboards (com correção de N+1). Essencial para a liderança avaliar o programa.
- **Exportação CSV/PDF** — **P.** Admin exporta lista de alunos + progresso para acompanhamento offline/reuniões de liderança.
- **Engajamento agregado** — **M.** Combinar `StudySession` (tempo de estudo), streaks e presença híbrida num painel de saúde da turma.

## 3.5 Lacunas transversais identificadas

- **Auto-matrícula / inscrição em programa** — **M.** Hoje a matrícula em curso/trilha é feita pelo admin. Um programa aberto precisa de fluxo de inscrição do próprio aluno (com aprovação opcional do tutor).
- **Certificado de programa completo** — **P.** Já há certificados de curso e trilha; estender para "concluiu o Vida em Prática" (as 10 semanas). Reusa a infra de `certificates.py`.
- **Onboarding específico do programa** — **P.** O onboarding genérico existe; uma trilha de boas-vindas do programa (o que esperar das 10 semanas, ritmo, compromisso) reduz evasão inicial.

## 3.6 Sequenciamento recomendado da Fase 3

1. **Pré-requisito (Fase 1):** unificar o modelo de progresso + Flask-Migrate + volume de uploads. Sem isso, qualquer feature nova herda os bugs.
2. **Fundação:** `Cohort` + `CohortEnrollment` + liberação por semana. Tudo o mais depende disso.
3. **Coração pedagógico:** diário de reflexão + painel do tutor por coorte + notas pastorais.
4. **Retenção:** lembretes por e-mail + prazos/status.
5. **Gestão:** relatórios de coorte + exportação + presença híbrida.
6. **Polimento:** certificado de programa + auto-matrícula + onboarding do programa.

---

## Apêndice — origem dos achados

Este documento consolida três auditorias independentes (backend Python, frontend SPA, infraestrutura/DevOps). Os três críticos de segurança (signup, SECRET_KEY, admin default) foram confirmados de forma independente pelas auditorias de backend **e** de infra. A configuração de CORS e o comportamento de `Flask-CORS` com curingas foram verificados empiricamente. Todos os `arquivo:linha` foram conferidos no código da branch `claude/zen-hopper-SeRac`.
