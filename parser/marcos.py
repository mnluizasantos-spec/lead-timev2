"""
Detecção de marcos (pedido_fechado, ferts_criados, ops_liberadas, pedido_revisado)
no corpo de cada email.

Lógica:
1. Detecta TIPO do marco por regex (mais específico primeiro)
2. Valida PAPEL do remetente (cada marco só vale do papel certo)
3. Retorna o tipo ou None

IMPORTANTE: Antes de classificar, REMOVE o trecho do CRONOGRAMA do corpo,
porque a tabela tem rótulos como "OP liberada" e "FERT criado" que iriam
disparar falsos positivos.
"""
import re
from .papeis import papel_do_remetente, PAPEL_EXIGIDO


# ============================================================
# REGEX DE DETECÇÃO
# ============================================================
RE_OPS_LIBERADAS = re.compile(
    r'(OPs?\s+liberadas?|Segue\s+OPs?\s+liberadas?)',
    re.IGNORECASE
)
RE_FERTS_CRIADOS = re.compile(
    r'(@\w+.+cadastrar|transferir\s+plano|Plano\s+lan[çc]ado)',
    re.IGNORECASE
)
RE_PEDIDO_REVISADO = re.compile(
    r'(versionar\s+os?\s+[Ff]erts?|inativar\s+os?\s+[Ff]erts?)',
    re.IGNORECASE
)
RE_PEDIDO_FECHADO_INICIAL = re.compile(
    r'SETOR DE ATIVIDADE',
    re.IGNORECASE
)

# Remove o bloco do CRONOGRAMA pra evitar falsos positivos.
# A tabela contém rótulos como "OP liberada", "FERT criado" que NÃO são
# marcos reais — são só nomes das linhas da tabela de previsão.
# A abordagem aqui é remover qualquer linha que tenha "OP liberada",
# "FERT criado", "Pedido Fechado", "Data Vitrine" ou "Produção" seguida
# de uma data DD/MM/AAAA — esses são os rótulos da tabela CRONOGRAMA.
RE_LINHA_CRONOGRAMA = re.compile(
    r'(Data\s+Vitrine|Pedido\s+Fechado|FERT\s+criado|OP\s+liberada|Produ[çc][ãa]o)'
    r'\s*\n?\s*\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{4}',
    re.IGNORECASE
)


def _limpar_cronograma(corpo: str) -> str:
    """Remove linhas da tabela CRONOGRAMA pra não confundir com marcos reais."""
    if not corpo:
        return ''
    return RE_LINHA_CRONOGRAMA.sub('', corpo)


def detectar_tipo_marco(corpo: str):
    """
    ORDEM IMPORTA — mais específico primeiro:

    1. ops_liberadas   — frase específica "OPs liberadas"
    2. pedido_revisado — frase específica "versionar/inativar FERTs"
    3. ferts_criados   — "@cadastrar / transferir plano"
       (PRECISA vir ANTES de pedido_fechado porque emails de FERTs criados
       contêm "SETOR DE ATIVIDADE" no histórico aninhado da resposta)
    4. pedido_fechado  — "SETOR DE ATIVIDADE" (genérico, só sobra pra
       emails iniciais)
    """
    # Remove CRONOGRAMA antes de detectar
    corpo_limpo = _limpar_cronograma(corpo)

    if RE_OPS_LIBERADAS.search(corpo_limpo):
        return 'ops_liberadas'
    if RE_PEDIDO_REVISADO.search(corpo_limpo):
        return 'pedido_revisado'
    if RE_FERTS_CRIADOS.search(corpo_limpo):
        return 'ferts_criados'
    if RE_PEDIDO_FECHADO_INICIAL.search(corpo_limpo):
        return 'pedido_fechado'
    return None


def classificar_marco(corpo: str, remetente: str) -> dict:
    """
    Detecta marco + valida papel do remetente.

    Returns:
        {'tipo': str ou None, 'aceito': bool, 'motivo_rejeicao': str ou None}
    """
    tipo = detectar_tipo_marco(corpo)
    if tipo is None:
        return {'tipo': None, 'aceito': False, 'motivo_rejeicao': None}

    papel = papel_do_remetente(remetente)
    papel_necessario = PAPEL_EXIGIDO[tipo]

    if papel == papel_necessario:
        return {'tipo': tipo, 'aceito': True, 'motivo_rejeicao': None}

    return {
        'tipo': tipo,
        'aceito': False,
        'motivo_rejeicao': f'papel_remetente={papel}, esperava={papel_necessario}',
    }


# ============================================================
# TESTES
# ============================================================
def _teste():
    # Caso 1: pedido fechado da comercial
    r = classificar_marco('SETOR DE ATIVIDADE: 11 HIG', 'gleicy.maia@antilhas.com.br')
    assert r['tipo'] == 'pedido_fechado' and r['aceito'], r
    print('Caso 1 (pedido fechado da comercial) OK ✓')

    # Caso 2: ferts criados (com @cadastrar) — engenharia
    r = classificar_marco(
        '@Qualidade, @cadastrar NCM. CODIGO 11055271-0001',
        'giovanna.alves@antilhas.com.br'
    )
    assert r['tipo'] == 'ferts_criados' and r['aceito'], r
    print('Caso 2 (ferts criados da engenharia) OK ✓')

    # Caso 3: OPs liberadas da engenharia
    r = classificar_marco('Segue OPs liberadas para produção', 'ariane.luz@antilhas.com.br')
    assert r['tipo'] == 'ops_liberadas' and r['aceito'], r
    print('Caso 3 (OPs liberadas da engenharia) OK ✓')

    # Caso 4: pedido fechado da engenharia (REJEITADO - papel errado)
    r = classificar_marco('SETOR DE ATIVIDADE: 11 HIG', 'giovanna.alves@antilhas.com.br')
    assert r['tipo'] == 'pedido_fechado' and not r['aceito'], r
    assert 'engenharia' in r['motivo_rejeicao']
    print('Caso 4 (rejeitado por papel) OK ✓')

    # Caso 5: corpo sem marco
    r = classificar_marco('Bom dia, segue anexo.', 'gleicy.maia@antilhas.com.br')
    assert r['tipo'] is None
    print('Caso 5 (sem marco detectável) OK ✓')

    # Caso 6: email da Giovanna com SETOR DE ATIVIDADE no histórico
    # (resposta dela contém o pedido original como quote)
    # Tem "@cadastrar" no corpo (resposta dela) E "SETOR DE ATIVIDADE" no quote
    # Detecção pega o ferts_criados primeiro (correto)
    corpo_friends = """
    @Qualidade, cadastrar QM
    @cadastrar NCM
    @cadastrar preço

    De: GLEICY MAIA
    SETOR DE ATIVIDADE: 11 HIG
    """
    r = classificar_marco(corpo_friends, 'giovanna.alves@antilhas.com.br')
    assert r['tipo'] == 'ferts_criados' and r['aceito'], f'caso6: {r}'
    print('Caso 6 (FRIENDS - ferts_criados com quote) OK ✓')

    print('\nTodos os testes de marcos passaram ✓')


if __name__ == '__main__':
    _teste()
