"""
Extração de SKUs (códigos de produto) do corpo dos emails.

FERT (Fertigprodukt) = código comercial    → formato 11055271-0001 (8 dígitos + hífen + 4 dígitos)
HALB (Halbfabrikat)  = semi-acabado        → formato 2100082620   (10 dígitos puros)

No email de pedido fechado, vem uma tabela como:
    CÓDIGO     DESCRIÇÃO
    FERT       11055271-0001    KIT CX TPA FDO FSC PRESS FRIENDS QDB
    HALB       2100082620       KIT CX TPA FSC PRESS FRIENDS QDB
    HALB       2100082621       KIT CX FDO FSC PRESS FRIENDS QDB

Vamos retornar uma lista de SKUs com codigo + tipo + descricao.
"""
import re
from collections import OrderedDict


RE_FERT = re.compile(r'\b(\d{8}-\d{4})\b')
RE_HALB = re.compile(r'(?<!\d)(\d{10})(?!\d)')

# Prefixos de 10 dígitos que NÃO são SKU do pedido (são insumos auxiliares
# como matéria-prima, embalagem geral). Ignoramos tanto na extração
# quanto no cruzamento com apontamentos.
PREFIXOS_HALB_IGNORAR = ('52', '86')


def _halb_valido(codigo: str) -> bool:
    """True se o código de 10 dígitos é um HALB legítimo de pedido."""
    if not codigo:
        return False
    return not str(codigo).startswith(PREFIXOS_HALB_IGNORAR)


# Palavras que aparecem na tabela mas não são descrição
PALAVRAS_RUIDO = {
    'FERT', 'HALB', 'CÓDIGO', 'CODIGO', 'DESCRIÇÃO', 'DESCRICAO',
    'REDE', 'PARA', 'ADEREÇO', 'ADERECO', ''
}


def extrair_skus(corpo: str) -> list:
    """
    Extrai SKUs do corpo do email.

    Retorna lista de dicts: [{'codigo': str, 'tipo': 'FERT'|'HALB', 'descricao': str}]
    Mantém ordem de aparição. Sem duplicatas.
    """
    if not corpo:
        return []

    linhas = [l.strip() for l in corpo.split('\n')]
    skus = OrderedDict()  # codigo → dict

    for i, linha in enumerate(linhas):
        if not linha:
            continue

        # FERT
        for m in RE_FERT.finditer(linha):
            codigo = m.group(1)
            if codigo not in skus:
                # Procura descrição: no resto da linha, ou nas próximas 5 linhas
                resto = linha[m.end():].strip()
                descricao = _extrair_descricao_proximo(resto, linhas, i)
                skus[codigo] = {
                    'codigo': codigo,
                    'tipo': 'FERT',
                    'descricao': descricao,
                }

        # HALB (10 dígitos puros). Ignora prefixos 52 e 86 (insumos auxiliares).
        for m in RE_HALB.finditer(linha):
            codigo = m.group(1)
            if not _halb_valido(codigo):
                continue
            if codigo not in skus:
                resto = linha[m.end():].strip()
                descricao = _extrair_descricao_proximo(resto, linhas, i)
                skus[codigo] = {
                    'codigo': codigo,
                    'tipo': 'HALB',
                    'descricao': descricao,
                }

    return list(skus.values())


def _extrair_descricao_proximo(resto_linha: str, linhas: list, i_atual: int) -> str:
    """
    Procura a descrição do SKU:
    1. No resto da linha onde foi encontrado
    2. Se não tiver, nas próximas 5 linhas, ignorando ruído
    """
    # Tenta primeiro no resto da linha
    if resto_linha and resto_linha.upper() not in PALAVRAS_RUIDO:
        return _limpar_descricao(resto_linha)

    # Procura nas próximas linhas
    for j in range(i_atual + 1, min(i_atual + 6, len(linhas))):
        lj = linhas[j]
        if not lj or lj.upper() in PALAVRAS_RUIDO:
            continue
        # Pula se for outro código (FERT ou HALB)
        if RE_FERT.search(lj) or RE_HALB.search(lj):
            continue
        # Pula se for assinatura
        if 'antilhas' in lj.lower() or '@' in lj or 'fone:' in lj.lower():
            return ''
        return _limpar_descricao(lj)

    return ''


def _limpar_descricao(s: str) -> str:
    """Limpa espaços, tabs e caracteres estranhos da descrição."""
    s = re.sub(r'[\t]+', ' ', s)
    s = re.sub(r'\s+', ' ', s)
    s = s.strip()
    # Trunca em 80 caracteres pra não pegar lixo
    if len(s) > 80:
        s = s[:80].strip()
    return s


# ============================================================
# TESTES
# ============================================================
def _teste():
    # Caso 1: tabela do FRIENDS
    t1 = """
    CÓDIGO     DESCRIÇÃO
    FERT
    11055271-0001
    KIT CX TPA FDO FSC PRESS FRIENDS QDB
    HALB
    2100082620
    KIT CX TPA FSC PRESS FRIENDS QDB
    HALB
    2100082621
    KIT CX FDO FSC PRESS FRIENDS QDB
    """
    skus = extrair_skus(t1)
    codigos = [s['codigo'] for s in skus]
    assert '11055271-0001' in codigos, f'FERT não achado: {codigos}'
    assert '2100082620' in codigos, f'HALB1 não achado: {codigos}'
    assert '2100082621' in codigos, f'HALB2 não achado: {codigos}'

    fert = [s for s in skus if s['codigo'] == '11055271-0001'][0]
    assert fert['tipo'] == 'FERT'
    assert 'FRIENDS' in fert['descricao'].upper(), f'desc fert: {fert}'
    print('Caso 1 (FRIENDS - 3 SKUs) OK ✓')

    # Caso 2: corpo vazio
    assert extrair_skus('') == []
    assert extrair_skus(None) == []
    print('Caso 2 (vazio) OK ✓')

    # Caso 3: descrição na MESMA linha
    t3 = "FERT 11055271-0001 KIT CX FRIENDS\nHALB 2100082620 SEMI-ACABADO"
    skus = extrair_skus(t3)
    assert len(skus) == 2
    assert 'FRIENDS' in skus[0]['descricao'].upper()
    print('Caso 3 (desc na mesma linha) OK ✓')

    # Caso 4: dedup - mesmo código aparece 2x
    t4 = "FERT 11055271-0001\n11055271-0001 mesmo de novo"
    skus = extrair_skus(t4)
    assert len(skus) == 1, f'esperava 1, achou {len(skus)}: {skus}'
    print('Caso 4 (dedup) OK ✓')

    # Caso 5: blacklist de prefixos 52xxx e 86xxx
    t5 = """
    FERT 11055271-0001 KIT CX FRIENDS
    HALB 2100082620 SEMI-ACABADO
    HALB 5200001612 INSUMO IGNORAR
    HALB 8600006921 OUTRO INSUMO IGNORAR
    HALB 2400008287 FUNDO GENERICO
    """
    skus = extrair_skus(t5)
    codigos = [s['codigo'] for s in skus]
    assert '11055271-0001' in codigos
    assert '2100082620' in codigos
    assert '2400008287' in codigos          # 24 entra normal
    assert '5200001612' not in codigos, f'52xxx vazou: {codigos}'
    assert '8600006921' not in codigos, f'86xxx vazou: {codigos}'
    print('Caso 5 (blacklist 52xxx/86xxx) OK ✓')

    print('\nTodos os testes de SKUs passaram ✓')


if __name__ == '__main__':
    _teste()
