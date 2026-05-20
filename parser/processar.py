"""
Processa um conjunto de emails da mesma thread (conversationId)
e produz UM pedido com os marcos, cronograma e SKUs identificados.
"""
import os
import re
from collections import defaultdict
from datetime import datetime

from .utils import (
    html_to_text, parse_iso, limpar_remetente, normalizar_remetente_dedup,
    extrair_cliente_do_subject, diferenca_dias
)
from .clientes import identificar_cliente_projeto, eh_subject_ruido, extrair_projeto_dos_skus
from .marcos import classificar_marco
from .cronograma import extrair_cronograma
from .skus import extrair_skus
from .threads import split_thread_inline
from .papeis import (
    STATUS_AGUARDANDO_FERT, STATUS_AGUARDANDO_OP,
    STATUS_EM_PRODUCAO, STATUS_CONCLUIDO, STATUS_CANCELADO,
    STATUS_COMPRAVEL, STATUS_AGUARDA_CRONOGRAMA,
    RESPONSAVEL_POR_STATUS, ORDEM_MARCOS,
)


# Regex pra detectar reedição/revisão no subject
# (com ou sem acento, em maiúsculas ou minúsculas)
RE_REEDICAO_SUBJECT = re.compile(
    r'\b(REEDI[ÇC][ÃA]O|REVIS[ÃA]O|REVISADO|RE-EDI[ÇC][ÃA]O)\b',
    re.IGNORECASE
)


def eh_reedicao(subject: str) -> bool:
    """Detecta se o pedido é uma reedição/revisão pelo subject,
    ou um subject de ruído (ALINHAMENTO, AGENDAMENTO, INFORME, FYI).
    Ambos casos devem ser ignorados pelo processador."""
    if not subject:
        return False
    if RE_REEDICAO_SUBJECT.search(subject):
        return True
    # Subjects de ruído (ALINHAMENTO, AGENDAMENTO, INFORME, FYI)
    if eh_subject_ruido(subject):
        return True
    return False


def processar_thread(emails_da_thread: list, auditoria: dict = None) -> dict:
    """
    Processa todos os emails de uma thread e retorna o pedido consolidado.

    Args:
        emails_da_thread: lista de emails do Power Automate (mesmo conversationId)
        auditoria: dict mutável pra registrar problemas (opcional)

    Returns:
        Dict do pedido (schema do BLUEPRINT_V2.md seção 3.5),
        None se a thread não tem pedido_fechado válido,
        ou None se a thread é reedição (descartada).
    """
    if auditoria is None:
        auditoria = {
            'marcos_rejeitados': [],
            'threads_sem_pedido_fechado': [],
            'remetentes_desconhecidos': set(),
            'reedicoes_ignoradas': [],
        }
    auditoria.setdefault('reedicoes_ignoradas', [])

    # ============================================================
    # 0. FILTRO DE REEDIÇÃO — ignora threads cujo subject (em QUALQUER
    #    email da thread) contém 'REEDICAO', 'REVISAO', etc.
    # ============================================================
    for email in emails_da_thread:
        subj = email.get('subject', '')
        if eh_reedicao(subj):
            auditoria['reedicoes_ignoradas'].append({
                'thread_id': email.get('conversationId', ''),
                'subject': subj,
            })
            return None

    # ============================================================
    # 1. EXPLODE CADA EMAIL EM MENSAGENS (split inline de quotes)
    # ============================================================
    mensagens_brutas = []  # lista de {remetente, data, corpo}
    subject_thread = None
    thread_id = None
    cronograma = {}  # do email inicial

    for email in emails_da_thread:
        if thread_id is None:
            thread_id = email.get('conversationId', email.get('id', ''))
        if subject_thread is None:
            subject_thread = email.get('subject', '')

        remetente_top = email.get('from', '')
        data_top = parse_iso(email.get('receivedDateTime'))

        # Converte HTML em texto
        corpo_html = email.get('body', '')
        is_html = email.get('isHtml', True)
        corpo_texto = html_to_text(corpo_html) if is_html else corpo_html

        # Tenta extrair CRONOGRAMA — só do email inicial (pedido_fechado)
        # vai ter a tabela; nas respostas tá no quote, então pode pegar
        # do mais antigo que tiver.
        if not cronograma:
            c = extrair_cronograma(corpo_texto)
            if c:
                cronograma = c

        # Quebra em mensagens (top + quotes aninhados)
        msgs = split_thread_inline(corpo_texto, remetente_top, data_top)
        for m in msgs:
            mensagens_brutas.append(m)

    if not mensagens_brutas:
        return None

    # ============================================================
    # 2. CLASSIFICA CADA MENSAGEM E COLETA MARCOS
    # ============================================================
    # Estrutura: {tipo_marco: [{data, remetente, corpo}, ...]}
    marcos_encontrados = defaultdict(list)

    # Dedup: (tipo, data_minuto, remetente_normalizado)
    visto = set()

    for msg in mensagens_brutas:
        if msg['data'] is None:
            continue
        classificacao = classificar_marco(msg['corpo'], msg['remetente'])
        tipo = classificacao['tipo']
        if tipo is None:
            continue
        if not classificacao['aceito']:
            auditoria['marcos_rejeitados'].append({
                'thread_id': thread_id,
                'tipo_detectado': tipo,
                'remetente': msg['remetente'],
                'motivo': classificacao['motivo_rejeicao'],
            })
            continue

        # Dedup
        key = (
            tipo,
            msg['data'].strftime('%Y-%m-%d %H:%M'),
            normalizar_remetente_dedup(msg['remetente'])
        )
        if key in visto:
            continue
        visto.add(key)

        marcos_encontrados[tipo].append({
            'data': msg['data'],
            'remetente': msg['remetente'],
            'corpo': msg['corpo'],
        })

    # ============================================================
    # 3. EXIGE pedido_fechado pra thread virar pedido
    # ============================================================
    if 'pedido_fechado' not in marcos_encontrados:
        auditoria['threads_sem_pedido_fechado'].append({
            'thread_id': thread_id,
            'subject': subject_thread,
            'marcos_que_tem': list(marcos_encontrados.keys()),
        })
        return None

    # ============================================================
    # 4. ESCOLHE O MAIS ANTIGO DE CADA MARCO (a 1ª vez que aconteceu)
    # ============================================================
    def mais_antigo(eventos):
        return min(eventos, key=lambda e: e['data'])

    def mais_recente(eventos):
        return max(eventos, key=lambda e: e['data'])

    pedido_fechado_ev = mais_antigo(marcos_encontrados['pedido_fechado'])
    fert_criado_ev    = mais_antigo(marcos_encontrados['ferts_criados']) if 'ferts_criados' in marcos_encontrados else None
    op_liberada_ev    = mais_antigo(marcos_encontrados['ops_liberadas']) if 'ops_liberadas' in marcos_encontrados else None
    # Para OP em parcelas: também guarda a ÚLTIMA liberação se houver mais de 1
    ops_liberadas_lista = marcos_encontrados.get('ops_liberadas', [])
    op_liberada_ultima_ev = mais_recente(ops_liberadas_lista) if len(ops_liberadas_lista) > 1 else None

    # ============================================================
    # 4.5. FILTRO DE DATA MÍNIMA (env: PEDIDO_FECHADO_DESDE)
    # ----
    # Se a env var PEDIDO_FECHADO_DESDE estiver setada (formato YYYY-MM-DD),
    # ignoramos pedidos cujo pedido_fechado.real é anterior. Útil pra
    # excluir threads antigas que o Power Automate puxou junto.
    # ============================================================
    desde = os.environ.get('PEDIDO_FECHADO_DESDE', '').strip()
    if desde:
        try:
            desde_iso = datetime.fromisoformat(desde).date()
            ped_data = pedido_fechado_ev['data'].date()
            if ped_data < desde_iso:
                if auditoria is not None:
                    auditoria.setdefault('pedidos_filtrados_data', []).append({
                        'thread_id': thread_id,
                        'subject': subject_thread,
                        'pedido_fechado_real': ped_data.isoformat(),
                        'limite': desde_iso.isoformat(),
                    })
                return None
        except (ValueError, AttributeError) as e:
            # Formato inválido — ignora filtro
            pass

    # ============================================================
    # 5. EXTRAI SKUs SÓ DO EMAIL DO FERTS_CRIADOS
    # ----
    # Regra: SKUs são extraídos APENAS da mensagem onde a Engenharia
    # respondeu o cadastro ("@cadastrar / transferir plano"). Se ainda
    # não tem ferts_criados, lista vazia — Maria/Comercial pode ter
    # mencionado códigos antigos no pedido_fechado, mas isso não conta.
    # ============================================================
    if fert_criado_ev:
        skus = extrair_skus(fert_criado_ev['corpo'])
    else:
        skus = []

    # ============================================================
    # 6. MONTA MARCOS NO SCHEMA FINAL
    # ============================================================
    marcos = {
        'pedido_fechado': {
            'previsto': cronograma.get('pedido_fechado').isoformat() if cronograma.get('pedido_fechado') else None,
            'real': pedido_fechado_ev['data'].date().isoformat(),
            'por': pedido_fechado_ev['remetente'],
        },
        'fert_criado': {
            'previsto': cronograma.get('fert_criado').isoformat() if cronograma.get('fert_criado') else None,
            'real': fert_criado_ev['data'].date().isoformat() if fert_criado_ev else None,
            'por': fert_criado_ev['remetente'] if fert_criado_ev else None,
        },
        'op_liberada': {
            'previsto': cronograma.get('op_liberada').isoformat() if cronograma.get('op_liberada') else None,
            'real': op_liberada_ev['data'].date().isoformat() if op_liberada_ev else None,
            'por': op_liberada_ev['remetente'] if op_liberada_ev else None,
            # Quando OP é liberada em parcelas, guarda a última data também
            'real_ultima': op_liberada_ultima_ev['data'].date().isoformat() if op_liberada_ultima_ev else None,
            'n_parcelas': len(ops_liberadas_lista) if ops_liberadas_lista else 0,
        },
        'producao': {
            'previsto': cronograma.get('producao').isoformat() if cronograma.get('producao') else None,
            'real': None,  # vem de apontamentos.xlsx (próximo módulo)
            'por': None,
        },
        'data_vitrine': {
            'previsto': cronograma.get('data_vitrine').isoformat() if cronograma.get('data_vitrine') else None,
            'real': None,  # data vitrine é só meta, não tem "real"
            'por': None,
        },
    }

    # ============================================================
    # 7. CALCULA LEAD TIMES (opção 1: entre etapas consecutivas)
    # ============================================================
    lead_times = _calcular_lead_times(marcos)

    # ============================================================
    # 8. STATUS (6 automáticos: aguardando_fert/op, em_producao,
    #    concluido, compravel, aguarda_crono)
    # ============================================================
    status, responsavel = _calcular_status(
        marcos,
        skus=skus,
        tem_cronograma=bool(cronograma),
    )

    # ============================================================
    # 9. PEDIDO FINAL
    # ============================================================
    # Identifica cliente e projeto a partir do subject
    cliente_ident, projeto_ident = identificar_cliente_projeto(subject_thread)

    # Fallback: se subject não deu projeto utilizável, busca na descrição
    # do primeiro FERT (que tem o nome real do produto/projeto).
    if not projeto_ident:
        projeto_ident = extrair_projeto_dos_skus(skus, cliente_ident)

    # Último recurso: deixa em branco. Subject cru não vai mais como projeto.
    projeto_final = projeto_ident or ''

    return {
        'pedido_id': thread_id,
        'subject': subject_thread,
        'projeto': projeto_final,
        'cliente': cliente_ident,
        'comercial': limpar_remetente(pedido_fechado_ev['remetente']),
        'skus': skus,
        'marcos': marcos,
        'lead_times': lead_times,
        'status': status,
        'responsavel_atual': responsavel,
        'tem_cronograma': bool(cronograma),
    }


# ============================================================
# HELPERS DE CÁLCULO
# ============================================================
def _calcular_lead_times(marcos: dict) -> dict:
    """
    Calcula lead times entre etapas consecutivas (opção 1).
    Cada lead time tem: previsto (dias), real (dias), desvio (real - previsto).
    """
    from datetime import date

    def parse(s):
        if not s:
            return None
        try:
            return date.fromisoformat(s)
        except (ValueError, TypeError):
            return None

    def diff(d1, d2):
        if d1 is None or d2 is None:
            return None
        return (d2 - d1).days

    p = {
        'pedido_fechado': parse(marcos['pedido_fechado']['previsto']),
        'fert_criado':    parse(marcos['fert_criado']['previsto']),
        'op_liberada':    parse(marcos['op_liberada']['previsto']),
        'producao':       parse(marcos['producao']['previsto']),
        'data_vitrine':   parse(marcos['data_vitrine']['previsto']),
    }
    r = {
        'pedido_fechado': parse(marcos['pedido_fechado']['real']),
        'fert_criado':    parse(marcos['fert_criado']['real']),
        'op_liberada':    parse(marcos['op_liberada']['real']),
        'producao':       parse(marcos['producao']['real']),
    }

    def lead(de, ate, real_de, real_ate):
        prev = diff(p[de], p[ate])
        real = diff(r.get(real_de), r.get(real_ate))
        desvio = real - prev if (real is not None and prev is not None) else None
        return {'previsto': prev, 'real': real, 'desvio': desvio}

    return {
        'pedido_para_fert':  lead('pedido_fechado', 'fert_criado', 'pedido_fechado', 'fert_criado'),
        'fert_para_op':      lead('fert_criado', 'op_liberada', 'fert_criado', 'op_liberada'),
        'op_para_producao':  lead('op_liberada', 'producao', 'op_liberada', 'producao'),
        'producao_para_vit': lead('producao', 'data_vitrine', None, None),  # vitrine não tem real
    }


def _calcular_status(marcos: dict, skus: list = None, tem_cronograma: bool = True) -> tuple:
    """
    Status baseado em quais marcos têm valor 'real', tipo de SKU e
    presença de cronograma.

    Regras (na ordem):
    1. Se TODOS os FERTs são "compravel" (prefixo 15) → 'compravel'
       (compra pronto, não passa por OP/produção)
    2. Se sem cronograma E sem FERT criado → 'aguarda_crono'
       (pedido fechado mas comercial ainda vai mandar o cronograma)
    3. Resto: fluxo normal por marcos (aguardando_fert → aguardando_op
       → em_producao → concluido)

    Returns:
        (status: str, responsavel: str)
    """
    from .papeis import todos_skus_compraveis

    tem_fert = marcos['fert_criado']['real'] is not None
    tem_op   = marcos['op_liberada']['real'] is not None
    tem_prod = marcos['producao']['real'] is not None

    # Regra 1: compravel — pedido com produtos 15xxx não passa por produção.
    # - Se FERT foi cadastrado → 'concluido' (fluxo administrativo encerrado).
    # - Senão → 'compravel' (aguarda Engenharia cadastrar o código).
    if todos_skus_compraveis(skus or []):
        if tem_fert:
            status = STATUS_CONCLUIDO
        else:
            status = STATUS_COMPRAVEL
        return status, RESPONSAVEL_POR_STATUS[status]

    # Regra 2: pedido fechado mas sem cronograma E sem FERT → aguarda crono
    if not tem_cronograma and not tem_fert:
        status = STATUS_AGUARDA_CRONOGRAMA
        return status, RESPONSAVEL_POR_STATUS[status]

    # Regra 3: fluxo normal
    if tem_prod:
        # TODO: distinguir em_producao vs concluido (precisa info do apontamento.xlsx)
        status = STATUS_EM_PRODUCAO
    elif tem_op:
        status = STATUS_EM_PRODUCAO  # OP liberada → produção começou
    elif tem_fert:
        status = STATUS_AGUARDANDO_OP
    else:
        status = STATUS_AGUARDANDO_FERT

    return status, RESPONSAVEL_POR_STATUS[status]
