/**
 * Dashboard Lead Time · Antilhas v2
 *
 * Lê o dados.json e renderiza:
 * - 3 cards de resumo (atrasados / semana / mês)
 * - Filtros (busca, status, responsável, cliente)
 * - Tabela de pedidos
 * - Drawer de detalhe com timeline horizontal dos 5 marcos
 */

// ============================================================
// CONFIGURAÇÃO
// ============================================================
const CONFIG = {
  // dados.json gerado pelo parser no GitHub
  URL_DADOS: 'https://raw.githubusercontent.com/mnluizasantos-spec/lead-timev2/main/dados.json',
};

const STATUS_LABEL = {
  aguardando_fert: 'Aguardando FERT',
  aguardando_op:   'Aguardando OP',
  em_producao:     'Em produção',
  concluido:       'Concluído',
  cancelado:       'Cancelado',
};

const MARCOS_ORDEM = [
  { key: 'pedido_fechado', label: 'Pedido fechado',  papel: 'Comercial' },
  { key: 'fert_criado',    label: 'FERT criado',     papel: 'Engenharia' },
  { key: 'op_liberada',    label: 'OP liberada',     papel: 'Engenharia' },
  { key: 'producao',       label: 'Produção',        papel: 'PCP/Fábrica' },
  { key: 'data_vitrine',   label: 'Data vitrine',    papel: 'Cliente' },
];

// ============================================================
// ESTADO
// ============================================================
const state = {
  pedidos: [],         // todos os pedidos do JSON
  filtros: {
    busca: '',
    status: '',
    responsavel: '',
    cliente: '',
  },
  pedidoAberto: null,  // pedido sendo exibido no drawer
};

// ============================================================
// UTILS
// ============================================================
function $(sel) { return document.querySelector(sel); }
function $$(sel) { return Array.from(document.querySelectorAll(sel)); }

function fmtData(iso) {
  if (!iso) return '—';
  const d = new Date(iso + 'T00:00:00');
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('pt-BR');
}

function diasEntre(d1, d2) {
  if (!d1 || !d2) return null;
  const a = new Date(d1 + 'T00:00:00');
  const b = new Date(d2 + 'T00:00:00');
  return Math.round((b - a) / 86400000);
}

function hoje() {
  return new Date().toISOString().slice(0, 10);
}

function daquiNDias(n) {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

// ============================================================
// CARREGAR DADOS
// ============================================================
async function carregarDados() {
  // Tela de loading
  $('#tabela-pedidos-body').innerHTML = `
    <tr><td colspan="7" class="vazio">
      Carregando dados...
    </td></tr>`;
  $('#lista-meta').textContent = 'Carregando...';

  try {
    // Cache-burst: ?t=timestamp pra forçar fetch fresh
    const url = `${CONFIG.URL_DADOS}?t=${Date.now()}`;
    const resp = await fetch(url, { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const dados = await resp.json();
    state.pedidos = Array.isArray(dados) ? dados : [];
    renderizarTudo();
  } catch (e) {
    console.error('Erro ao carregar dados:', e);
    $('#tabela-pedidos-body').innerHTML = `
      <tr><td colspan="7" class="vazio">
        Erro ao carregar dados.<br>
        <small>${e.message}</small><br>
        <button class="btn-ghost" onclick="carregarDados()" style="margin-top:12px">Tentar de novo</button>
      </td></tr>`;
    $('#lista-meta').textContent = 'Erro';
  }
}

// ============================================================
// CÁLCULOS DE NEGÓCIO
// ============================================================
function calcularAtrasados() {
  /**
   * Pedido está atrasado se algum marco tem data prevista no passado
   * e o marco ainda não foi cumprido (real = null).
   */
  const ho = hoje();
  const atrasados = [];

  for (const p of state.pedidos) {
    if (p.status === 'concluido' || p.status === 'cancelado') continue;
    if (p.oculto) continue;

    const marcos = p.marcos || {};
    let responsavelAtraso = null;

    // FERT atrasado?
    if (marcos.fert_criado?.previsto && marcos.fert_criado.previsto < ho
        && !marcos.fert_criado.real) {
      responsavelAtraso = 'Engenharia';
    }
    // OP atrasada?
    if (marcos.op_liberada?.previsto && marcos.op_liberada.previsto < ho
        && !marcos.op_liberada.real) {
      responsavelAtraso = 'Engenharia';
    }
    // Produção atrasada?
    if (marcos.producao?.previsto && marcos.producao.previsto < ho
        && !marcos.producao.real) {
      responsavelAtraso = 'PCP/Fábrica';
    }

    if (responsavelAtraso) {
      atrasados.push({ pedido: p, responsavel: responsavelAtraso });
    }
  }

  return atrasados;
}

function calcularProduzSemana() {
  /**
   * Pedidos com data de produção prevista nos próximos 5 dias úteis (~7 corridos)
   */
  const ho = hoje();
  const limite = daquiNDias(7);

  return state.pedidos.filter(p => {
    if (p.status === 'concluido' || p.status === 'cancelado') return false;
    if (p.oculto) return false;
    const prev = p.marcos?.producao?.previsto;
    if (!prev) return false;
    return prev >= ho && prev <= limite;
  });
}

function calcularFechamentoMes() {
  /**
   * Resumo do mês corrente (lead time médio + aderência ao plano).
   */
  const mesAtual = hoje().slice(0, 7); // YYYY-MM
  const doMes = state.pedidos.filter(p => {
    const ped = p.marcos?.pedido_fechado?.real;
    return ped && ped.slice(0, 7) === mesAtual;
  });

  // Lead time médio = média dos lead times REAIS conhecidos
  const leadTimesReais = [];
  for (const p of doMes) {
    const lt = p.lead_times || {};
    for (const k of Object.keys(lt)) {
      const real = lt[k]?.real;
      if (real != null && real >= 0) leadTimesReais.push(real);
    }
  }
  const ltMedio = leadTimesReais.length
    ? Math.round(leadTimesReais.reduce((s, n) => s + n, 0) / leadTimesReais.length)
    : null;

  // Aderência: % de lead times realizados com desvio == 0 ou negativo
  const comDesvio = [];
  for (const p of doMes) {
    const lt = p.lead_times || {};
    for (const k of Object.keys(lt)) {
      const d = lt[k]?.desvio;
      if (d != null) comDesvio.push(d);
    }
  }
  const noPrazo = comDesvio.filter(d => d <= 0).length;
  const aderencia = comDesvio.length
    ? Math.round((noPrazo / comDesvio.length) * 100)
    : null;

  return { ltMedio, aderencia, totalPedidos: doMes.length };
}

// ============================================================
// RENDERIZAÇÃO — CARDS DE RESUMO
// ============================================================
function renderizarCards() {
  // Card 1: Atrasados
  const atrasados = calcularAtrasados();
  $('#card-atrasados-total').textContent = atrasados.length;

  const breakdown = atrasados.reduce((acc, a) => {
    acc[a.responsavel] = (acc[a.responsavel] || 0) + 1;
    return acc;
  }, {});
  const breakdownHtml = Object.entries(breakdown)
    .map(([r, n]) => `<span class="chip">${n} ${r}</span>`)
    .join('') || '<span class="chip">Nenhum atraso</span>';
  $('#card-atrasados-breakdown').innerHTML = breakdownHtml;

  // Card 2: Produz semana
  const semana = calcularProduzSemana();
  $('#card-semana-total').textContent = semana.length;
  $('#card-semana-breakdown').innerHTML = semana.length
    ? `<span class="chip">próximos 7 dias</span>`
    : '<span class="chip">Nenhum agendado</span>';

  // Card 3: Fechamento mês
  const fm = calcularFechamentoMes();
  $('#card-mes-leadtime').textContent = fm.ltMedio !== null ? `${fm.ltMedio}d` : '—';
  $('#card-mes-aderencia').textContent = fm.aderencia !== null ? `${fm.aderencia}%` : '—';
}

// ============================================================
// RENDERIZAÇÃO — LEAD TIME POR ETAPA
// ============================================================
const ETAPAS = [
  { key: '__comercial_aderencia', label: 'Comercial (envio)',  cor: 'var(--azul-900)', tipo: 'aderencia' },
  { key: 'pedido_para_fert',  label: 'Pedido → FERT',    cor: 'var(--azul-700)' },
  { key: 'fert_para_op',      label: 'FERT → OP',        cor: 'var(--azul-500)' },
  { key: 'op_para_producao',  label: 'OP → Produção',    cor: 'var(--laranja-500)' },
  { key: 'producao_para_vit', label: 'Produção → Vitrine', cor: 'var(--verde-500)' },
];

function calcularMediasEtapas() {
  /**
   * Pra cada etapa, calcula:
   *  - real médio (média dos lead_times.real dos pedidos do mês)
   *  - plano médio (média dos previsto)
   *  - delta = real - plano
   *
   * O card especial 'aderencia' (Comercial — envio) usa um cálculo diferente:
   *  - real = média de "dias de atraso" do envio do pedido
   *           (data_real_pedido_fechado - data_prevista_pedido_fechado)
   *  - plano = 0 (ideal é enviar no dia previsto)
   *  - delta = real (porque plano=0)
   */
  const mesAtual = hoje().slice(0, 7);
  const doMes = state.pedidos.filter(p => {
    const ped = p.marcos?.pedido_fechado?.real;
    return ped && ped.slice(0, 7) === mesAtual && !p.oculto;
  });

  const resultados = ETAPAS.map(etapa => {
    // Card especial: pontualidade do comercial
    if (etapa.tipo === 'aderencia') {
      const desvios = [];
      for (const p of doMes) {
        const prev = p.marcos?.pedido_fechado?.previsto;
        const real = p.marcos?.pedido_fechado?.real;
        if (prev && real) {
          const d = diasEntre(prev, real);
          if (d != null) desvios.push(d);
        }
      }
      const real = desvios.length
        ? desvios.reduce((s, n) => s + n, 0) / desvios.length
        : null;
      return {
        ...etapa,
        real,              // dias médios de atraso (pode ser negativo se adiantou)
        plano: 0,          // ideal é zero
        delta: real,       // como plano=0, delta=real
        amostra: desvios.length,
      };
    }

    // Cards normais (Pedido→FERT, FERT→OP, etc.)
    const reais = [];
    const planos = [];
    for (const p of doMes) {
      const lt = p.lead_times?.[etapa.key];
      if (lt?.real != null) reais.push(lt.real);
      if (lt?.previsto != null) planos.push(lt.previsto);
    }
    const real = reais.length ? reais.reduce((s, n) => s + n, 0) / reais.length : null;
    const plano = planos.length ? planos.reduce((s, n) => s + n, 0) / planos.length : null;
    const delta = (real != null && plano != null) ? real - plano : null;
    return { ...etapa, real, plano, delta, amostra: reais.length };
  });

  // Identifica gargalo: SÓ entre cards de lead time (não conta o card de aderência)
  const comReal = resultados.filter(r => r.real != null && r.tipo !== 'aderencia');
  let gargalo = null;
  if (comReal.length > 0) {
    gargalo = comReal.reduce((max, r) => r.real > max.real ? r : max, comReal[0]).key;
  }
  return { resultados, gargalo };
}

function renderizarEtapas() {
  const { resultados, gargalo } = calcularMediasEtapas();

  // Pra largura da barra: maior valor entre real e plano de TODAS as etapas
  // (sem contar a aderência, que usa escala diferente)
  const valoresLeadtime = resultados
    .filter(r => r.tipo !== 'aderencia')
    .flatMap(r => [r.real, r.plano])
    .filter(v => v != null);
  const maxValor = valoresLeadtime.length ? Math.max(...valoresLeadtime, 1) : 1;

  $('#etapas-grid').innerHTML = resultados.map(r => {
    const isGargalo = gargalo === r.key;

    // Dias formatados com vírgula (padrão BR)
    const formatDias = v => v != null ? v.toFixed(1).replace('.', ',') : '—';

    // ============= CARD ESPECIAL: aderência do comercial =============
    if (r.tipo === 'aderencia') {
      const sem = r.real == null;
      let valorDisplay, deltaHtml, larguraBarra, corBarra;

      if (sem) {
        valorDisplay = '—';
        deltaHtml = '<span class="delta zero">sem cronograma</span>';
        larguraBarra = 0;
        corBarra = 'var(--cinza-300)';
      } else if (r.real <= 0) {
        // No prazo ou adiantado
        valorDisplay = r.real < -0.05
          ? `<span style="color:var(--verde-700)">${formatDias(Math.abs(r.real))}</span>`
          : '<span style="color:var(--verde-700)">0,0</span>';
        deltaHtml = r.real < -0.05
          ? `<span class="delta pos">↓ adiantou ${formatDias(Math.abs(r.real))}d</span>`
          : `<span class="delta pos">no dia</span>`;
        larguraBarra = 100;
        corBarra = 'var(--verde-500)';
      } else {
        // Atrasou
        valorDisplay = `<span style="color:var(--vermelho-700)">+${formatDias(r.real)}</span>`;
        deltaHtml = `<span class="delta neg">↑ atrasou ${formatDias(r.real)}d</span>`;
        // Barra: máx 7 dias = 100%
        larguraBarra = Math.min(100, (r.real / 7) * 100);
        corBarra = 'var(--vermelho-500)';
      }

      return `
        <div class="etapa-card">
          <div class="top-stripe" style="background:${r.cor}"></div>
          <div class="etapa-head">
            <span class="etapa-nome">${r.label}</span>
          </div>
          <div class="etapa-dias">${valorDisplay}<span class="unit">d</span></div>
          <div class="etapa-bar"><i style="width:${larguraBarra}%; background:${corBarra}"></i></div>
          <div class="etapa-meta">
            <span>plano: no dia</span>
            ${deltaHtml}
          </div>
        </div>
      `;
    }

    // ============= CARDS NORMAIS =============
    const larguraReal = r.real != null ? (r.real / maxValor) * 100 : 0;

    let deltaHtml = '';
    if (r.delta != null) {
      const absD = Math.abs(r.delta).toFixed(1).replace('.', ',');
      if (r.delta > 0.05) {
        deltaHtml = `<span class="delta neg">↑ ${absD}d</span>`;
      } else if (r.delta < -0.05) {
        deltaHtml = `<span class="delta pos">↓ ${absD}d</span>`;
      } else {
        deltaHtml = `<span class="delta zero">no plano</span>`;
      }
    } else {
      deltaHtml = `<span class="delta zero">sem dados</span>`;
    }

    return `
      <div class="etapa-card ${isGargalo ? 'is-gargalo' : ''}">
        <div class="top-stripe" style="background:${r.cor}"></div>
        <div class="etapa-head">
          <span class="etapa-nome">${r.label}</span>
          ${isGargalo ? '<span class="tag-gargalo">Gargalo</span>' : ''}
        </div>
        <div class="etapa-dias">${formatDias(r.real)}<span class="unit">d</span></div>
        <div class="etapa-bar"><i style="width:${larguraReal}%; background:${r.cor}"></i></div>
        <div class="etapa-meta">
          <span>plano ${formatDias(r.plano)}d</span>
          ${deltaHtml}
        </div>
      </div>
    `;
  }).join('');
}
function popularFiltroCliente() {
  const clientes = Array.from(new Set(
    state.pedidos.map(p => p.cliente).filter(Boolean)
  )).sort();
  const sel = $('#filtro-cliente');
  const atual = sel.value;
  sel.innerHTML = '<option value="">Todos</option>' +
    clientes.map(c => `<option value="${c}">${c}</option>`).join('');
  sel.value = atual;
}

function aplicarFiltros(pedidos) {
  const f = state.filtros;
  return pedidos.filter(p => {
    if (p.oculto) return false;
    if (f.status && p.status !== f.status) return false;
    if (f.responsavel && p.responsavel_atual !== f.responsavel) return false;
    if (f.cliente && p.cliente !== f.cliente) return false;
    if (f.busca) {
      const q = f.busca.toLowerCase();
      const haystack = [
        p.cliente, p.projeto, p.comercial, p.subject,
        ...(p.skus || []).map(s => s.codigo + ' ' + s.descricao),
      ].filter(Boolean).join(' ').toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  });
}

// ============================================================
// RENDERIZAÇÃO — TABELA
// ============================================================
function renderizarTabela() {
  const pedidosFiltrados = aplicarFiltros(state.pedidos);
  $('#lista-count').textContent = pedidosFiltrados.length;
  $('#lista-meta').textContent = `de ${state.pedidos.length} total`;

  const tbody = $('#tabela-pedidos-body');
  if (pedidosFiltrados.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="vazio">Nenhum pedido com esses filtros.</td></tr>';
    return;
  }

  tbody.innerHTML = pedidosFiltrados.map(p => {
    const status = STATUS_LABEL[p.status] || p.status;
    const aderenciaHtml = renderAderenciaBadge(p);
    return `
      <tr data-pedido-id="${p.pedido_id}">
        <td class="celula-cliente">${p.cliente || '—'}</td>
        <td class="celula-projeto" title="${p.projeto || ''}">${p.projeto || '—'}</td>
        <td><span class="badge badge-status badge-${p.status}">${status}</span></td>
        <td class="celula-data">${fmtData(p.marcos?.pedido_fechado?.real)}</td>
        <td class="celula-data">
          ${fmtData(p.marcos?.op_liberada?.previsto)}
          ${p.marcos?.op_liberada?.real ? `<br><span class="data-prevista">real ${fmtData(p.marcos.op_liberada.real)}</span>` : ''}
        </td>
        <td class="celula-data">
          ${fmtData(p.marcos?.producao?.previsto)}
          ${p.marcos?.producao?.real ? `<br><span class="data-prevista">real ${fmtData(p.marcos.producao.real)}</span>` : ''}
        </td>
        <td>${aderenciaHtml}</td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('tr').forEach(tr => {
    tr.addEventListener('click', () => {
      const id = tr.dataset.pedidoId;
      const p = state.pedidos.find(x => x.pedido_id === id);
      if (p) abrirDrawer(p);
    });
  });
}

function renderAderenciaBadge(p) {
  // Aderência = pior desvio entre os lead times realizados
  const lt = p.lead_times || {};
  const desvios = Object.values(lt)
    .map(x => x?.desvio)
    .filter(d => d != null);

  if (desvios.length === 0) {
    return '<span class="badge badge-aderencia-na">—</span>';
  }

  const pior = Math.max(...desvios);
  if (pior > 0)  return `<span class="badge badge-aderencia-atrasado">+${pior}d</span>`;
  if (pior < 0)  return `<span class="badge badge-aderencia-adiantado">${pior}d</span>`;
  return '<span class="badge badge-aderencia-ok">No prazo</span>';
}

// ============================================================
// RENDERIZAÇÃO — DRAWER DE DETALHE
// ============================================================
function abrirDrawer(p) {
  state.pedidoAberto = p;
  $('#drawer-body').innerHTML = renderDetalhe(p);
  $('#drawer').setAttribute('aria-hidden', 'false');
}

function fecharDrawer() {
  $('#drawer').setAttribute('aria-hidden', 'true');
  state.pedidoAberto = null;
}

function renderDetalhe(p) {
  return `
    ${renderCabecalho(p)}
    ${renderMetricasResumo(p)}
    <div class="timeline-titulo">Marcos do pedido</div>
    ${renderTimelineHorizontal(p)}
    ${renderLeadTimes(p)}
    ${renderSkus(p)}
  `;
}

function renderCabecalho(p) {
  const status = STATUS_LABEL[p.status] || p.status;
  return `
    <div class="detalhe-cabecalho">
      <div class="breadcrumb">${p.cliente || '—'}</div>
      <h2>${p.projeto || p.subject || 'Pedido sem título'}</h2>
      <div class="detalhe-meta">
        <span>Comercial: <strong>${p.comercial || '—'}</strong></span>
        <span class="meta-dot">${p.skus?.length || 0} SKUs</span>
        <span class="meta-dot">${p.tem_cronograma ? 'Com cronograma' : 'Sem cronograma'}</span>
        <span class="detalhe-meta-status">
          <span class="badge badge-status badge-${p.status}">${status}</span>
        </span>
      </div>
    </div>
  `;
}

function renderMetricasResumo(p) {
  // 3 métricas: lead time real até agora · previsto total · aderência
  const marcos = p.marcos || {};
  const realInicio = marcos.pedido_fechado?.real;
  const hoje_ = hoje();
  const ltRealAteAgora = realInicio ? diasEntre(realInicio, hoje_) : null;

  const prevInicio = marcos.pedido_fechado?.previsto;
  const prevFim = marcos.producao?.previsto;
  const ltPrevistoTotal = (prevInicio && prevFim) ? diasEntre(prevInicio, prevFim) : null;

  // Aderência: pior desvio
  const lt = p.lead_times || {};
  const desvios = Object.values(lt).map(x => x?.desvio).filter(d => d != null);
  const pior = desvios.length ? Math.max(...desvios) : null;
  let aderTexto, aderClasse;
  if (pior === null) { aderTexto = '—'; aderClasse = ''; }
  else if (pior > 0) { aderTexto = `+${pior}d atrasado`; aderClasse = 'cor-atrasado'; }
  else if (pior < 0) { aderTexto = `${pior}d adiantado`; aderClasse = 'cor-ok'; }
  else { aderTexto = 'No prazo'; aderClasse = 'cor-ok'; }

  return `
    <div class="metricas-resumo">
      <div class="metrica">
        <div class="metrica-label">Lead time real</div>
        <div class="metrica-valor">${ltRealAteAgora !== null ? ltRealAteAgora + 'd' : '—'}</div>
        <div class="metrica-sub">desde pedido fechado</div>
      </div>
      <div class="metrica">
        <div class="metrica-label">Previsto total</div>
        <div class="metrica-valor">${ltPrevistoTotal !== null ? ltPrevistoTotal + 'd' : '—'}</div>
        <div class="metrica-sub">pedido → produção</div>
      </div>
      <div class="metrica">
        <div class="metrica-label">Aderência</div>
        <div class="metrica-valor ${aderClasse}">${aderTexto}</div>
        <div class="metrica-sub">pior desvio entre etapas</div>
      </div>
    </div>
  `;
}

function renderTimelineHorizontal(p) {
  const marcos = p.marcos || {};
  const items = MARCOS_ORDEM.map((m, i) => {
    const dadosMarco = marcos[m.key] || {};
    const real = dadosMarco.real;
    const prev = dadosMarco.previsto;
    const por = dadosMarco.por;

    // Determinar estado: feito, atual, pendente
    let estado;
    if (real) estado = 'feito';
    else {
      // É o "atual" se o anterior tá feito e este é o primeiro pendente
      const anterior = MARCOS_ORDEM[i - 1];
      const anteriorFeito = anterior ? marcos[anterior.key]?.real : true;
      estado = (i === 0 || anteriorFeito) ? 'atual' : 'pendente';
    }

    // Tag de aderência da etapa
    let tagHtml = '';
    if (m.key === 'data_vitrine') {
      tagHtml = `<div class="marco-tag tag-na">meta cliente</div>`;
    } else if (real && prev) {
      const d = diasEntre(prev, real);
      if (d > 0) tagHtml = `<div class="marco-tag tag-atrasado">+${d}d</div>`;
      else if (d < 0) tagHtml = `<div class="marco-tag tag-adiantado">${d}d</div>`;
      else tagHtml = `<div class="marco-tag tag-ok">no dia</div>`;
    } else if (real && !prev) {
      tagHtml = `<div class="marco-tag tag-na">sem previsto</div>`;
    } else if (!real && prev) {
      const d = diasEntre(hoje(), prev);
      if (d != null && d >= 0)  tagHtml = `<div class="marco-tag tag-pendente">faltam ${d}d</div>`;
      else if (d != null && d < 0) tagHtml = `<div class="marco-tag tag-atrasado">atrasou ${-d}d</div>`;
      else tagHtml = `<div class="marco-tag tag-pendente">pendente</div>`;
    } else {
      tagHtml = `<div class="marco-tag tag-na">—</div>`;
    }

    // Datas
    const datasHtml = `
      <div class="marco-datas">
        ${prev ? `prev ${fmtData(prev)}` : 'sem previsto'}
        ${real ? `<span class="data-real">real ${fmtData(real)}</span>` : ''}
      </div>
    `;

    // Ícone do círculo
    const proximoFeito = MARCOS_ORDEM[i + 1] ? marcos[MARCOS_ORDEM[i + 1].key]?.real : false;
    const linhaDepoisFeita = !!real && !!proximoFeito;
    const linhaAntesFeita = i > 0 && marcos[MARCOS_ORDEM[i - 1].key]?.real && !!real;

    let icone;
    if (estado === 'feito') icone = '✓';
    else if (estado === 'atual') icone = '◔';
    else icone = '○';

    return `
      <div class="marco">
        <div class="marco-circulo-wrap">
          ${i > 0 ? `<div class="marco-linha-antes ${linhaAntesFeita ? 'feita' : ''}"></div>` : ''}
          <div class="marco-circulo ${estado}">${icone}</div>
          ${i < MARCOS_ORDEM.length - 1 ? `<div class="marco-linha-depois ${linhaDepoisFeita ? 'feita' : ''}"></div>` : ''}
        </div>
        <div class="marco-titulo">${m.label}</div>
        <div class="marco-papel">${por || m.papel}</div>
        ${datasHtml}
        ${tagHtml}
      </div>
    `;
  }).join('');

  return `<div class="timeline-marcos">${items}</div>`;
}

function renderLeadTimes(p) {
  const lt = p.lead_times || {};
  const itens = [
    { key: 'pedido_para_fert',  label: 'Pedido → FERT' },
    { key: 'fert_para_op',      label: 'FERT → OP' },
    { key: 'op_para_producao',  label: 'OP → Produção' },
    { key: 'producao_para_vit', label: 'Produção → Vitrine' },
  ];

  const itensHtml = itens.map(it => {
    const dados = lt[it.key] || {};
    const { previsto, real, desvio } = dados;

    let valor, sub;
    if (real != null) {
      valor = `${real}d`;
      if (previsto != null) {
        const classe = desvio > 0 ? 'pos' : (desvio < 0 ? 'neg' : 'zero');
        const sinal = desvio > 0 ? '+' : '';
        sub = `<span class="lead-time-desvio ${classe}">previsto ${previsto}d (${sinal}${desvio})</span>`;
      } else {
        sub = '<span>sem previsto</span>';
      }
    } else if (previsto != null) {
      valor = `<span style="color:var(--cinza-400)">${previsto}d</span>`;
      sub = '<span>previsto · não realizado</span>';
    } else {
      valor = '<span style="color:var(--cinza-400)">—</span>';
      sub = '<span>sem dados</span>';
    }

    return `
      <div class="lead-time-item">
        <div class="lead-time-label">${it.label}</div>
        <div class="lead-time-valor">${valor}</div>
        <div class="lead-time-comp">${sub}</div>
      </div>
    `;
  }).join('');

  return `
    <div class="lead-times">
      <div class="lead-times-titulo">Lead time entre etapas</div>
      <div class="lead-times-grid">${itensHtml}</div>
    </div>
  `;
}

function renderSkus(p) {
  const skus = p.skus || [];
  if (skus.length === 0) {
    return '<div class="skus-section"><h3>SKUs</h3><p style="color:var(--cinza-500);font-size:13px">Nenhum SKU identificado.</p></div>';
  }
  const itens = skus.map(s => `
    <div class="sku-item">
      <div class="sku-tipo sku-tipo-${s.tipo}">${s.tipo}</div>
      <div class="sku-codigo">${s.codigo}</div>
      <div class="sku-descricao" title="${s.descricao || ''}">${s.descricao || '—'}</div>
    </div>
  `).join('');
  return `
    <div class="skus-section">
      <h3>SKUs (${skus.length})</h3>
      <div class="skus-lista">${itens}</div>
    </div>
  `;
}

// ============================================================
// RENDERIZAÇÃO — ORQUESTRADOR
// ============================================================
function renderizarTudo() {
  popularFiltroCliente();
  renderizarCards();
  renderizarEtapas();
  renderizarTabela();
}

// ============================================================
// EVENTOS
// ============================================================
function ligarEventos() {
  // Filtros
  $('#filtro-busca').addEventListener('input', e => {
    state.filtros.busca = e.target.value;
    renderizarTabela();
  });
  $('#filtro-status').addEventListener('change', e => {
    state.filtros.status = e.target.value;
    renderizarTabela();
  });
  $('#filtro-responsavel').addEventListener('change', e => {
    state.filtros.responsavel = e.target.value;
    renderizarTabela();
  });
  $('#filtro-cliente').addEventListener('change', e => {
    state.filtros.cliente = e.target.value;
    renderizarTabela();
  });
  $('#btn-limpar-filtros').addEventListener('click', () => {
    state.filtros = { busca: '', status: '', responsavel: '', cliente: '' };
    $('#filtro-busca').value = '';
    $('#filtro-status').value = '';
    $('#filtro-responsavel').value = '';
    $('#filtro-cliente').value = '';
    renderizarTabela();
  });

  // Drawer
  $('#drawer-close').addEventListener('click', fecharDrawer);
  $('#drawer-backdrop').addEventListener('click', fecharDrawer);
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && state.pedidoAberto) fecharDrawer();
  });

  // Refresh
  $('#btn-refresh').addEventListener('click', carregarDados);

  // Cards (clicáveis pra filtrar)
  $('.card-atrasados').addEventListener('click', () => {
    state.filtros = { busca: '', status: '', responsavel: '', cliente: '' };
    // Filtra direto pelos atrasados via busca rápida (TODO: melhorar)
    alert('Em breve: clique nos cards filtrará a lista automaticamente.');
  });

  // Apontamentos
  $('#btn-apontamentos').addEventListener('click', () => {
    alert('Em breve: modal de upload de apontamentos.');
  });
}

// ============================================================
// INIT
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
  ligarEventos();
  carregarDados();
});
