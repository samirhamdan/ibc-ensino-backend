# Personalização — plataforma (XR) e tenants

Levantamento de out/2026. Define o que cada camada pode personalizar, o que já existe e a ordem de implementação.

## Duas camadas

| Camada | Quem edita | Onde aparece |
|---|---|---|
| **Plataforma (XR Educação)** | Operador da XR | Marca padrão: login sem tenant, tenant sem marca própria, e-mails e páginas da plataforma |
| **Tenant (cliente)** | Admin do tenant | Tudo o que os alunos e tutores daquele cliente veem |

Regra: o tenant sobrescreve a plataforma. Campo vazio no tenant significa que vale o padrão da XR.

## Estado atual

### Pronto (Fase 1, out/2026)
- **Isolamento das configurações por tenant**: `platform_config` e `levels` ganharam `tenant_id`, com política RLS. Migração `0021`, teste `tests/isolation/test_config_isolation.py`.
  - Antes, o admin de um cliente alterava o nome, os contatos e a pontuação de todos os clientes.
  - Salvar os níveis apagava os níveis de todos os clientes.
- **Editor de marca** em Configurações → Marca: nome exibido, sigla, cor principal (com ajuste automático de contraste AA), logo, favicon, título e subtítulo do login. Tem pré-visualização ao vivo.
- **A marca é aplicada em toda a interface**: título e ícone da aba, login, barra superior e cor de botões, links e destaques.
  - Tenant com logo própria: o login usa a cor do tenant.
  - Tenant sem logo: aparece a marca da XR.
- **Contato no login** (WhatsApp) só aparece se o tenant configurar.
- APIs: `GET/PUT /api/admin/branding`, `POST /api/admin/branding/<logo|favicon>`, `GET /api/branding/<arquivo>`.

### Pronto (Fase 2 — painel do operador P0, out/2026)
- Papel global `operadores_plataforma` (migração `0022`). Concedido só por CLI (`make_operator.py`), nunca pelo painel de um tenant.
- **2FA TOTP obrigatório**, com QR code gerado no servidor. A sessão do painel expira após 30 min de inatividade.
- Suspender e reativar exigem um código novo do autenticador e um motivo.
- **Pulso**: saúde técnica (banco e migração), MRR estimado pela tabela de planos, clientes ativos e pagantes, usuários ativos em 7 dias e fila de ação (inadimplência, cliente sem usuários, cliente sem acesso há 21 dias).
- **Clientes**: lista com busca, filtro e paginação; perfil com métricas, administradores e histórico; criação de cliente (subdomínio validado, plano, admin com senha temporária, catálogo padrão de níveis, conquistas e categorias); edição de nome e plano; suspensão e reativação.
- **Auditoria**: toda ação do operador gera uma linha na mesma transação da mudança.
- Testes: `tests/test_operador.py` e `tests/isolation/test_operador_isolation.py`. Este último percorre todas as rotas `/api/ops` e exige 403 para admin de tenant e para anônimo.

**Pendente do operador**:
- Marca padrão da plataforma editável.
- Impersonação auditada.
- Tela de Receita (Asaas).
- Custos de IA.
- Plataforma (flags, jobs, erros).
- Exportação e exclusão LGPD.

### Lacunas encontradas
1. **Marca da plataforma fixa no código**: o logo, as cores e os textos da XR estão em `index.html` e `css/pages/brand-xr.css`. Falta um operador para editá-los sem deploy.
2. **Sem painel do operador**: criar tenant, definir subdomínio e plano e suspender exige acesso ao banco.
3. **Certificado**: layout único, e o código começa com `IBC-`. Faltam a assinatura, o texto e o logo de cada tenant.
4. **E-mails** (convite, recuperação de senha): remetente e visual fixos.
5. **Terminologia fixa**: cada cliente fala de um jeito ("Curso"/"Disciplina", "Trilha"/"Jornada", "Aluno"/"Colaborador"/"Membro").
6. **Módulos sempre ligados**: gamificação, ranking, perguntas ao tutor, trilhas e cadastro aberto ("Criar conta grátis") não podem ser desligados por tenant.
7. **Domínio próprio** (`ead.cliente.com.br`): depende de DNS wildcard e on-demand TLS no Caddy.
8. **Área do aluno**: modo claro/escuro padrão e imagem de fundo do login não são configuráveis.
9. **Três sistemas de nível concorrentes** (DEBITOS #1): os níveis editados no admin ainda não alteram o cálculo real.

## Roadmap de personalização

| Fase | Entrega | Lacunas |
|---|---|---|
| **2. Painel do operador** | ~~Papel de operador, CRUD de tenants, auditoria~~ (pronto). Falta: marca padrão da plataforma editável, visão de cobrança, impersonação | 1, 2 |
| **3. Experiência do tenant** | Módulos liga/desliga, cadastro aberto ou só por convite, terminologia, tema padrão claro/escuro, imagem de fundo do login | 5, 6, 8 |
| **4. Documentos e comunicação** | Certificado por tenant (logo, assinatura, texto, prefixo do código), e-mails com remetente e marca do tenant | 3, 4 |
| **5. Domínio próprio** | Domínio customizado por tenant com HTTPS automático | 7 |
| **6. Gamificação configurável** | Unificar os sistemas de nível; pontos e níveis do admin passam a valer | 9 |

## Levantamento do produto (o que mais precisa ser feito)

Além da personalização, por ordem de impacto:
1. **Tutor com IA**: o diferencial do produto, que ainda não existe. Deve passar por `ai/providers/`, com RAG sobre os materiais do curso.
2. **Fila de jobs (RQ + Redis)**: e-mail e Asaas são chamados de forma síncrona na própria requisição.
3. **Unificar o progresso**: `Progress` e `LessonProgress` (DEBITOS #4).
4. **Ativar o RLS em produção**: hoje o usuário do banco tem BYPASSRLS (`docs/RUNBOOK-RLS.md`).
5. **Performance mobile**: Lighthouse 62–64, meta ≥85. Falta bundle de CSS e `defer` nos scripts.
6. **Onboarding do admin** (ONB-03): checklist marca → curso → convidar → publicar.
