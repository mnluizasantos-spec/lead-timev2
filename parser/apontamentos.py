"""
Enriquecimento de pedidos com dados de apontamentos de produção.

O arquivo `apontamentos.xlsx` é exportado do shop floor com as colunas:

  descmaq            descrição da máquina
  colaborador        operador
  numapont           ID único do apontamento (NÃO usado pra cruzar)
  data               YYYY-MM-DD (data da produção naquela máquina)
  maq                código da máquina
  qtdprodconfirmada  quantidade produzida
  numdaop            'OP/operação' ex: '1171338/0060' (etapa 60 da OP 1171338)
  codproduto         FERT 8-4 ou HALB 10 dígitos
  descricaodeproduto descrição
  nomedocliente, coddepto, descdepto (FLEXOGRAFICA, OFFSET, SALTO, CAJAMAR)
  codcliente
  horainical, horatermino  horários dentro do dia

Cruzamento com pedidos:
  Pra cada pedido, varre os FERTs/HALBs e pega os apontamentos correspondentes.
  - producao.real     = data do PRIMEIRO apontamento (1ª produção)
  - producao.fim      = data do ÚLTIMO apontamento (última produção)
  - producao.deptos   = departamentos onde produziu (FLEXO, OFFSET, SALTO, ...)
  - producao.qtd      = quantidade total apontada

Regra de status:
  Se a última produção foi há > 15 dias  → 'concluido'
  Se a última produção foi há <= 15 dias → 'em_producao'
  Se não tem nenhum apontamento          → status atual (não toca)
"""
import re
from collections import defaultdict
from datetime import date, timedelta
from .papeis import (
    STATUS_EM_PRODUCAO, STATUS_CONCLUIDO,
    RESPONSAVEL_POR_STATUS,
)

# Dias sem apontamento pra considerar produção concluída
DIAS_PRA_CONCLUIR = 15


def _normalizar_codigo(c) -> str:
    """Normaliza código do Excel. Strings com '.0' do Excel viram limpas."""
    if c is None:
        return ''
    s = str(c).strip()
    if s.endswith('.0'):
        s = s[:-2]
    return s


def _data_to_str(v):
    """Converte timestamp/datetime/string em 'YYYY-MM-DD'. None se inválido."""
    if v is None:
        return None
    if hasattr(v, 'strftime'):
        return v.strftime('%Y-%m-%d')
    s = str(v).strip()
    if not s or s.lower() == 'nat':
        return None
    return s[:10]


def indexar_apontamentos(apontamentos_path: str) -> dict:
    """
    Lê apontamentos do xlsx OU csv e indexa por codproduto.

    Returns:
        {codproduto_normalizado: [lista de apontamentos]}
        Cada apontamento: {data, descdepto, descmaq, qtdprodconfirmada, numdaop}
    """
    try:
        import pandas as pd
    except ImportError:
        print('  ⚠️  pandas não instalado — pulando apontamentos')
        return {}

    if not apontamentos_path:
        return {}

    colunas = ['data', 'codproduto', 'qtdprodconfirmada',
               'descdepto', 'descmaq', 'numdaop']

    try:
        ext = apontamentos_path.lower()
        if ext.endswith('.csv'):
            df = pd.read_csv(
                apontamentos_path,
                usecols=lambda c: str(c).lower().strip() in colunas,
                dtype={'codproduto': str},   # preserva código sem perder zeros
                low_memory=False,
            )
        else:
            df = pd.read_excel(
                apontamentos_path,
                usecols=colunas,
                dtype={'codproduto': str},
            )
    except Exception as e:
        print(f'  ⚠️  Erro ao ler {apontamentos_path}: {e}')
        return {}

    # Normaliza colunas pra lowercase (caso o usuário mude case)
    df.columns = [str(c).lower().strip() for c in df.columns]

    if 'codproduto' not in df.columns or 'data' not in df.columns:
        print(f'  ⚠️  Colunas obrigatórias não achadas. Tem: {list(df.columns)}')
        return {}

    indice = defaultdict(list)
    for _, row in df.iterrows():
        cod = _normalizar_codigo(row.get('codproduto'))
        if not cod:
            continue
        data_str = _data_to_str(row.get('data'))
        if not data_str:
            continue
        indice[cod].append({
            'data': data_str,
            'descdepto': str(row.get('descdepto', '')).strip(),
            'descmaq': str(row.get('descmaq', '')).strip(),
            'qtd': int(row.get('qtdprodconfirmada', 0) or 0),
            'numdaop': str(row.get('numdaop', '')).strip(),
        })

    print(f'   {len(indice)} código(s) indexados (de {len(df)} apontamentos)')
    return dict(indice)


def enriquecer_com_apontamentos(pedido: dict, indice_apontamentos: dict) -> dict:
    """
    Adiciona dados de produção ao pedido.

    Estratégia:
    1. Pra cada SKU (FERT primeiro, depois HALB), tenta achar apontamentos
    2. Marco 'producao.real' = data do PRIMEIRO apontamento
    3. Novo campo 'producao.fim' = data do ÚLTIMO apontamento
    4. Status: 'em_producao' se última < 15 dias atrás, senão 'concluido'

    Não modifica o pedido in-place — retorna cópia.
    """
    p = dict(pedido)
    p['marcos'] = {k: dict(v) for k, v in pedido['marcos'].items()}

    if not indice_apontamentos:
        return p

    skus = p.get('skus', [])
    ferts = [s['codigo'] for s in skus if s.get('tipo') == 'FERT']
    halbs = [s['codigo'] for s in skus if s.get('tipo') == 'HALB']

    # Coleta apontamentos (FERTs primeiro, HALBs como fallback)
    apontamentos_pedido = []
    busca_por = None
    codigos_encontrados = []

    # Coleta apontamentos POR código (separado pra cada SKU)
    apontamentos_por_codigo = {}  # {codigo: [lista de apontamentos]}
    apontamentos_pedido = []      # agregado (todos juntos)
    busca_por = None
    codigos_encontrados = []

    for fert in ferts:
        if fert in indice_apontamentos:
            apontamentos_por_codigo[fert] = list(indice_apontamentos[fert])
            apontamentos_pedido.extend(indice_apontamentos[fert])
            codigos_encontrados.append(fert)
            busca_por = 'fert'

    # Se nenhum FERT teve apontamento, tenta HALBs
    if not apontamentos_pedido:
        for halb in halbs:
            if halb in indice_apontamentos:
                apontamentos_por_codigo[halb] = list(indice_apontamentos[halb])
                apontamentos_pedido.extend(indice_apontamentos[halb])
                codigos_encontrados.append(halb)
                busca_por = 'halb'

    if not apontamentos_pedido:
        return p  # nenhum apontamento — não toca no pedido

    # ============================================================
    # FILTRO: só apontamentos >= op_liberada.real
    # ----
    # Importante: FERTs/HALBs são REUTILIZADOS em vários pedidos (mesmo
    # código pode rodar várias vezes ao longo do ano). Pra não pegar
    # apontamentos de pedidos passados, filtramos só os feitos APÓS a
    # OP ter sido liberada pra esse pedido específico.
    # Se não tem op_liberada.real, usamos pedido_fechado.real como base.
    # ============================================================
    data_minima_str = (
        p['marcos']['op_liberada'].get('real')
        or p['marcos']['pedido_fechado'].get('real')
    )
    if data_minima_str:
        apontamentos_pedido = [
            a for a in apontamentos_pedido
            if a['data'] >= data_minima_str
        ]
        # Filtra também o mapa por código
        for cod in list(apontamentos_por_codigo.keys()):
            apontamentos_por_codigo[cod] = [
                a for a in apontamentos_por_codigo[cod]
                if a['data'] >= data_minima_str
            ]
            if not apontamentos_por_codigo[cod]:
                del apontamentos_por_codigo[cod]

    if not apontamentos_pedido:
        return p  # nenhum apontamento APÓS op_liberada — produção ainda não começou

    # ============================================================
    # ANEXAR PRODUÇÃO EM CADA SKU DO PEDIDO
    # ----
    # Pra cada SKU, calcula 1ª data, última data, qtd, deptos, n° apontamentos.
    # SKU sem apontamento fica com producao=None (frontend mostra "sem apontamento").
    # ============================================================
    skus_novos = []
    for sku in p.get('skus', []):
        cod = sku.get('codigo')
        ap_do_sku = apontamentos_por_codigo.get(cod, [])
        if ap_do_sku:
            datas_sku = sorted(set(a['data'] for a in ap_do_sku))
            deptos_sku = sorted(set(a['descdepto'] for a in ap_do_sku if a['descdepto']))
            qtd_sku = sum(a.get('qtd', 0) for a in ap_do_sku)
            sku_novo = dict(sku)
            sku_novo['producao'] = {
                'inicio': datas_sku[0],
                'fim': datas_sku[-1],
                'n_apontamentos': len(ap_do_sku),
                'deptos': deptos_sku,
                'qtd': qtd_sku,
            }
            skus_novos.append(sku_novo)
        else:
            skus_novos.append(dict(sku))  # sem produção, mantém SKU original
    p['skus'] = skus_novos

    # ============================================================
    # 1ª e ÚLTIMA produção
    # ============================================================
    datas = sorted(set(a['data'] for a in apontamentos_pedido if a['data']))
    if not datas:
        return p

    primeira = datas[0]
    ultima = datas[-1]

    p['marcos']['producao']['real'] = primeira
    p['marcos']['producao']['fim'] = ultima

    # ============================================================
    # STATUS: concluído se última produção foi há > 15 dias
    # ============================================================
    try:
        d_ultima = date.fromisoformat(ultima)
        if (date.today() - d_ultima).days > DIAS_PRA_CONCLUIR:
            p['status'] = STATUS_CONCLUIDO
        else:
            p['status'] = STATUS_EM_PRODUCAO
        p['responsavel_atual'] = RESPONSAVEL_POR_STATUS[p['status']]
    except (ValueError, TypeError):
        pass

    # ============================================================
    # RECALCULA LEAD TIME OP → PRODUÇÃO COM DADOS REAIS
    # ============================================================
    try:
        op_real = p['marcos']['op_liberada']['real']
        if op_real and primeira:
            d_op = date.fromisoformat(op_real)
            d_prod = date.fromisoformat(primeira)
            real_dias = (d_prod - d_op).days
            p['lead_times']['op_para_producao']['real'] = real_dias
            previsto = p['lead_times']['op_para_producao'].get('previsto')
            if previsto is not None:
                p['lead_times']['op_para_producao']['desvio'] = real_dias - previsto
    except (ValueError, TypeError):
        pass

    # ============================================================
    # DETALHE DA PRODUÇÃO (pra debug e dashboard)
    # ============================================================
    deptos = sorted(set(a['descdepto'] for a in apontamentos_pedido if a['descdepto']))
    qtd_total = sum(a.get('qtd', 0) for a in apontamentos_pedido)

    p['producao_detalhe'] = {
        'busca_por': busca_por,
        'codigos_encontrados': codigos_encontrados,
        'total_apontamentos': len(apontamentos_pedido),
        'primeira_data': primeira,
        'ultima_data': ultima,
        'deptos': deptos,
        'qtd_total': qtd_total,
        'dias_desde_ultima': (date.today() - date.fromisoformat(ultima)).days,
    }

    return p


# ============================================================
# TESTES
# ============================================================
def _teste():
    # Cria pedido falso
    pedido = {
        'pedido_id': 'test',
        'projeto': 'TESTE',
        'cliente': 'CLIENTE TESTE',
        'skus': [
            {'codigo': '11055331-0001', 'tipo': 'FERT'},
        ],
        'marcos': {
            'pedido_fechado': {'previsto': '2026-04-01', 'real': '2026-04-01', 'por': 'X'},
            'fert_criado':    {'previsto': '2026-04-02', 'real': '2026-04-02', 'por': 'Y'},
            'op_liberada':    {'previsto': '2026-04-10', 'real': '2026-04-12', 'por': 'Z'},
            'producao':       {'previsto': '2026-04-20', 'real': None, 'por': None},
            'data_vitrine':   {'previsto': '2026-05-15', 'real': None, 'por': None},
        },
        'lead_times': {
            'op_para_producao': {'previsto': 10, 'real': None, 'desvio': None},
        },
        'status': 'em_producao',
    }

    # Indice falso
    indice = {
        '11055331-0001': [
            {'data': '2026-04-15', 'descdepto': 'SALTO', 'descmaq': 'M1', 'qtd': 1000, 'numdaop': '1/10'},
            {'data': '2026-04-18', 'descdepto': 'SALTO', 'descmaq': 'M1', 'qtd': 2000, 'numdaop': '1/20'},
            {'data': '2026-04-20', 'descdepto': 'OFFSET', 'descmaq': 'M2', 'qtd': 500,  'numdaop': '1/30'},
        ],
    }

    resultado = enriquecer_com_apontamentos(pedido, indice)
    assert resultado['marcos']['producao']['real'] == '2026-04-15'
    assert resultado['marcos']['producao']['fim'] == '2026-04-20'
    assert resultado['producao_detalhe']['qtd_total'] == 3500
    assert set(resultado['producao_detalhe']['deptos']) == {'SALTO', 'OFFSET'}
    print('Caso 1 (1ª e última data) OK ✓')

    # Lead time op→produção foi recalculado: 12/04 → 15/04 = 3 dias
    assert resultado['lead_times']['op_para_producao']['real'] == 3, resultado['lead_times']
    assert resultado['lead_times']['op_para_producao']['desvio'] == -7
    print('Caso 2 (lead time recalculado) OK ✓')

    # Pedido sem apontamento — não toca no status
    pedido_sem = dict(pedido)
    pedido_sem['marcos'] = {k: dict(v) for k, v in pedido['marcos'].items()}
    resultado2 = enriquecer_com_apontamentos(pedido_sem, {})
    assert resultado2['marcos']['producao']['real'] is None
    print('Caso 3 (sem apontamento) OK ✓')

    print('\nTodos os testes de apontamentos passaram ✓')


if __name__ == '__main__':
    _teste()
