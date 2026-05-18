"""
Extração do CRONOGRAMA estruturado do email.

A partir de 15/05/2026, emails de pedido fechado têm uma tabela como:

    CRONOGRAMA — PEDIDO FECHADO VAREJO
    PROJETO: QUEM DISSE BERENISSE – CAIXA PRESS KIT FRIENDS
    #  MARCO            DATA PREVISTA   OBSERVAÇÕES
    1  Data Vitrine     17/07/2026      Quando o produto precisa estar em loja
    2  Pedido Fechado   14/05/2026      Data prevista de envio do pedido
    3  FERT criado      15/05/2026      Cadastro / transferência de plano
    4  OP liberada      26/05/2026      Liberação da Ordem de Produção
    5  Produção         19/06/2026      Conclusão da produção pelo PCP/Fábrica

Esse módulo extrai as 5 datas previstas. Se não achar tabela, retorna {}.
"""
import re
from .utils import parse_data_curta


# Marcador que indica início do bloco do cronograma
RE_HEADER_CRONOGRAMA = re.compile(
    r'CRONOGRAMA\s*[—\-–]\s*PEDIDO\s+FECHADO',
    re.IGNORECASE
)

# Rótulos esperados no cronograma. Ordem importa: mais específico primeiro.
ROTULOS_CRONOGRAMA = [
    ('data_vitrine',   re.compile(r'\bData\s+Vitrine\b',   re.IGNORECASE)),
    ('fert_criado',    re.compile(r'\bFERT\s+criado\b',    re.IGNORECASE)),
    ('op_liberada',    re.compile(r'\bOP\s+liberada\b',    re.IGNORECASE)),
    ('producao',       re.compile(r'\bPRODUÇÃO\b|\bProdução\b|\bProducao\b', re.IGNORECASE)),
    ('pedido_fechado', re.compile(r'\bPedido\s+Fechado\b', re.IGNORECASE)),
]

# Data DD/MM/AAAA (aceita espaços ao redor das barras: "14 / 05 / 2026" ou "14/05/2026")
RE_DATA_PREVISTA = re.compile(r'(\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{4})')

# Linha do header da tabela (pra pular)
RE_HEADER_TABELA = re.compile(
    r'(MARCO|DATA\s+PREVISTA|OBSERVA[ÇC][ÕO]ES|CRONOGRAMA|PROJETO\s*:)',
    re.IGNORECASE
)


def extrair_cronograma(corpo_texto: str) -> dict:
    """
    Extrai datas previstas do CRONOGRAMA.

    Args:
        corpo_texto: corpo do email já convertido pra texto.

    Returns:
        Dict com chaves: 'data_vitrine', 'pedido_fechado', 'fert_criado',
        'op_liberada', 'producao' — cada uma com date.
        Retorna {} se não achar o bloco CRONOGRAMA.
    """
    if not corpo_texto:
        return {}

    m_header = RE_HEADER_CRONOGRAMA.search(corpo_texto)
    if not m_header:
        return {}

    # Pega só o trecho APÓS o header e limita a 3000 caracteres.
    inicio = m_header.end()
    trecho = corpo_texto[inicio: inicio + 3000]
    linhas = trecho.split('\n')

    cronograma = {}

    for marco_key, re_rotulo in ROTULOS_CRONOGRAMA:
        for i, linha in enumerate(linhas):
            if RE_HEADER_TABELA.search(linha):
                continue
            if not re_rotulo.search(linha):
                continue
            # Acha data na mesma linha
            m_data = RE_DATA_PREVISTA.search(linha)
            if m_data:
                data = parse_data_curta(m_data.group(1))
                if data:
                    cronograma[marco_key] = data
                    break
            # Se não tem data na linha, procura nas próximas 3
            achou = False
            for offset in range(1, 4):
                if i + offset >= len(linhas):
                    break
                prox = linhas[i + offset]
                m_data = RE_DATA_PREVISTA.search(prox)
                if m_data:
                    data = parse_data_curta(m_data.group(1))
                    if data:
                        cronograma[marco_key] = data
                        achou = True
                        break
            if achou:
                break

    return cronograma


# ============================================================
# TESTES
# ============================================================
def _teste():
    from datetime import date

    # Caso 1: tabela direta
    t1 = """
    CRONOGRAMA — PEDIDO FECHADO VAREJO
    PROJETO: QUEM DISSE BERENISSE
    #  MARCO            DATA PREVISTA
    1  Data Vitrine     17/07/2026
    2  Pedido Fechado   14/05/2026
    3  FERT criado      15/05/2026
    4  OP liberada      26/05/2026
    5  Produção         19/06/2026
    """
    c = extrair_cronograma(t1)
    assert c.get('data_vitrine')   == date(2026, 7, 17), f'vitrine: {c.get("data_vitrine")}'
    assert c.get('pedido_fechado') == date(2026, 5, 14), f'pedido: {c.get("pedido_fechado")}'
    assert c.get('fert_criado')    == date(2026, 5, 15), f'fert: {c.get("fert_criado")}'
    assert c.get('op_liberada')    == date(2026, 5, 26), f'op: {c.get("op_liberada")}'
    assert c.get('producao')       == date(2026, 6, 19), f'prod: {c.get("producao")}'
    print('Caso 1 (tabela direta) OK ✓')

    # Caso 2: sem CRONOGRAMA - email antigo
    t2 = "Boa tarde, segue pedido fechado. SETOR DE ATIVIDADE: 11 HIG"
    c = extrair_cronograma(t2)
    assert c == {}, f'Esperava vazio, achou: {c}'
    print('Caso 2 (sem cronograma) OK ✓')

    # Caso 3: dados em linhas separadas (HTML quebrado mal)
    t3 = """
    CRONOGRAMA - PEDIDO FECHADO VAREJO

    1
    Data Vitrine
    17/07/2026

    2
    Pedido Fechado
    14/05/2026
    """
    c = extrair_cronograma(t3)
    assert c.get('data_vitrine')   == date(2026, 7, 17), f'caso3 vitrine: {c}'
    assert c.get('pedido_fechado') == date(2026, 5, 14), f'caso3 pedido: {c}'
    print('Caso 3 (linhas separadas) OK ✓')

    print('\nTodos os testes do cronograma passaram ✓')


if __name__ == '__main__':
    _teste()
