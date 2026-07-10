# DÉBITOS — Comportamentos legados registrados na caracterização (Fase 1)

Regra do playbook: testes de caracterização **documentam** o que o sistema faz
hoje; nada aqui foi "corrigido" durante a Fase 1. Cada item vira decisão
consciente (corrigir, conviver ou aposentar) — a maioria se resolve
naturalmente na reestruturação da Release 0.9/1.0.

| # | Débito | Evidência | Observação |
|---|---|---|---|
| 1 | **Três sistemas de nível concorrentes:** `calculate_level()` é linear hardcoded (100 pts/nível, teto 7) e ignora tanto a tabela `Level` (editável pelo admin em `/api/admin/levels` — edição sem efeito real) quanto os `points_*` do `PlatformConfig` (config de pontos do admin ignorada pelos `POINTS_PER_ACTION` hardcoded) | `tests/test_characterization_gamification.py::test_nivel_sobe_a_cada_100_pontos` · `routes/gamification.py:14-43` | Já apontado no ROADMAP.md #11; alinhar com GAM-01 na 0.9/1.0 |
| 2 | `points_in_level` cresce sem teto no nível 7 (2000 pts → "1400 no nível") | mesmo teste acima | Cosmético; UI mostra número estranho |
| 3 | **Dois sistemas de conquistas concorrentes:** `Badge/UserBadge` (legado) e `Achievement/UserAchievement` (Sprint 6.1) coexistem e são exibidos em lugares diferentes | `routes/gamification.py` (comentário na própria rota) | Consolidar em um só na 0.9/1.0 |
| 4 | **Progresso duplicado:** tabela `Progress` (por curso, legado) e `LessonProgress` (por aula) registram avanço em paralelo; dashboards misturam as fontes | `routes/progress.py` vs `routes/lessons.py` | PRD CUR-01 consolida em `progresso_licoes` |
| 5 | Quiz legado de curso (`POST /api/progress/quiz/<id>/submit`) **revela o gabarito completo mesmo errando** — diferente do quiz de aula, que oculta ao reprovar | `tests/test_characterization_progress_questions.py::test_quiz_legado_do_curso_corrigido_no_servidor` | Fluxo aparentemente não usado pelo SPA atual (que usa o quiz de aula); candidato a aposentadoria |
| 6 | Badge `servo_fiel` (streak 7 dias) é **inalcançável**: `_consecutive_days()` retorna sempre 0 | `routes/gamification.py:128-129` | Streaks server-side são GAM-02 (Release 1.0); badge exibido como 0/7 para sempre |
| 7 | Badge `corredor_incansavel` idem: progresso fixo `0/1` | `routes/gamification.py:106-107` | |
| 8 | Catálogo (`GET /api/courses`) é público e lista cursos `acesso='interno'` para anônimos (o detalhe bloqueia, a listagem não) | `tests/test_characterization_courses.py::test_anonimo_lista_publicados` | Vaza títulos/resumos de conteúdo interno; revisar na 0.9 junto com tenancy |
| 9 | Modelos usam emoji como default (`Course.icon='📖'`, `Trail.icon='🛤️'`) — contradiz a diretriz "zero emoji nativo" do design system | `models.py` | UX_ALUNO.md B2; trocar por código de ícone vetorial |
| 10 | Flask-Limiter com storage em memória (warning em todo boot) — funciona com `--workers 1`, quebra silenciosamente com réplicas (doc 02 prevê 2×) | warning no boot | Redis entra na Fase 4 do playbook; migrar o limiter junto |
| 11 | `/health` responde `db: connected` sem consultar o banco | `app.py` | Enganoso para monitoração |
| 12 | N+1 em serialização: `Course.to_dict` (category_rel), `Question.to_dict` (author), `TrailCourse.to_dict` (course) — listagens disparam 1 query por linha | revisão de código (jul/2026) | Irrelevante no volume atual; tratar nos repositórios da 0.9 |
| 13 | Schema nasce de `db.create_all()` — sem Alembic, sem migração versionada | `app.py:106` | Resolvido na Fase 2 do playbook (Alembic entra com tenancy) |
| 14 | `User.onboarding_completed` é flag GLOBAL: concluir o onboarding num tenant marca concluído em todos (a resposta `OnboardingAnswer` em si é por tenant desde o grupo 2) | `routes/trails.py::onboarding_status` | Resolver na Fase 4 junto com papéis por tenant (`tenant_users`) |
| 15 | `forgot-password` ainda tem um resíduo de timing side-channel: e-mail existente dispara envio SMTP **síncrono** antes de responder (e-mail inexistente responde na hora) — a diferença de status/corpo já foi corrigida (revisão de segurança, jul/2026), mas o tempo de resposta ainda varia | `routes/auth.py::forgot_password` | Mitigação completa exige enviar o e-mail num worker assíncrono (RQ — Release 1.0); fora do escopo da correção de enumeração |
