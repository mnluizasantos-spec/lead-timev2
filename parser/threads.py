"""
Split de threads de email aninhadas.

Quando alguém responde um email, o cliente Outlook inclui o histórico:

    [resposta atual]

    De: GLEICY MAIA <gleicy.maia@antilhas.com.br>
    Enviada em: quinta-feira, 14 de maio de 2026 15:54
    Para: PedidoFechado_Varejo
    Assunto: PEDIDO FECHADO VAREJO - FRIENDS

    [email original]

A gente precisa separar cada mensagem dessa cadeia, identificar o remetente
e data de cada uma, pra detectar marcos no email CERTO (e não atribuir
"pedido_fechado" pra Giovanna quando o "SETOR DE ATIVIDADE" tá no quote dela).
"""
import re
from .utils import limpar_remetente, parse_data_pt


# Padrão do header de email Outlook em PT-BR
RE_HEADER_OUTLOOK_PT = re.compile(
    r'\n+De:\s*([^\n]+?)\s*\n+'
    r'Enviada em:\s*([^\n]+?)\s*\n+'
    r'(?:Para:\s*.+?)?'
    r'(?:\n+Cc:\s*.+?)?'
    r'\n+Assunto:\s*[^\n]+',
    re.DOTALL | re.IGNORECASE
)


def split_thread_inline(body_text: str, top_remetente: str, top_data) -> list:
    """
    Separa uma cadeia de emails aninhada em mensagens individuais.

    Args:
        body_text: corpo textual completo (top + quotes aninhados)
        top_remetente: nome do remetente do email atual (top da cadeia)
        top_data: datetime do recebimento do email atual

    Returns:
        Lista de mensagens, da MAIS ANTIGA pra MAIS RECENTE:
        [{'remetente': str, 'data': datetime, 'corpo': str}, ...]
    """
    matches = list(RE_HEADER_OUTLOOK_PT.finditer(body_text))
    mensagens = []

    if not matches:
        # Não tem cadeia aninhada — é um email único
        return [{
            'remetente': limpar_remetente(top_remetente),
            'data': top_data,
            'corpo': body_text.strip(),
        }]

    # Mensagem do topo (resposta atual) — do começo até o primeiro header
    mensagens.append({
        'remetente': limpar_remetente(top_remetente),
        'data': top_data,
        'corpo': body_text[:matches[0].start()].strip(),
    })

    # Cada bloco aninhado
    for i, m in enumerate(matches):
        inicio = m.end()
        fim = matches[i + 1].start() if i + 1 < len(matches) else len(body_text)
        mensagens.append({
            'remetente': limpar_remetente(m.group(1)),
            'data': parse_data_pt(m.group(2)),
            'corpo': body_text[inicio:fim].strip(),
        })

    # Inverte pra ordem cronológica (mais antiga primeiro)
    return list(reversed(mensagens))


# ============================================================
# TESTES
# ============================================================
def _teste():
    from datetime import datetime

    # Caso 1: email único, sem aninhamento
    body1 = "Boa tarde, segue pedido fechado.\nSETOR DE ATIVIDADE: 11 HIG"
    msgs = split_thread_inline(body1, 'Gleicy Maia', datetime(2026, 5, 14, 15, 54))
    assert len(msgs) == 1
    assert msgs[0]['remetente'] == 'Gleicy Maia'
    print('Caso 1 (email único) OK ✓')

    # Caso 2: resposta com 1 quote aninhado
    body2 = """Boa tarde, @cadastrar QM
@cadastrar NCM

De: GLEICY MAIA <gleicy.maia@antilhas.com.br>
Enviada em: quinta-feira, 14 de maio de 2026 15:54
Para: PedidoFechado_Varejo
Assunto: PEDIDO FECHADO VAREJO - FRIENDS

Boa tarde, segue.
SETOR DE ATIVIDADE: 11 HIG/PERF/COS/LIMP
PROJETO: FRIENDS
"""
    msgs = split_thread_inline(body2, 'Giovanna Alves', datetime(2026, 5, 15, 18, 44))
    assert len(msgs) == 2

    # Em ordem cronológica: Gleicy primeiro, Giovanna depois
    assert 'GLEICY' in msgs[0]['remetente'].upper(), f'msg0: {msgs[0]["remetente"]}'
    assert 'GIOVANNA' in msgs[1]['remetente'].upper(), f'msg1: {msgs[1]["remetente"]}'

    # Conteúdo: Gleicy tem SETOR DE ATIVIDADE, Giovanna tem @cadastrar
    assert 'SETOR DE ATIVIDADE' in msgs[0]['corpo']
    assert '@cadastrar' in msgs[1]['corpo']
    print('Caso 2 (1 quote aninhado) OK ✓')

    # Caso 3: data do quote foi parseada
    assert msgs[0]['data'] == datetime(2026, 5, 14, 15, 54), f'data quote: {msgs[0]["data"]}'
    print('Caso 3 (data do quote parseada) OK ✓')

    print('\nTodos os testes de split passaram ✓')


if __name__ == '__main__':
    _teste()
