/* Painel do operador da plataforma XR (UX_OPERADOR_SAAS P0).
   Usa helpers globais do index.html: api, icon, escapeHtml, showToast, showModal, closeModal. */
(function () {
  'use strict';

  const esc = (v) => escapeHtml(v == null ? '' : String(v));
  const brl = (v) => (v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  const data = (iso) => (iso ? new Date(iso + (iso.endsWith('Z') ? '' : 'Z')).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : '—');
  const STATUS = { active: ['Ativo', 'ok'], read_only: ['Somente leitura', 'warn'], suspended: ['Suspenso', 'bad'] };
  const BILLING = { ativo: ['Em dia', 'ok'], leitura: ['Inadimplente (leitura)', 'warn'], suspenso: ['Inadimplente (suspenso)', 'bad'] };
  let aba = 'pulso';

  function main() { return document.getElementById('main-content'); }
  function selo([txt, tipo]) { return `<span class="ops-selo ops-selo-${tipo}">${esc(txt)}</span>`; }

  window.detectarOperador = async function () {
    const nav = document.getElementById('nav-ops');
    if (!nav) return;
    const ok = typeof currentUser !== 'undefined' && !!(currentUser && currentUser.operador);
    nav.style.display = ok ? 'flex' : 'none';
    if (ok) document.getElementById('admin-nav-section').style.display = 'block';
  };

  window.sairModoOperador = function () {
    document.body.classList.remove('modo-operador');
    const nav = document.getElementById('nav-ops');
    if (nav) nav.classList.remove('active');
  };

  window.abrirPainelOperador = async function (destino) {
    document.querySelectorAll('.course-item[id^=nav-admin]').forEach((x) => x.classList.remove('active'));
    document.getElementById('nav-ops').classList.add('active');
    document.body.classList.add('modo-operador');
    if (destino) aba = destino;
    const res = await fetch('/api/ops/me', { credentials: 'same-origin' });
    if (!res.ok) { main().innerHTML = '<p>Acesso restrito ao operador da plataforma.</p>'; return; }
    const me = await res.json();
    if (!me['2fa_verificado']) return renderDoisFatores(me);
    renderShell();
  };

  // ── 2FA ────────────────────────────────────────────────────────────────
  async function renderDoisFatores(me) {
    let setup = '';
    if (!me['2fa_configurado']) {
      const r = await api('POST', '/ops/2fa/configurar');
      const d = await r.json();
      setup = `
        <ol class="ops-2fa-passos">
          <li>Instale um app autenticador (Google Authenticator, Authy ou Microsoft Authenticator).</li>
          <li>Escaneie o QR code abaixo ou digite a chave manualmente.</li>
          <li>Digite o código de 6 dígitos que aparece no app.</li>
        </ol>
        <img class="ops-2fa-qr" src="${esc(d.qr_svg)}" alt="QR code para o app autenticador" width="180" height="180">
        <p class="ops-2fa-chave">Chave: <code>${esc(d.segredo)}</code></p>`;
    }
    main().innerHTML = `
      <div class="ops-2fa">
        <div class="ops-badge">${icon('key', '14')} OPERADOR</div>
        <h1 class="text-h3">Verificação em duas etapas</h1>
        <p class="text-muted">O painel da plataforma exige um código do seu app autenticador.${me['2fa_configurado'] ? '' : ' Configure agora — leva 1 minuto.'}</p>
        ${setup}
        <form id="ops-2fa-form" class="ops-2fa-form">
          <input id="ops-2fa-codigo" class="form-control" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="000000" required>
          <button class="btn btn-primary" type="submit">Verificar</button>
        </form>
      </div>`;
    document.getElementById('ops-2fa-codigo').focus();
    document.getElementById('ops-2fa-form').onsubmit = async (e) => {
      e.preventDefault();
      const r = await api('POST', '/ops/2fa/verificar', { codigo: document.getElementById('ops-2fa-codigo').value });
      if (r.ok) { showToast('Verificado.', 'success'); renderShell(); }
      else { const d = await r.json().catch(() => ({})); showToast(d.error || 'Código inválido.', 'error'); }
    };
  }

  async function opsApi(method, path, body) {
    const r = await api(method, '/ops' + path, body);
    if (r.status === 428) { abrirPainelOperador(); throw new Error('2fa'); }
    return r;
  }

  // ── Estrutura ──────────────────────────────────────────────────────────
  function renderShell() {
    const abas = [['pulso', 'bar-chart', 'Pulso'], ['tenants', 'users', 'Clientes'], ['auditoria', 'document-text', 'Auditoria']];
    main().innerHTML = `
      <div class="ops-header">
        <div class="ops-badge">${icon('key', '14')} OPERADOR DA PLATAFORMA</div>
        <nav class="ops-abas">${abas.map(([id, ic, nome]) =>
          `<button class="ops-aba${aba === id ? ' active' : ''}" data-aba="${id}">${icon(ic, '16')} ${nome}</button>`).join('')}</nav>
      </div>
      <div id="ops-corpo"><p class="text-muted">Carregando…</p></div>`;
    main().querySelectorAll('.ops-aba').forEach((b) => (b.onclick = () => { aba = b.dataset.aba; renderShell(); }));
    ({ pulso: renderPulso, tenants: renderTenants, auditoria: renderAuditoria })[aba]();
  }
  const corpo = () => document.getElementById('ops-corpo');

  // ── Pulso ──────────────────────────────────────────────────────────────
  async function renderPulso() {
    const d = await (await opsApi('GET', '/pulso')).json();
    const n = d.negocio, t = d.tecnico;
    const kpis = [
      ['MRR estimado', brl(n.mrr), 'pela tabela de planos'],
      ['Clientes ativos', `${n.tenants_ativos} / ${n.tenants_total}`, `${n.tenants_pagantes} pagantes`],
      ['Usuários ativos (7d)', n.usuarios_ativos_7d, 'em todos os clientes'],
      ['Novos clientes (30d)', n.novos_tenants_30d, ''],
    ];
    corpo().innerHTML = `
      <div class="ops-grid-2">
        <section class="ops-card">
          <h2 class="ops-card-titulo">Saúde técnica</h2>
          <div class="ops-semaforo ops-semaforo-${t.semaforo}"><span></span>${t.semaforo === 'verde' ? 'Operando normalmente' : 'Banco lento'}</div>
          <dl class="ops-dl">
            <dt>Banco de dados</dt><dd>${t.db_ok ? 'Conectado' : 'Fora do ar'} · ${t.db_latencia_ms} ms</dd>
            <dt>Migração do banco</dt><dd><code>${esc(t.migracao || '—')}</code></dd>
          </dl>
        </section>
        <section class="ops-card">
          <h2 class="ops-card-titulo">Negócio</h2>
          <div class="ops-kpis">${kpis.map(([l, v, s]) => `<div class="ops-kpi"><div class="ops-kpi-valor">${esc(v)}</div><div class="ops-kpi-label">${l}</div>${s ? `<div class="ops-kpi-sub">${s}</div>` : ''}</div>`).join('')}</div>
        </section>
      </div>
      <section class="ops-card">
        <h2 class="ops-card-titulo">Precisa de ação</h2>
        ${d.fila.length ? `<ul class="ops-fila">${d.fila.map((f) => `
          <li class="ops-fila-item" data-nivel="${f.nivel}"><span>${esc(f.msg)}</span>
            <button class="btn-link" data-tenant="${f.tenant_id}">Ver cliente</button></li>`).join('')}</ul>`
          : '<p class="ops-vazio">Nenhuma ação pendente.</p>'}
      </section>`;
    corpo().querySelectorAll('[data-tenant]').forEach((b) => (b.onclick = () => renderPerfil(b.dataset.tenant)));
  }

  // ── Tenants ────────────────────────────────────────────────────────────
  let filtro = { busca: '', status: '', pagina: 1 };
  async function renderTenants() {
    const qs = new URLSearchParams(filtro).toString();
    const d = await (await opsApi('GET', '/tenants?' + qs)).json();
    const paginas = Math.max(1, Math.ceil(d.total / d.por_pagina));
    corpo().innerHTML = `
      <div class="ops-toolbar">
        <input id="ops-busca" class="form-control" placeholder="Buscar por nome ou subdomínio" value="${esc(filtro.busca)}">
        <select id="ops-status" class="form-control">
          <option value="">Todos os status</option>
          ${Object.entries(STATUS).map(([k, [n]]) => `<option value="${k}"${filtro.status === k ? ' selected' : ''}>${n}</option>`).join('')}
        </select>
        <button class="btn btn-primary" id="ops-novo">${icon('plus', '16')} Novo cliente</button>
      </div>
      <div class="ops-tabela-wrap"><table class="admin-users-tbl ops-tabela">
        <thead><tr><th>Cliente</th><th>Plano</th><th>Status</th><th>Pagamento</th><th>Usuários</th><th>Ativos 7d</th><th>Cursos</th><th>Último acesso</th><th>MRR</th></tr></thead>
        <tbody>${d.tenants.map((t) => `
          <tr class="ops-linha" data-id="${t.id}">
            <td><strong>${esc(t.nome)}</strong><div class="text-muted ops-slug">${esc(t.subdominio)}</div></td>
            <td>${esc(t.plano_nome)}</td><td>${selo(STATUS[t.status] || [t.status, 'warn'])}</td>
            <td>${selo(BILLING[t.billing_status] || [t.billing_status, 'warn'])}</td>
            <td>${t.usuarios}</td><td>${t.ativos_7d}</td><td>${t.cursos}</td>
            <td>${data(t.ultimo_acesso)}</td><td>${brl(t.mrr)}</td>
          </tr>`).join('') || '<tr><td colspan="9" class="ops-vazio">Nenhum cliente encontrado.</td></tr>'}</tbody>
      </table></div>
      <div class="ops-paginacao">${d.total} cliente(s) · página ${d.pagina} de ${paginas}
        <button class="btn btn-sm btn-outline" id="ops-ant" ${d.pagina <= 1 ? 'disabled' : ''}>Anterior</button>
        <button class="btn btn-sm btn-outline" id="ops-prox" ${d.pagina >= paginas ? 'disabled' : ''}>Próxima</button></div>`;
    let t;
    document.getElementById('ops-busca').oninput = (e) => { clearTimeout(t); t = setTimeout(() => { filtro = { ...filtro, busca: e.target.value, pagina: 1 }; renderTenants(); }, 300); };
    document.getElementById('ops-status').onchange = (e) => { filtro = { ...filtro, status: e.target.value, pagina: 1 }; renderTenants(); };
    document.getElementById('ops-ant').onclick = () => { filtro.pagina--; renderTenants(); };
    document.getElementById('ops-prox').onclick = () => { filtro.pagina++; renderTenants(); };
    document.getElementById('ops-novo').onclick = abrirNovoTenant;
    corpo().querySelectorAll('.ops-linha').forEach((tr) => (tr.onclick = () => renderPerfil(tr.dataset.id)));
  }

  async function abrirNovoTenant() {
    const planos = await (await opsApi('GET', '/planos')).json();
    showModal('Novo cliente', `
      <div class="form-group"><label class="form-label">Nome do cliente</label><input id="nt-nome" class="form-control" maxlength="200" placeholder="Ex.: Escola Bíblica Central"></div>
      <div class="form-group"><label class="form-label">Subdomínio</label>
        <div class="ops-subdominio"><input id="nt-slug" class="form-control" maxlength="30" placeholder="escola-central"><span>.xreducacao</span></div>
        <span class="form-hint" id="nt-slug-msg">Letras minúsculas, números e hífen.</span></div>
      <div class="form-group"><label class="form-label">Plano</label><select id="nt-plano" class="form-control">
        ${planos.map((p) => `<option value="${p.id}">${esc(p.nome)}${p.preco ? ' — ' + brl(p.preco) + '/mês' : ' — sob consulta'}</option>`).join('')}</select></div>
      <div class="form-row">
        <div class="form-group"><label class="form-label">Nome do administrador</label><input id="nt-admin-nome" class="form-control"></div>
        <div class="form-group"><label class="form-label">E-mail do administrador</label><input id="nt-admin-email" type="email" class="form-control"></div>
      </div>
      <p class="form-hint">Se o e-mail ainda não tiver conta, criamos uma com senha temporária (mostrada uma única vez).</p>`,
      `<button class="btn" onclick="closeModal()">Cancelar</button><button class="btn btn-primary" id="nt-criar">Criar cliente</button>`);
    const nome = document.getElementById('nt-nome'), slug = document.getElementById('nt-slug'), msg = document.getElementById('nt-slug-msg');
    let editado = false, timer;
    const checar = () => { clearTimeout(timer); timer = setTimeout(async () => {
      if (!slug.value) return;
      const d = await (await opsApi('GET', '/tenants/disponibilidade?slug=' + encodeURIComponent(slug.value))).json();
      msg.textContent = d.disponivel ? 'Disponível.' : d.motivo; msg.className = 'form-hint ' + (d.disponivel ? 'ops-ok' : 'ops-erro');
    }, 300); };
    nome.oninput = () => { if (!editado) { slug.value = nome.value.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 30); checar(); } };
    slug.oninput = () => { editado = true; checar(); };
    document.getElementById('nt-criar').onclick = async () => {
      const r = await opsApi('POST', '/tenants', { nome: nome.value, slug: slug.value, plano: document.getElementById('nt-plano').value,
        admin_nome: document.getElementById('nt-admin-nome').value, admin_email: document.getElementById('nt-admin-email').value });
      const d = await r.json();
      if (!r.ok) { showToast(d.error || 'Erro ao criar cliente.', 'error'); return; }
      closeModal();
      showModal('Cliente criado', `
        <p><strong>${esc(d.tenant.nome)}</strong> está pronto.</p>
        <p>Administrador: <code>${esc(d.admin_email)}</code></p>
        ${d.senha_temporaria ? `<p>Senha temporária: <code class="ops-senha">${esc(d.senha_temporaria)}</code></p>
          <p class="form-hint">Copie agora — ela não será mostrada de novo. Peça para o administrador trocar no primeiro acesso.</p>`
          : '<p class="form-hint">O e-mail já tinha conta: o acesso usa a senha atual dessa pessoa.</p>'}`,
        `<button class="btn btn-primary" onclick="closeModal()">Fechar</button>`);
      renderPerfil(d.tenant.id);
    };
  }

  async function renderPerfil(id) {
    aba = 'tenants';
    document.querySelectorAll('.ops-aba').forEach((b) => b.classList.toggle('active', b.dataset.aba === 'tenants'));
    const r = await opsApi('GET', '/tenants/' + id);
    if (!r.ok) { showToast('Cliente não encontrado.', 'error'); return; }
    const t = await r.json();
    const planos = await (await opsApi('GET', '/planos')).json();
    const cor = (t.tema && t.tema.primary) || '';
    corpo().innerHTML = `
      <button class="btn-link" id="ops-voltar">${icon('chevron-left', '14')} Todos os clientes</button>
      <div class="ops-perfil-topo">
        ${t.tema && t.tema.logo ? `<img class="ops-perfil-logo" src="${esc(t.tema.logo)}" alt="">` : `<div class="ops-perfil-inicial" style="${cor ? 'background:' + esc(cor) : ''}">${esc(t.nome.charAt(0))}</div>`}
        <div><h2 class="text-h3">${esc(t.nome)}</h2><div class="text-muted">${esc(t.subdominio)} · criado em ${data(t.criado_em)}</div></div>
        <div class="ops-perfil-selos">${selo(STATUS[t.status] || [t.status, 'warn'])} ${selo(BILLING[t.billing_status] || [t.billing_status, 'warn'])}</div>
      </div>
      <div class="ops-kpis ops-kpis-linha">
        ${[['Usuários', t.usuarios], ['Alunos', t.alunos], ['Ativos 7d', t.ativos_7d], ['Cursos', t.cursos], ['MRR', brl(t.mrr)], ['Último acesso', data(t.ultimo_acesso)]]
          .map(([l, v]) => `<div class="ops-kpi"><div class="ops-kpi-valor">${esc(v)}</div><div class="ops-kpi-label">${l}</div></div>`).join('')}
      </div>
      <div class="ops-grid-2">
        <section class="ops-card">
          <h3 class="ops-card-titulo">Dados e plano</h3>
          <div class="form-group"><label class="form-label">Nome</label><input id="pf-nome" class="form-control" value="${esc(t.nome)}"></div>
          <div class="form-group"><label class="form-label">Plano</label><select id="pf-plano" class="form-control">
            ${planos.map((p) => `<option value="${p.id}"${p.id === t.plano ? ' selected' : ''}>${esc(p.nome)}</option>`).join('')}</select></div>
          <button class="btn btn-primary" id="pf-salvar">Salvar</button>
          <h3 class="ops-card-titulo ops-mt">Ciclo de vida</h3>
          ${t.status === 'suspended'
            ? `<p class="text-muted">Suspenso: ninguém deste cliente consegue entrar.</p><button class="btn btn-primary" id="pf-status" data-status="active">Reativar cliente</button>`
            : `<p class="text-muted">Suspender bloqueia o acesso de todos os usuários deste cliente. Os dados são mantidos e você pode reativar depois.</p><button class="btn btn-danger" id="pf-status" data-status="suspended">Suspender cliente</button>`}
        </section>
        <section class="ops-card">
          <h3 class="ops-card-titulo">Administradores</h3>
          ${t.admins.length ? `<ul class="ops-lista">${t.admins.map((a) => `<li><strong>${esc(a.nome)}</strong> <span class="text-muted">${esc(a.email)}</span><div class="text-muted ops-slug">Último acesso: ${data(a.ultimo_acesso)}</div></li>`).join('')}</ul>` : '<p class="ops-vazio">Nenhum administrador.</p>'}
          <h3 class="ops-card-titulo ops-mt">Histórico</h3>
          ${t.eventos.length ? `<ul class="ops-lista ops-eventos">${t.eventos.map((e) => `<li><code>${esc(e.acao)}</code> <span class="text-muted">${data(e.criado_em)}</span>${e.payload && e.payload.motivo ? `<div class="text-muted">Motivo: ${esc(e.payload.motivo)}</div>` : ''}</li>`).join('')}</ul>` : '<p class="ops-vazio">Sem eventos registrados.</p>'}
        </section>
      </div>`;
    document.getElementById('ops-voltar').onclick = renderTenants;
    document.getElementById('pf-salvar').onclick = async () => {
      const r2 = await opsApi('PATCH', '/tenants/' + id, { nome: document.getElementById('pf-nome').value, plano: document.getElementById('pf-plano').value });
      const d = await r2.json();
      if (r2.ok) { showToast('Cliente atualizado.', 'success'); renderPerfil(id); } else showToast(d.error || 'Erro ao salvar.', 'error');
    };
    document.getElementById('pf-status').onclick = (e) => confirmarStatus(t, e.currentTarget.dataset.status);
  }

  function confirmarStatus(t, status) {
    const suspender = status === 'suspended';
    showModal(suspender ? `Suspender ${esc(t.nome)}?` : `Reativar ${esc(t.nome)}?`, `
      <p>${suspender ? 'Todos os usuários deste cliente perdem o acesso imediatamente. Nenhum dado é apagado.' : 'Os usuários deste cliente voltam a ter acesso.'}</p>
      ${suspender ? '<div class="form-group"><label class="form-label">Motivo (fica na auditoria)</label><input id="st-motivo" class="form-control" maxlength="200"></div>' : ''}
      <div class="form-group"><label class="form-label">Código do app autenticador</label><input id="st-codigo" class="form-control" inputmode="numeric" maxlength="6" placeholder="000000"></div>`,
      `<button class="btn" onclick="closeModal()">Cancelar</button><button class="btn ${suspender ? 'btn-danger' : 'btn-primary'}" id="st-ok">${suspender ? 'Suspender' : 'Reativar'}</button>`);
    document.getElementById('st-ok').onclick = async () => {
      const motivo = suspender ? document.getElementById('st-motivo').value : '';
      const r = await opsApi('POST', `/tenants/${t.id}/status`, { status, motivo, codigo: document.getElementById('st-codigo').value });
      const d = await r.json();
      if (!r.ok) { showToast(d.error || 'Não foi possível alterar.', 'error'); return; }
      closeModal(); showToast(suspender ? 'Cliente suspenso.' : 'Cliente reativado.', 'success'); renderPerfil(t.id);
    };
  }

  // ── Auditoria ──────────────────────────────────────────────────────────
  let paginaAud = 1;
  async function renderAuditoria() {
    const d = await (await opsApi('GET', '/auditoria?pagina=' + paginaAud)).json();
    corpo().innerHTML = `
      <div class="ops-tabela-wrap"><table class="admin-users-tbl ops-tabela">
        <thead><tr><th>Quando</th><th>Operador</th><th>Ação</th><th>Cliente</th><th>Detalhes</th></tr></thead>
        <tbody>${d.eventos.map((e) => `<tr><td>${data(e.criado_em)}</td><td>${esc(e.operador || '—')}</td><td><code>${esc(e.acao)}</code></td>
          <td>${esc(e.tenant_nome || '')}</td><td class="ops-detalhes">${esc(Object.entries(e.payload || {}).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(' → ') : v}`).join(' · '))}</td></tr>`).join('')
          || '<tr><td colspan="5" class="ops-vazio">Nenhuma ação registrada ainda.</td></tr>'}</tbody>
      </table></div>
      <div class="ops-paginacao">${d.total} registro(s)
        <button class="btn btn-sm btn-outline" id="aud-ant" ${paginaAud <= 1 ? 'disabled' : ''}>Anterior</button>
        <button class="btn btn-sm btn-outline" id="aud-prox" ${paginaAud * 50 >= d.total ? 'disabled' : ''}>Próxima</button></div>`;
    document.getElementById('aud-ant').onclick = () => { paginaAud--; renderAuditoria(); };
    document.getElementById('aud-prox').onclick = () => { paginaAud++; renderAuditoria(); };
  }
})();
