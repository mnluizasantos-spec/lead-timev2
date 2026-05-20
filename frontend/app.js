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
  // overrides.json com cancelamentos e ocultamentos manuais
  URL_OVERRIDES: 'https://raw.githubusercontent.com/mnluizasantos-spec/lead-timev2/main/overrides.json',
};

const STATUS_LABEL = {
  aguardando_fert: 'Aguardando FERT',
  aguardando_op:   'Aguardando OP',
  em_producao:     'Em produção',
  concluido:       'Concluído',
  cancelado:       'Cancelado',
  compravel:       'Compravel',
  aguarda_crono:   'Aguarda cronograma',
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
    cronograma: '',   // '' | 'com' | 'sem'
  },
  periodo: '90',       // 30 | 90 | 180 | 'mes_atual' | 'tudo'
  pedidoAberto: null,  // pedido sendo exibido no drawer
};

/**
 * Retorna a data ISO mínima conforme o filtro de período.
 * Se 'tudo', retorna null (sem filtro).
 */
function dataMinimaDoPeriodo() {
  const p = state.periodo;
  if (p === 'tudo') return null;
  const agora = new Date();
  if (p === 'mes_atual') {
    return new Date(agora.getFullYear(), agora.getMonth(), 1).toISOString().slice(0, 10);
  }
  const dias = parseInt(p, 10);
  if (isNaN(dias)) return null;
  const d = new Date(agora.getTime() - dias * 86400000);
  return d.toISOString().slice(0, 10);
}

/**
 * Retorna label legível do período pra mostrar no card.
 */
function labelDoPeriodo() {
  switch (state.periodo) {
    case 'tudo': return 'todos';
    case 'mes_atual': return 'mês atual';
    case '30': return '30d';
    case '90': return '90d';
    case '180': return '6m';
    default: return state.periodo;
  }
}

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
    <tr><td colspan="10" class="vazio">
      Carregando dados...
    </td></tr>`;
  $('#lista-meta').textContent = 'Carregando...';

  try {
    // Cache-burst: ?t=timestamp pra forçar fetch fresh
    const ts = Date.now();
    const [dadosResp, overridesResp] = await Promise.all([
      fetch(`${CONFIG.URL_DADOS}?t=${ts}`,    { cache: 'no-store' }),
      fetch(`${CONFIG.URL_OVERRIDES}?t=${ts}`, { cache: 'no-store' }).catch(() => null),
    ]);
    if (!dadosResp.ok) throw new Error(`HTTP ${dadosResp.status}`);
    const dados = await dadosResp.json();
    state.pedidos = Array.isArray(dados) ? dados : [];

    // Tenta carregar overrides do servidor (não fatal se falhar)
    state.overridesServidor = {};
    if (overridesResp && overridesResp.ok) {
      try {
        state.overridesServidor = await overridesResp.json() || {};
      } catch (e) {
        console.warn('overrides.json malformado:', e);
      }
    }

    renderizarTudo();
  } catch (e) {
    console.error('Erro ao carregar dados:', e);
    $('#tabela-pedidos-body').innerHTML = `
      <tr><td colspan="10" class="vazio">
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
  // Cards de resumo foram removidos do layout. Função mantida vazia
  // pra não quebrar chamadas existentes em renderizarTudo().
  if (!$('#card-atrasados-total')) return;

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
];

function calcularMediasEtapas() {
  /**
   * Pra cada etapa, calcula:
   *  - real médio (média dos lead_times.real dos pedidos do período)
   *  - plano médio (média dos previsto)
   *  - delta = real - plano
   *
   * O card especial 'aderencia' (Comercial — envio) usa um cálculo diferente:
   *  - real = média de "dias de atraso" do envio do pedido
   *           (data_real_pedido_fechado - data_prevista_pedido_fechado)
   *  - plano = 0 (ideal é enviar no dia previsto)
   *  - delta = real (porque plano=0)
   *
   * Filtro: usa o filtro global de período (state.periodo).
   * Considera pedido_fechado.real como referência temporal.
   */
  const dataMin = dataMinimaDoPeriodo();
  const doPeriodo = state.pedidos.filter(p => {
    if (p.oculto) return false;
    const ped = p.marcos?.pedido_fechado?.real;
    if (!ped) return false;
    if (dataMin && ped < dataMin) return false;
    return true;
  });

  const resultados = ETAPAS.map(etapa => {
    // Card especial: pontualidade do comercial
    if (etapa.tipo === 'aderencia') {
      const desvios = [];
      for (const p of doPeriodo) {
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
    for (const p of doPeriodo) {
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
          <span>plano ${formatDias(r.plano)}d · n=${r.amostra || 0}</span>
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
  const dataMin = dataMinimaDoPeriodo();
  return pedidos.filter(p => {
    if (p.oculto) return false;
    // Filtro de período: pedido_fechado.real dentro do período selecionado
    if (dataMin) {
      const ped = p.marcos?.pedido_fechado?.real;
      if (!ped || ped < dataMin) return false;
    }
    if (f.status && p.status !== f.status) return false;
    if (f.responsavel && p.responsavel_atual !== f.responsavel) return false;
    if (f.cliente && p.cliente !== f.cliente) return false;
    if (f.cronograma === 'com' && !p.tem_cronograma) return false;
    if (f.cronograma === 'sem' && p.tem_cronograma) return false;
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
    tbody.innerHTML = '<tr><td colspan="6" class="vazio">Nenhum pedido com esses filtros.</td></tr>';
    return;
  }

  tbody.innerHTML = pedidosFiltrados.map(p => {
    // Motivo de cancelamento/ocultamento (se houver)
    const info = p.cancelado_info || p.oculto_info;
    const motivoHtml = info && info.motivo
      ? `<div class="td-motivo">📌 ${info.motivo}${info.por ? ' · ' + info.por : ''}</div>`
      : '';

    return `
      <tr data-pedido-id="${p.pedido_id}">
        <td class="td-cliente-projeto">
          <div class="td-cliente-label">${p.cliente || '—'}</div>
          <div class="td-projeto-nome" title="${p.projeto || ''}">${p.projeto || '—'}</div>
          ${motivoHtml}
        </td>
        <td>${renderStatusPill(p)}</td>
        <td>${renderPipeline(p)}</td>
        <td class="td-leadtime">${renderLeadTimeCelula(p)}</td>
        <td style="text-align:center">${renderAderenciaBadge(p)}</td>
        <td class="td-acoes">
          <button class="btn-acao" data-acao="excluir" data-pedido-id="${p.pedido_id}" title="Ocultar ou cancelar este pedido">⋮</button>
        </td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('tr').forEach(tr => {
    tr.addEventListener('click', (e) => {
      // Se o clique foi no botão de ação, não abre o drawer
      if (e.target.closest('.btn-acao')) return;
      const id = tr.dataset.pedidoId;
      const p = state.pedidos.find(x => x.pedido_id === id);
      if (p) abrirDrawer(p);
    });
  });

  // Botões de ação (⋮)
  tbody.querySelectorAll('.btn-acao').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const id = btn.dataset.pedidoId;
      const p = state.pedidos.find(x => x.pedido_id === id);
      if (p) abrirModalExcluir(p);
    });
  });
}

// ============================================================
// HELPERS DE RENDERIZAÇÃO DA TABELA
// ============================================================

// 1. Status pill
function renderStatusPill(p) {
  const map = {
    aguardando_fert:   { label: 'Aguardando CAD', classe: 'status-aguardando-cad' },
    aguardando_op:     { label: 'Aguardando ENG', classe: 'status-aguardando-eng' },
    em_producao:       { label: 'Em produção',    classe: 'status-em-producao'   },
    concluido:         { label: 'Concluído',      classe: 'status-concluido'     },
    cancelado:         { label: 'Cancelado',      classe: 'status-cancelado'     },
    compravel:         { label: 'Compravel',      classe: 'status-compravel'     },
    aguarda_crono:     { label: 'Aguarda cronograma', classe: 'status-aguarda-crono' },
  };
  const info = map[p.status] || { label: p.status, classe: '' };

  // Atrasado tem prioridade visual: se o pedido está em alguma etapa e a
  // data prevista dela já passou, mostra "Atrasado" em vermelho
  if (etapaAtualAtrasada(p) && p.status !== 'concluido' && p.status !== 'cancelado') {
    return `<span class="status-pill status-atrasado">Atrasado</span>`;
  }

  return `<span class="status-pill ${info.classe}">${info.label}</span>`;
}

// Verifica se a etapa atual já passou da data prevista
function etapaAtualAtrasada(p) {
  const hojeStr = hoje();
  const m = p.marcos || {};
  const ordem = ['fert_criado', 'op_liberada', 'producao'];
  for (const k of ordem) {
    const real = m[k]?.real;
    const prev = m[k]?.previsto;
    if (real) continue;           // etapa já concluída, não está atrasada
    if (prev && hojeStr > prev) return true;  // não tem real e já passou data
    return false;                  // primeira etapa pendente sem atraso
  }
  return false;
}

// 2. Pipeline visual COM → CAD → ENG → PROD
function renderPipeline(p) {
  const m = p.marcos || {};
  const isCompravel = ['compravel', 'concluido'].includes(p.status) &&
                       (p.skus || []).filter(s => s.tipo === 'FERT').every(s => String(s.codigo).startsWith('15'));

  const etapas = [
    { id: 'COM', marco: 'pedido_fechado' },
    { id: 'CAD', marco: 'fert_criado'    },
    { id: 'ENG', marco: 'op_liberada'    },
    { id: 'PROD', marco: 'producao'      },
  ];

  const items = etapas.map((e, idx) => {
    const real = m[e.marco]?.real;
    const prev = m[e.marco]?.previsto;

    // Compravel: ENG e PROD viram "compra"
    if (isCompravel && (e.id === 'ENG' || e.id === 'PROD')) {
      return `<div class="pipeline-etapa compra" title="Pedido compravel — não passa pela produção interna">compra</div>`;
    }

    if (real) {
      // Etapa concluída
      const classe = (e.id === 'PROD' && p.status === 'concluido')
        ? 'pipeline-etapa concluida-prod'
        : 'pipeline-etapa feita';
      const tooltip = `${e.id} concluído em ${fmtData(real)}`;
      return `<div class="${classe}" title="${tooltip}">${e.id}${e.id === 'PROD' && p.status === 'concluido' ? ' ✓' : ''}</div>`;
    }

    // Etapa não concluída — verifica se é a atual ou pendente
    const anterior = idx > 0 ? etapas[idx - 1] : null;
    const anteriorFeita = anterior ? !!m[anterior.marco]?.real : true;

    if (anteriorFeita) {
      // É a etapa atual. Verifica se está atrasada.
      const atrasada = prev && hoje() > prev;
      const classe = atrasada ? 'pipeline-etapa atrasada' : `pipeline-etapa atual-${e.id.toLowerCase()}`;
      const tooltip = prev
        ? (atrasada ? `${e.id} atrasada (previsto ${fmtData(prev)})` : `${e.id} em andamento (previsto ${fmtData(prev)})`)
        : `${e.id} em andamento`;
      return `<div class="${classe}" title="${tooltip}">${e.id}</div>`;
    }

    // Etapa pendente (anterior ainda não concluída)
    return `<div class="pipeline-etapa" title="${e.id} pendente">${e.id}</div>`;
  }).join('');

  return `<div class="pipeline">${items}</div>`;
}

// 3. Lead Time celula: real / previsto · prog%
function renderLeadTimeCelula(p) {
  const m = p.marcos || {};
  const pedReal = m.pedido_fechado?.real;
  const pedPrev = m.pedido_fechado?.previsto;
  const prodReal = m.producao?.real;
  const prodPrev = m.producao?.previsto;

  // Real: pedido_fechado.real até último marco realizado (ou hoje se em andamento)
  let leadReal = null;
  if (pedReal) {
    if (p.status === 'concluido' && prodReal) {
      leadReal = diasEntre(pedReal, prodReal);
    } else if (p.status === 'concluido' && m.fert_criado?.real) {
      // Compravel concluído: real = pedido → FERT (pq não tem produção)
      leadReal = diasEntre(pedReal, m.fert_criado.real);
    } else {
      leadReal = diasEntre(pedReal, hoje());
    }
  }

  // Previsto: pedido_fechado.previsto → producao.previsto
  let leadPrev = null;
  if (pedPrev && prodPrev) {
    leadPrev = diasEntre(pedPrev, prodPrev);
  }

  let valoresHtml;
  if (leadReal != null && leadPrev != null) {
    valoresHtml = `<span class="real">${leadReal}d</span><span class="slash">/</span><span class="prev">${leadPrev}d</span>`;
  } else if (leadReal != null) {
    valoresHtml = `<span class="real">${leadReal}d</span><span class="slash">/</span><span class="prev">—</span>`;
  } else {
    valoresHtml = `<span style="color:var(--cinza-400)">—</span>`;
  }

  // Progresso
  let progHtml = '';
  if (leadReal != null && leadPrev != null && leadPrev > 0) {
    const pct = Math.round((leadReal / leadPrev) * 100);
    progHtml = `<div class="leadtime-prog">${pct}% do previsto</div>`;
  }

  return `
    <div class="leadtime-cell">
      <div class="leadtime-valores">${valoresHtml}</div>
      ${progHtml}
    </div>
  `;
}

function renderAderenciaBadge(p) {
  // Aderência = SOMA dos desvios das etapas realizadas
  // (compensação: ganho em uma etapa pode anular atraso em outra)
  const lt = p.lead_times || {};
  const desvios = Object.values(lt)
    .map(x => x?.desvio)
    .filter(d => d != null);

  if (desvios.length === 0) {
    return '<span class="aderencia ader-vazio">—</span>';
  }

  const soma = desvios.reduce((a, b) => a + b, 0);
  // Verde: no prazo ou adiantado
  if (soma <= 0) {
    if (soma < 0) return `<span class="aderencia ader-ok">${soma}d</span>`;
    return '<span class="aderencia ader-ok">No prazo</span>';
  }
  // Atraso leve (1 a 3 dias) → amarelo. Forte (4+) → vermelho.
  if (soma <= 3) return `<span class="aderencia ader-atraso-leve">+${soma}d</span>`;
  return `<span class="aderencia ader-atraso">+${soma}d</span>`;
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
    ${renderBannerMotivo(p)}
    ${renderMetricasResumo(p)}
    <div class="timeline-titulo">Marcos do pedido</div>
    ${renderTimelineHorizontal(p)}
    ${renderLeadTimes(p)}
    ${renderSkus(p)}
  `;
}

function renderBannerMotivo(p) {
  // Banner amarelo/vermelho com motivo de cancelamento ou ocultamento
  const info = p.cancelado_info || p.oculto_info;
  if (!info || !info.motivo) return '';

  const tipo = p.cancelado_info ? 'cancelado' : 'oculto';
  const titulo = tipo === 'cancelado' ? 'Pedido cancelado' : 'Pedido oculto';
  const classe = tipo === 'cancelado' ? 'banner-cancelado' : 'banner-oculto';

  const dataFmt = info.data ? fmtData(info.data) : '';
  const porFmt = info.por ? ` por ${info.por}` : '';
  const meta = [dataFmt, porFmt].filter(Boolean).join(' · ');

  return `
    <div class="banner-motivo ${classe}">
      <div class="banner-motivo-titulo">${titulo}</div>
      <div class="banner-motivo-texto">${info.motivo}</div>
      ${meta ? `<div class="banner-motivo-meta">${meta}</div>` : ''}
    </div>
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
  // 3 métricas: lead time real até último marco · previsto total · aderência
  const marcos = p.marcos || {};
  const realInicio = marcos.pedido_fechado?.real;

  // Lead time real = início do pedido até o último marco que ACONTECEU
  // (não usa "hoje" — usa só dados que efetivamente aconteceram)
  const ORDEM_MARCOS_LT = ['pedido_fechado', 'fert_criado', 'op_liberada', 'producao'];
  let ultimoMarcoReal = null;
  for (const k of ORDEM_MARCOS_LT) {
    if (marcos[k]?.real) ultimoMarcoReal = marcos[k].real;
  }
  const ltRealAteAgora = (realInicio && ultimoMarcoReal)
    ? diasEntre(realInicio, ultimoMarcoReal)
    : null;

  const prevInicio = marcos.pedido_fechado?.previsto;
  const prevFim = marcos.producao?.previsto;
  const ltPrevistoTotal = (prevInicio && prevFim) ? diasEntre(prevInicio, prevFim) : null;

  // Aderência = SOMA dos desvios das etapas realizadas
  const lt = p.lead_times || {};
  const desvios = Object.values(lt).map(x => x?.desvio).filter(d => d != null);
  const soma = desvios.length ? desvios.reduce((a, b) => a + b, 0) : null;
  let aderTexto, aderClasse;
  if (soma === null) { aderTexto = '—'; aderClasse = ''; }
  else if (soma > 0) { aderTexto = `+${soma}d atrasado`; aderClasse = 'cor-atrasado'; }
  else if (soma < 0) { aderTexto = `${soma}d adiantado`; aderClasse = 'cor-ok'; }
  else { aderTexto = 'No prazo'; aderClasse = 'cor-ok'; }

  return `
    <div class="metricas-resumo">
      <div class="metrica">
        <div class="metrica-label">Lead time real</div>
        <div class="metrica-valor">${ltRealAteAgora !== null ? ltRealAteAgora + 'd' : '—'}</div>
        <div class="metrica-sub">pedido → último marco</div>
      </div>
      <div class="metrica">
        <div class="metrica-label">Previsto total</div>
        <div class="metrica-valor">${ltPrevistoTotal !== null ? ltPrevistoTotal + 'd' : '—'}</div>
        <div class="metrica-sub">pedido → produção</div>
      </div>
      <div class="metrica">
        <div class="metrica-label">Aderência</div>
        <div class="metrica-valor ${aderClasse}">${aderTexto}</div>
        <div class="metrica-sub">soma dos desvios entre etapas</div>
      </div>
    </div>
  `;
}

function renderTimelineHorizontal(p) {
  const marcos = p.marcos || {};
  const compravel = p.status === 'compravel';

  // Pra compravel, escondemos OP, Produção e Vitrine (vai direto pedido→FERT→compra pronta)
  const marcosVisiveis = compravel
    ? MARCOS_ORDEM.filter(m => m.key !== 'op_liberada' && m.key !== 'producao' && m.key !== 'data_vitrine')
    : MARCOS_ORDEM;

  const items = marcosVisiveis.map((m, i) => {
    const dadosMarco = marcos[m.key] || {};
    const real = dadosMarco.real;
    const prev = dadosMarco.previsto;
    const por = dadosMarco.por;

    // Determinar estado: feito, atual, pendente
    let estado;
    if (real) estado = 'feito';
    else {
      // É o "atual" se o anterior tá feito e este é o primeiro pendente
      const anterior = marcosVisiveis[i - 1];
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
    const realUltima = m.key === 'op_liberada' ? dadosMarco.real_ultima : null;
    const nParcelas = m.key === 'op_liberada' ? (dadosMarco.n_parcelas || 0) : 0;
    const datasHtml = `
      <div class="marco-datas">
        ${prev ? `prev ${fmtData(prev)}` : 'sem previsto'}
        ${real ? `<span class="data-real">início ${fmtData(real)}</span>` : ''}
        ${realUltima && realUltima !== real ? `<span class="data-real">última ${fmtData(realUltima)}</span>` : ''}
        ${nParcelas > 1 ? `<span class="data-extra">${nParcelas} parcelas</span>` : ''}
        ${m.key === 'producao' && dadosMarco.fim ? `<span class="data-real">fim ${fmtData(dadosMarco.fim)}</span>` : ''}
      </div>
    `;

    // Linhas verde/cinza conectando círculos
    const proximo = marcosVisiveis[i + 1];
    const proximoFeito = proximo ? marcos[proximo.key]?.real : false;
    const linhaDepoisFeita = !!real && !!proximoFeito;
    const linhaAntesFeita = i > 0 && marcos[marcosVisiveis[i - 1].key]?.real && !!real;

    let icone;
    if (estado === 'feito') icone = '✓';
    else if (estado === 'atual') icone = '◔';
    else icone = '○';

    return `
      <div class="marco">
        <div class="marco-circulo-wrap">
          ${i > 0 ? `<div class="marco-linha-antes ${linhaAntesFeita ? 'feita' : ''}"></div>` : ''}
          <div class="marco-circulo ${estado}">${icone}</div>
          ${i < marcosVisiveis.length - 1 ? `<div class="marco-linha-depois ${linhaDepoisFeita ? 'feita' : ''}"></div>` : ''}
        </div>
        <div class="marco-titulo">${m.label}</div>
        <div class="marco-papel">${por || m.papel}</div>
        ${datasHtml}
        ${tagHtml}
      </div>
    `;
  }).join('');

  const colsClass = compravel ? 'compravel' : '';
  return `<div class="timeline-marcos ${colsClass}">${items}</div>`;
}

function renderLeadTimes(p) {
  const lt = p.lead_times || {};
  const compravel = p.status === 'compravel';

  // Pra compraveis, só mostra Pedido → FERT (resto não se aplica)
  const itens = compravel
    ? [{ key: 'pedido_para_fert', label: 'Pedido → FERT' }]
    : [
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
  const itens = skus.map(s => {
    const prod = s.producao;
    const isCompravel = String(s.codigo || '').startsWith('15');
    let prodHtml;

    if (prod) {
      // Tem apontamentos — mostra início → fim · departamentos (sem qtd)
      const ini = fmtData(prod.inicio);
      const fim = fmtData(prod.fim);
      const intervalo = ini === fim ? ini : `${ini} → ${fim}`;
      const deptos = (prod.deptos || []).join(', ');
      prodHtml = `
        <div class="sku-producao sku-producao-feita" title="${prod.n_apontamentos} apontamento(s)">
          <span class="sku-producao-icone">✓</span>
          <span class="sku-producao-datas">${intervalo}</span>
          <span class="sku-producao-extra">· ${deptos}</span>
        </div>
      `;
    } else if (isCompravel) {
      // FERT 15xxx — é compravel, não passa por produção interna
      prodHtml = `
        <div class="sku-producao sku-producao-compravel">
          <span class="sku-producao-icone">🛒</span>
          <span class="sku-producao-datas">compravel</span>
        </div>
      `;
    } else {
      prodHtml = `
        <div class="sku-producao sku-producao-vazia">
          <span class="sku-producao-icone">—</span>
          <span class="sku-producao-datas">sem apontamento</span>
        </div>
      `;
    }
    return `
      <div class="sku-item">
        <div class="sku-cabecalho">
          <div class="sku-tipo sku-tipo-${s.tipo}">${s.tipo}</div>
          <div class="sku-codigo">${s.codigo}</div>
          <div class="sku-descricao" title="${s.descricao || ''}">${s.descricao || '—'}</div>
        </div>
        ${prodHtml}
      </div>
    `;
  }).join('');
  return `
    <div class="skus-section">
      <h3>SKUs (${skus.length})</h3>
      <div class="skus-lista">${itens}</div>
    </div>
  `;
}

// ============================================================
// MODAL DE EXCLUSÃO (ocultar / cancelar)
// ============================================================
// A senha é validada SEMPRE no backend (Netlify Function).
// O cliente não conhece a senha — envia o que o usuário digitou.
let pedidoModalAtual = null;

function abrirModalExcluir(p) {
  pedidoModalAtual = p;
  $('#modal-pedido-nome').textContent = `${p.cliente || 'Pedido'} — ${p.projeto || '—'}`;
  $('#modal-motivo').value = '';
  $('#modal-senha').value = '';
  $('#modal-erro').style.display = 'none';
  // Reset radio pra 'ocultar'
  document.querySelectorAll('input[name="acao-excluir"]').forEach(r => {
    r.checked = (r.value === 'ocultar');
  });
  $('#modal-excluir').setAttribute('aria-hidden', 'false');
  setTimeout(() => $('#modal-senha').focus(), 100);
}

function fecharModalExcluir() {
  $('#modal-excluir').setAttribute('aria-hidden', 'true');
  pedidoModalAtual = null;
}

async function confirmarExcluir() {
  if (!pedidoModalAtual) return;

  const senha = $('#modal-senha').value;
  const motivo = $('#modal-motivo').value.trim();
  const acao = document.querySelector('input[name="acao-excluir"]:checked')?.value;
  const pedidoId = pedidoModalAtual.pedido_id;

  if (!senha) {
    $('#modal-erro').textContent = 'Digite a senha.';
    $('#modal-erro').style.display = 'block';
    return;
  }

  // Monta override
  const override = {
    status_manual: acao === 'cancelar' ? 'cancelado' : 'oculto',
    motivo: motivo || null,
    por: 'PCP',
    data: new Date().toISOString().slice(0, 10),
  };

  // Envia pro backend ANTES de aplicar local — a senha é validada lá
  $('#btn-confirmar-excluir').disabled = true;
  $('#btn-confirmar-excluir').textContent = 'Enviando...';
  $('#modal-erro').style.display = 'none';

  try {
    await enviarOverrideBackend(pedidoId, override, senha);
  } catch (e) {
    $('#modal-erro').textContent = e.message || 'Erro ao enviar';
    $('#modal-erro').style.display = 'block';
    $('#btn-confirmar-excluir').disabled = false;
    $('#btn-confirmar-excluir').textContent = 'Confirmar';
    return;
  }

  // Backend aceitou — aplica local
  if (acao === 'cancelar') {
    pedidoModalAtual.status = 'cancelado';
    pedidoModalAtual.responsavel_atual = '-';
    pedidoModalAtual.cancelado_info = override;
  } else {
    pedidoModalAtual.oculto = true;
    pedidoModalAtual.oculto_info = override;
  }

  salvarOverrideLocal(pedidoId, override);
  fecharModalExcluir();
  renderizarTudo();
  $('#btn-confirmar-excluir').disabled = false;
  $('#btn-confirmar-excluir').textContent = 'Confirmar';
}

function salvarOverrideLocal(pedidoId, override) {
  try {
    const overrides = JSON.parse(localStorage.getItem('overrides') || '{}');
    overrides[pedidoId] = override;
    localStorage.setItem('overrides', JSON.stringify(overrides));
  } catch (e) {
    console.warn('Erro salvando override local:', e);
  }
}

function aplicarOverridesLocaisAosPedidos() {
  // Aplica overrides na seguinte ordem (último sobrescreve):
  // 1) overrides do servidor (overrides.json — fonte da verdade)
  // 2) localStorage (mudanças recentes que ainda não persistiram)
  try {
    const overridesLocal = JSON.parse(localStorage.getItem('overrides') || '{}');
    const overridesServidor = state.overridesServidor || {};

    for (const p of state.pedidos) {
      // Merge: servidor primeiro, local depois (local prevalece)
      const ov = { ...overridesServidor[p.pedido_id], ...overridesLocal[p.pedido_id] };
      if (!ov || !ov.status_manual) continue;

      if (ov.status_manual === 'cancelado') {
        p.status = 'cancelado';
        p.responsavel_atual = '-';
        p.cancelado_info = ov;
      } else if (ov.status_manual === 'oculto') {
        p.oculto = true;
        p.oculto_info = ov;
      }
    }
  } catch (e) {
    console.warn('Erro aplicando overrides:', e);
  }
}

async function enviarOverrideBackend(pedidoId, override, senha) {
  // Chama a Netlify Function pra commitar no overrides.json no GitHub.
  // A senha é validada lá no backend (process.env.SENHA_OP).
  const resp = await fetch('/.netlify/functions/upsert-override', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pedido_id: pedidoId, override, senha }),
  });
  if (!resp.ok) {
    let detalhe = '';
    try {
      const json = await resp.json();
      detalhe = json.error || JSON.stringify(json);
    } catch (e) { /* ignore */ }
    throw new Error(`HTTP ${resp.status}${detalhe ? ': ' + detalhe : ''}`);
  }
  return resp.json();
}

// ============================================================
// MODAL DE UPLOAD DE APONTAMENTOS
// ============================================================
function abrirModalApontamentos() {
  $('#modal-arquivo').value = '';
  $('#modal-arquivo-info').style.display = 'none';
  $('#modal-senha-apont').value = '';
  $('#modal-erro-apont').style.display = 'none';
  $('#modal-progresso-secao').style.display = 'none';
  $('#btn-confirmar-apont').disabled = false;
  $('#btn-confirmar-apont').textContent = 'Enviar';
  $('#modal-apontamentos').setAttribute('aria-hidden', 'false');
}

function fecharModalApontamentos() {
  $('#modal-apontamentos').setAttribute('aria-hidden', 'true');
}

async function confirmarUploadApontamentos() {
  const arquivo = $('#modal-arquivo').files?.[0];
  const senha = $('#modal-senha-apont').value;
  const erro = $('#modal-erro-apont');
  const progresso = $('#modal-progresso');
  const progressoSecao = $('#modal-progresso-secao');
  const btn = $('#btn-confirmar-apont');

  erro.style.display = 'none';

  // Validações
  if (!arquivo) {
    erro.textContent = 'Selecione um arquivo xlsx.';
    erro.style.display = 'block';
    return;
  }
  if (!/\.xlsx?$/i.test(arquivo.name)) {
    erro.textContent = 'Arquivo deve ser .xlsx ou .xls.';
    erro.style.display = 'block';
    return;
  }
  if (!senha) {
    erro.textContent = 'Digite a senha.';
    erro.style.display = 'block';
    return;
  }
  if (arquivo.size > 25 * 1048576) {
    erro.textContent = 'Arquivo > 25MB. Tente compactar/exportar com menos colunas.';
    erro.style.display = 'block';
    return;
  }

  // Lê arquivo, converte pra CSV, comprime com gzip
  btn.disabled = true;
  btn.textContent = 'Enviando...';
  progressoSecao.style.display = 'block';
  progresso.textContent = 'Lendo arquivo...';

  try {
    // 1. Lê bytes do arquivo
    const bytes = await arquivoParaBytes(arquivo);
    const tamOriginal = bytes.length;

    // 2. Converte xlsx → CSV no navegador (SheetJS)
    // Por que? xlsx é zip-comprimido por dentro, gzip não reduz mais.
    // CSV é texto repetitivo, gzip reduz pra ~15% do tamanho.
    progresso.textContent = 'Convertendo xlsx → CSV...';
    if (typeof XLSX === 'undefined') {
      throw new Error('SheetJS (XLSX) nao carregou. Recarregue a pagina.');
    }
    const wb = XLSX.read(bytes, { type: 'array' });
    const sheet = wb.Sheets[wb.SheetNames[0]];
    const csvStr = XLSX.utils.sheet_to_csv(sheet, { rawNumbers: true });
    const csvBytes = new TextEncoder().encode(csvStr);
    console.log(`xlsx ${(tamOriginal/1048576).toFixed(2)}MB → CSV ${(csvBytes.length/1048576).toFixed(2)}MB`);

    // 3. Comprime CSV com gzip
    progresso.textContent = 'Comprimindo CSV...';
    if (typeof pako === 'undefined') {
      throw new Error('pako (gzip) nao carregou. Recarregue a pagina.');
    }
    const comprimido = pako.gzip(csvBytes, { level: 9 });
    const tamComprimido = comprimido.length;
    console.log(`CSV ${(csvBytes.length/1048576).toFixed(2)}MB → gzip ${(tamComprimido/1048576).toFixed(2)}MB`);

    // 4. Converte pra base64
    const base64gz = bytesPraBase64(comprimido);
    const tamPayloadMB = base64gz.length / 1048576;
    progresso.textContent = `Comprimido pra ${tamPayloadMB.toFixed(2)} MB. Enviando...`;

    if (tamPayloadMB > 5.5) {
      throw new Error(`Payload ainda muito grande (${tamPayloadMB.toFixed(2)} MB). Limite ~5.5 MB.`);
    }

    // 5. Envia pra Netlify Function (que descomprime e commita CSV no GitHub)
    const resp = await fetch('/.netlify/functions/upload-apontamentos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        senha,
        filename: 'apontamentos.csv',     // agora envia CSV, mais leve
        content_base64_gz: base64gz,
        size_original: csvBytes.length,
      }),
    });

    if (!resp.ok) {
      let detalhe = '';
      try {
        const json = await resp.json();
        detalhe = json.error || JSON.stringify(json);
      } catch (e) { /* ignore */ }
      throw new Error(`HTTP ${resp.status}${detalhe ? ': ' + detalhe : ''}`);
    }

    const json = await resp.json();
    const reducaoTotal = ((1 - tamComprimido / tamOriginal) * 100).toFixed(0);
    progresso.innerHTML = `
      ✓ Enviado! Commit <code style="font-family:var(--font-mono)">${(json.sha || '').slice(0,7)}</code><br>
      Original: ${(tamOriginal/1048576).toFixed(2)} MB · enviado: ${tamPayloadMB.toFixed(2)} MB (-${reducaoTotal}%)<br>
      O parser vai rodar agora (~30s). Atualize em 1 minuto pra ver os dados.
    `;
    progresso.style.background = 'var(--verde-100)';
    progresso.style.borderColor = 'var(--verde-500)';
    progresso.style.color = 'var(--verde-700)';
    btn.textContent = 'Concluído';
  } catch (e) {
    console.error(e);
    erro.textContent = 'Erro: ' + e.message;
    erro.style.display = 'block';
    btn.disabled = false;
    btn.textContent = 'Tentar de novo';
  }
}

// Lê arquivo como Uint8Array
function arquivoParaBytes(arquivo) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(new Uint8Array(reader.result));
    reader.onerror = () => reject(new Error('Falha lendo arquivo'));
    reader.readAsArrayBuffer(arquivo);
  });
}

// Converte Uint8Array em base64 (em chunks pra não estourar a call stack)
function bytesPraBase64(bytes) {
  const CHUNK = 0x8000; // 32KB
  let binary = '';
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}

// ============================================================
// RENDERIZAÇÃO — ORQUESTRADOR
// ============================================================
function renderizarTudo() {
  aplicarOverridesLocaisAosPedidos();
  popularFiltroCliente();
  renderizarCards();
  renderizarEtapas();
  renderizarTabela();
}

// ============================================================
// EVENTOS
// ============================================================
function ligarEventos() {
  // Filtro global de período (afeta cards de etapas E tabela de pedidos)
  $('#filtro-periodo').addEventListener('change', e => {
    state.periodo = e.target.value;
    renderizarEtapas();
    renderizarTabela();
  });

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
  $('#filtro-cronograma').addEventListener('change', e => {
    state.filtros.cronograma = e.target.value;
    renderizarTabela();
  });
  $('#btn-limpar-filtros').addEventListener('click', () => {
    state.filtros = { busca: '', status: '', responsavel: '', cliente: '', cronograma: '' };
    $('#filtro-busca').value = '';
    $('#filtro-status').value = '';
    $('#filtro-responsavel').value = '';
    $('#filtro-cliente').value = '';
    $('#filtro-cronograma').value = '';
    renderizarTabela();
  });

  // Drawer
  $('#drawer-close').addEventListener('click', fecharDrawer);
  $('#drawer-backdrop').addEventListener('click', fecharDrawer);
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      if (document.querySelector('#modal-excluir[aria-hidden="false"]')) fecharModalExcluir();
      else if (state.pedidoAberto) fecharDrawer();
    }
  });

  // Modal de exclusão
  document.querySelectorAll('[data-close-modal]').forEach(el => {
    el.addEventListener('click', fecharModalExcluir);
  });
  $('#btn-confirmar-excluir').addEventListener('click', confirmarExcluir);
  $('#modal-senha').addEventListener('keypress', e => {
    if (e.key === 'Enter') confirmarExcluir();
  });

  // Refresh
  $('#btn-refresh').addEventListener('click', carregarDados);

  // Apontamentos
  $('#btn-apontamentos').addEventListener('click', abrirModalApontamentos);
  document.querySelectorAll('[data-close-modal-apontamentos]').forEach(el => {
    el.addEventListener('click', fecharModalApontamentos);
  });
  $('#btn-confirmar-apont').addEventListener('click', confirmarUploadApontamentos);
  $('#modal-arquivo').addEventListener('change', e => {
    const arq = e.target.files?.[0];
    const info = $('#modal-arquivo-info');
    if (arq) {
      const tamMB = (arq.size / 1048576).toFixed(2);
      info.textContent = `${arq.name} · ${tamMB} MB`;
      info.style.display = 'block';
    } else {
      info.style.display = 'none';
    }
  });
}

// ============================================================
// INIT
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
  ligarEventos();
  carregarDados();
});
