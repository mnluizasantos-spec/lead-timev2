"""
Enriquecimento de pedidos com dados de apontamentos de produção.

O arquivo `apontamentos.xlsx` é exportado do shop floor com colunas:
  - codproduto: código do produto (FERT 8-4 ou HALB de 10 dígitos)
  - dataini, datafim: datas de início e fim da operação
  - numdaop: número da OP / operação
  - ... (outros campos)

Pra cada pedido, a gente cruza os SKUs com o apontamentos:
  - Tenta primeiro pelo FERT (código comercial)
  - Se não achar, tenta pelo HALB (semi-acabado, fallback)
  - O marco 'producao.real' = data do PRIMEIRO apontamento encontrado
  - Status pode virar 'em_producao' (tem apontamento ativo) ou 'concluido'
"""
import re
from collections import defaultdict
from .papeis import (
    STATUS_AGUARDANDO_FERT, STATUS_AGUARDANDO_OP,
    STATUS_EM_PRODUCAO, STATUS_CONCLUIDO, STATUS_CANCELADO,
    RESPONSAVEL_POR_STATUS,
)


def _normalizar_codigo(c) -> str:
    """
    Normaliza código do Excel (pode vir como float "2100082620.0").
    Retorna string limpa pronta pra comparação.
    """
    if c is None:
        return ''
    s = str(c).strip()
    # Remove '.0' do final (Excel converte int em float às vezes)
    if s.endswith('.0'):
        s = s[:-2]
    return s


def indexar_apontamentos(apontamentos_path: str) -> dict:
    """
    Lê o xlsx e indexa apontamentos por codproduto.

    Returns:
        {codproduto_normalizado: [lista de apontamentos]}
        Cada apontamento é um dict com chaves: codproduto, dataini, datafim, numdaop, ...
    """
    try:
        import pandas as pd
    except ImportError:
        print('  ⚠️  pandas não instalado — pulando apontamentos')
        return {}

    if not apontamentos_path:
        return {}

    try:
        df = pd.read_excel(apontamentos_path)
    except Exception as e:
        print(f'  ⚠️  Erro ao ler {apontamentos_path}: {e}')
        return {}

    # Normaliza colunas pra lowercase sem espaços
    df.columns = [str(c).lower().strip() for c in df.columns]

    if 'codproduto' not in df.columns:
        print(f'  ⚠️  Coluna codproduto não achada. Colunas: {list(df.columns)}')
        return {}

    indice = defaultdict(list)
    for _, row in df.iterrows():
        cod = _normalizar_codigo(row.get('codproduto'))
        if not cod:
            continue
        registro = {k: row.get(k) for k in df.columns}
        # Converte timestamps em string ISO pra serializar depois
        for k in ('dataini', 'datafim'):
            if k in registro and registro[k] is not None:
                try:
                    registro[k] = registro[k].isoformat() if hasattr(registro[k], 'isoformat') else str(registro[k])
                except Exception:
                    pass
        indice[cod].append(registro)

    return dict(indice)


def enriquecer_com_apontamentos(pedido: dict, indice_apontamentos: dict) -> dict:
    """
    Adiciona dados de produção ao pedido.

    Estratégia:
    1. Pra cada SKU FERT do pedido, tenta achar apontamentos
    2. Se não achar pelo FERT, tenta pelos HALBs
    3. Marco 'producao.real' = data do PRIMEIRO apontamento (1ª produção)
    4. Adiciona 'producao_detalhe' com lista de apontamentos agrupados

    Não modifica o pedido in-place — retorna cópia.
    """
    p = dict(pedido)  # cópia rasa
    p['marcos'] = {k: dict(v) for k, v in pedido['marcos'].items()}

    if not indice_apontamentos:
        return p

    skus = p.get('skus', [])
    ferts = [s['codigo'] for s in skus if s['tipo'] == 'FERT']
    halbs = [s['codigo'] for s in skus if s['tipo'] == 'HALB']

    # Coleta apontamentos achados (tenta FERT primeiro, depois HALB)
    apontamentos_pedido = []
    busca_por = None

    for fert in ferts:
        if fert in indice_apontamentos:
            apontamentos_pedido.extend(indice_apontamentos[fert])
            busca_por = 'fert'

    # Se não achou nada pelos FERTs, busca pelos HALBs
    if not apontamentos_pedido:
        for halb in halbs:
            if halb in indice_apontamentos:
                apontamentos_pedido.extend(indice_apontamentos[halb])
                busca_por = 'halb'

    if not apontamentos_pedido:
        return p  # nenhum apontamento — pedido fica sem produção

    # Acha a data mais antiga de início (1ª produção)
    datas_inicio = [a.get('dataini') for a in apontamentos_pedido if a.get('dataini')]
    datas_fim    = [a.get('datafim') for a in apontamentos_pedido if a.get('datafim')]

    if datas_inicio:
        data_min = min(str(d) for d in datas_inicio)
        # Converte pra date YYYY-MM-DD
        primeira = data_min[:10] if len(data_min) >= 10 else data_min
        p['marcos']['producao']['real'] = primeira

    # Verifica se ainda tem produção em andamento
    # (algum apontamento sem datafim = produção em curso)
    tem_em_curso = any(not a.get('datafim') for a in apontamentos_pedido)
    tem_concluido = all(a.get('datafim') for a in apontamentos_pedido)

    # Atualiza status
    if p['marcos']['producao']['real'] is not None:
        if tem_em_curso:
            p['status'] = STATUS_EM_PRODUCAO
        elif tem_concluido and datas_fim:
            p['status'] = STATUS_CONCLUIDO
        p['responsavel_atual'] = RESPONSAVEL_POR_STATUS[p['status']]

    # Recalcula lead time op→producao com dados reais
    from datetime import date
    try:
        op_real = p['marcos']['op_liberada']['real']
        prod_real = p['marcos']['producao']['real']
        if op_real and prod_real:
            d_op = date.fromisoformat(op_real)
            d_prod = date.fromisoformat(prod_real)
            real_dias = (d_prod - d_op).days
            p['lead_times']['op_para_producao']['real'] = real_dias
            previsto = p['lead_times']['op_para_producao']['previsto']
            if previsto is not None:
                p['lead_times']['op_para_producao']['desvio'] = real_dias - previsto
    except (ValueError, TypeError):
        pass

    # Detalhe da produção
    p['producao_detalhe'] = {
        'busca_por': busca_por,
        'total_apontamentos': len(apontamentos_pedido),
        'data_inicio_min': min(str(d)[:10] for d in datas_inicio) if datas_inicio else None,
        'data_fim_max': max(str(d)[:10] for d in datas_fim) if datas_fim else None,
        'em_curso': tem_em_curso,
    }

    return p
