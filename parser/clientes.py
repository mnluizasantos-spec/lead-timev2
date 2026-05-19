"""
Identifica CLIENTE e PROJETO a partir do subject do email.

Lista oficial de clientes da Antilhas + aliases pra normalizar
variações de digitação.

Estratégia:
1. Limpa o subject de prefixos ruido (RES:, RE:, FW:, ENC:)
2. Limpa palavras de processo (PEDIDO FECHADO, VAREJO, INST, etc)
3. Procura cada cliente conhecido no que sobrou
4. Tudo que sobra depois de remover o cliente vira "projeto"
"""
import re
import unicodedata


# ----------------------------------------------------------------------
# Lista oficial de clientes
# Cada item: (nome_canonico, [aliases])
# A busca é feita por todos os aliases, mas o nome retornado é o canônico.
# ----------------------------------------------------------------------
_CLIENTES_LISTA = [
    ('ALLOS',                ['ALLOS']),
    ('ANACAPRI',             ['ANACAPRI']),
    ('ARCO EDUCACAO',        ['ARCO EDUCACAO', 'ARCO EDUCAÇÃO']),
    ('AREZZO',               ['AREZZO']),
    ('AVATIM',               ['AVATIM']),
    ('AVON',                 ['AVON']),
    ('BAUDUCCO',             ['BAUDUCCO']),
    ('BELEZA NA WEB',        ['BELEZA NA WEB']),
    ('BISCOITE',             ['BISCOITE']),
    ('BOBSTORE',             ['BOBSTORE', 'BOB STORE']),
    # BOTICARIO inclui "O BOTICARIO" + sigla BOT (cuidado: BOT muito curto, só com hífen)
    ('BOTICARIO',            ['O BOTICARIO', 'O BOTICÁRIO', 'BOTICARIO', 'BOTICÁRIO']),
    ('BROOKSFIELD',          ['BROOKSFIELD']),
    ('BROOKSFIELD DONNA',    ['BROOKSFIELD DONNA']),
    ('BROOKSFIELD JR',       ['BROOKSFIELD JR']),
    ('C&A',                  ['C&A', 'C E A']),
    ('CAMICADO',             ['CAMICADO']),
    ('CASA GRANADO CARE',    ['CASA GRANADO CARE', 'GRANADO CARE']),
    ('CASA GRANADO PHEBO',   ['CASA GRANADO PHEBO', 'GRANADO PHEBO', 'PHEBO']),
    ('CASA GRANADO',         ['CASA GRANADO', 'GRANADO']),  # base — depois das variantes
    ('CAU CHOCOL',           ['CAU CHOCOL', 'CAU CHOCOLATES']),
    ('CHILLI BEANS OTICA',   ['CHILLI BEANS OTICA', 'CHILLI BEANS ÓTICA']),
    ('CHILLI BEANS',         ['CHILLI BEANS']),
    ('CHOC BRASIL CACAU',    ['CHOC BRASIL CACAU', 'BRASIL CACAU']),
    ('DECATHLON',            ['DECATHLON']),
    ('DENGO',                ['DENGO']),
    ('DROGARIA SAO PAULO',   ['DROGARIA SAO PAULO', 'DROGARIA SÃO PAULO', 'DPSP', 'DROGA SP', 'DROGARIA SP']),
    ('DUDALINA',             ['DUDALINA']),
    ('ELLUS',                ['ELLUS']),
    ('EUDORA',               ['EUDORA']),
    ('GAZIT',                ['GAZIT']),
    ('GBARBOSA CENCOSUD',    ['GBARBOSA CENCOSUD', 'GBARBOSA', 'CENCOSUD']),
    ('GIRAFFAS',             ['GIRAFFAS']),
    ('HAVAIANAS',            ['HAVAIANAS']),
    ('HOPE LINGERIE',        ['HOPE LINGERIE']),
    ('HOPE RESORT',          ['HOPE RESORT']),
    ('ISA BAHIA',            ['ISA BAHIA']),
    ('KOP KOFFEE',           ['KOP KOFFEE']),
    ('KOPENHAGEN',           ['KOPENHAGEN']),
    ('LA VILLE',             ['LA VILLE']),
    ('LE LIS BLANC CASA',    ['LE LIS BLANC CASA']),
    ('LE LIS BLANC',         ['LE LIS BLANC']),
    ('LE POSTICHE',          ['LE POSTICHE']),
    ('LINDT',                ['LINDT']),
    # LOCCITANE inclui "AU BRESIL" como mesmo cliente
    ('LOCCITANE',            ['LOCCITANE AU BRESIL', 'LOCCITANE']),
    ('LOFT STYLE',           ['LOFT STYLE']),
    ('LUPO SPORT',           ['LUPO SPORT']),
    ('LUPO',                 ['LUPO']),
    ('MAHOGANY',             ['MAHOGANY']),
    ('MERCADO JAGUARE',      ['MERCADO JAGUARE', 'JAGUARE']),
    ('MONTE CARLO',          ['MONTE CARLO']),
    ('MORANA',               ['MORANA']),
    ('MULTIPLAN',            ['MULTIPLAN']),
    ('MUNDIAL CALCADOS',     ['MUNDIAL CALCADOS', 'MUNDIAL CALÇADOS']),
    ('NATURA VAREJO',        ['NATURA VAREJO', 'NATURA']),
    ('NESTLE',               ['NESTLE', 'NESTLÉ']),
    ('NETSHOES',             ['NETSHOES']),
    ('NUTTY BAVARIAN',       ['NUTTY BAVARIAN']),
    ('O.U.I',                ['O.U.I', 'OUI']),
    ('PAGSEGURO',            ['PAGSEGURO', 'PAG SEGURO']),
    ('PHARMAPELE',           ['PHARMAPELE']),
    ('PREGO CALCADOS',       ['PREGO CALCADOS', 'PREGO CALÇADOS']),
    ('PUKET',                ['PUKET']),
    # QDB = Quem Disse Berenice (com variações de grafia)
    ('QUEM DISSE BERENICE',  ['QUEM DISSE BERENICE', 'QUEM DISSE BERENISSE', 'QDB', 'BERENICE', 'BERENISSE']),
    ('RENNER',               ['RENNER']),
    ('RICHARDS',             ['RICHARDS']),
    ('SALINAS',              ['SALINAS']),
    ('SANTA LUZIA',          ['SANTA LUZIA']),
    ('SCALA TRIFIL',         ['SCALA TRIFIL', 'TRIFIL']),
    ('SCHUTZ',               ['SCHUTZ']),
    ('SEPHORA',              ['SEPHORA']),
    ('SHOPPING IBIRAPUERA',  ['SHOPPING IBIRAPUERA', 'IBIRAPUERA']),
    ('TO QUE TO',            ['TO QUE TO', 'TÔ QUE TÔ']),
    ('TOMMY',                ['TOMMY']),
    ('TRACK & FIELD COFFEE', ['TRACK & FIELD COFFEE', 'TF COFFEE']),
    ('TRACK & FIELD',        ['TRACK & FIELD', 'TRACK FIELD', 'TF']),
    ('V R',                  ['V R', 'VR ', ' VR']),
    ('VIVARA',               ['VIVARA']),
    ('VIVENDA DO CAMARAO',   ['VIVENDA DO CAMARAO', 'VIVENDA DO CAMARÃO', 'VIVENDA']),
    ('YOUCOM',               ['YOUCOM']),
]


# Subjects que NÃO são pedido fechado — ignorar inteiro
SUBJECTS_RUIDO = [
    'ALINHAMENTO',
    'AGENDAMENTO',
    'INFORME',
    'FYI',
    'REEDIÇÃO', 'REEDICAO',
    'REVISÃO', 'REVISAO', 'REVISADO',
]


# Palavras a remover do subject pra deixar só cliente+projeto
PALAVRAS_PROCESSO = [
    'PEDIDO FECHADO',
    'PEDIDO',
    'FECHADO',
    'VAREJO',
    'INSTITUCIONAL',
    'INST',
    'PROMOCIONAL',
    'PROMO',
    'PHASE IN', 'PHASE OUT', 'PHEASE IN', 'PHEASE OUT',
    'PHASE-IN', 'PHASE-OUT', 'PHEASE-IN', 'PHEASE-OUT',
    'NOVO PRODUTO',
    'NOVO',
]


# Prefixos de email a remover (RES:, RE:, FW:, ENC:)
_RE_PREFIXOS = re.compile(
    r'^\s*((RES|RE|FW|ENC|FWD|ENCAMINHAR):\s*)+',
    flags=re.IGNORECASE,
)


def _normalizar(s: str) -> str:
    """Maiúsculas, sem acento, espaços únicos."""
    if not s:
        return ''
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.upper()
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _limpar_subject(subject: str) -> str:
    """Remove prefixos (RES:/RE:/FW:) e palavras de processo."""
    s = _RE_PREFIXOS.sub('', subject or '')
    s_norm = _normalizar(s)
    # Remove palavras de processo (PEDIDO FECHADO, VAREJO, etc) com word boundary
    for palavra in PALAVRAS_PROCESSO:
        palavra_norm = _normalizar(palavra)
        s_norm = re.sub(
            rf'\b{re.escape(palavra_norm)}\b',
            ' ',
            s_norm,
        )
    s_norm = re.sub(r'\s+', ' ', s_norm).strip()
    return s_norm


def eh_subject_ruido(subject: str) -> bool:
    """True se o subject é ruído (ALINHAMENTO, REEDIÇÃO, etc)."""
    s_norm = _normalizar(subject)
    for r in SUBJECTS_RUIDO:
        if _normalizar(r) in s_norm:
            return True
    return False


def identificar_cliente_projeto(subject: str) -> tuple:
    """
    Identifica cliente e projeto a partir do subject.

    Returns:
        (cliente: str, projeto: str)
        Se não achar cliente, retorna ('', subject_limpo)

    Exemplos:
        'PEDIDO FECHADO VAREJO - SEPHORA - INSTITUCIONAL'
          → ('SEPHORA', '')   # INSTITUCIONAL é palavra-processo

        'PEDIDO FECHADO VAREJO - RENNER AGOSTO'
          → ('RENNER', 'AGOSTO')

        'RES: PEDIDO FECHADO VAREJO INST - SACL PAP AUT PRES DPSP - DROGARIA SAO PAULO'
          → ('DROGARIA SAO PAULO', 'SACL PAP AUT PRES')

        'BELEZA NA WEB - PHEASE IN / PHEASE OUT - PAPEL DE SEDA'
          → ('BELEZA NA WEB', 'PAPEL DE SEDA')
    """
    if not subject:
        return ('', '')

    s_limpo = _limpar_subject(subject)

    # Procura cada cliente. Pega o que tiver alias mais longo (mais específico)
    # pra evitar match parcial — ex: "BROOKSFIELD JR" tem que bater antes
    # de "BROOKSFIELD".
    achados = []  # (cliente_canonico, alias, posicao)
    for canonico, aliases in _CLIENTES_LISTA:
        for alias in aliases:
            alias_norm = _normalizar(alias)
            # Usa word boundary pra não pegar "RENNER" dentro de "RENNERIA"
            # Mas como aliases podem ter espaços, é mais simples buscar
            # rodeado de não-letra ou início/fim
            pattern = rf'(?:^|[^A-Z0-9]){re.escape(alias_norm)}(?:[^A-Z0-9]|$)'
            m = re.search(pattern, s_limpo)
            if m:
                achados.append((canonico, alias_norm, m.start()))

    if not achados:
        # Sem cliente — devolve o que sobrou como projeto
        # (pelo menos a Maria vê o que estava no subject)
        return ('', s_limpo.strip(' -/'))

    # Escolhe o cliente com alias MAIS LONGO (mais específico)
    achados.sort(key=lambda x: -len(x[1]))
    cliente, alias_usado, _ = achados[0]

    # Remove o alias do subject limpo pra extrair o projeto
    s_sem_cliente = re.sub(
        rf'(?:^|[^A-Z0-9]){re.escape(alias_usado)}(?:[^A-Z0-9]|$)',
        ' ',
        s_limpo,
    )
    # Limpa traços, barras, espaços
    projeto = re.sub(r'[-/]+', ' ', s_sem_cliente)
    projeto = re.sub(r'\s+', ' ', projeto).strip()

    return (cliente, projeto)


# ============================================================
# TESTES
# ============================================================
def _teste():
    casos = [
        # (subject, cliente_esperado, projeto_esperado)
        ('PEDIDO FECHADO VAREJO - SEPHORA - INSTITUCIONAL',
         'SEPHORA', ''),
        ('RES: PEDIDO FECHADO VAREJO - RENNER AGOSTO',
         'RENNER', 'AGOSTO'),
        ('RES: PEDIDO FECHADO VAREJO INST - SACL PAP AUT PRES DPSP - DROGARIA SÃO PAULO',
         'DROGARIA SAO PAULO', 'SACL PAP AUT PRES DPSP'),  # DPSP fica como rastro, OK
        ('BELEZA NA WEB - PHEASE IN / PHEASE OUT - PAPEL DE SEDA',
         'BELEZA NA WEB', 'PAPEL DE SEDA'),
        ('RES: PEDIDO FECHADO VAREJO - BOTICÁRIO - KIT PINS',
         'BOTICARIO', 'KIT PINS'),
        ('RES: PEDIDO FECHADO VAREJO - RENNER JUNHO/AGO',
         'RENNER', 'JUNHO AGO'),
        ('PEDIDO FECHADO - QUEM DISSE BERENISSE - FRIENDS',
         'QUEM DISSE BERENICE', 'FRIENDS'),
        ('PEDIDO FECHADO - QDB - CAIXA PRESS KIT',
         'QUEM DISSE BERENICE', 'CAIXA PRESS KIT'),
        # Casa Granado - variações de bandeira
        ('PEDIDO FECHADO - CASA GRANADO - PRESENTE NATAL',
         'CASA GRANADO', 'PRESENTE NATAL'),
        ('PEDIDO FECHADO - CASA GRANADO PHEBO - KIT MAES',
         'CASA GRANADO PHEBO', 'KIT MAES'),
        ('PEDIDO FECHADO - CASA GRANADO CARE - CREMES',
         'CASA GRANADO CARE', 'CREMES'),
        # Boticário variações
        ('PEDIDO FECHADO VAREJO - O BOTICÁRIO - EGOS REFIL',
         'BOTICARIO', 'EGOS REFIL'),
        # Loccitane
        ('PEDIDO FECHADO - LOCCITANE AU BRESIL - CESTA',
         'LOCCITANE', 'CESTA'),
        # Sem cliente conhecido
        ('PEDIDO ALEATORIO X Y Z',
         '', 'ALEATORIO X Y Z'),
    ]

    falhou = 0
    for subject, cli_esp, proj_esp in casos:
        cli, proj = identificar_cliente_projeto(subject)
        ok_cli = cli == cli_esp
        ok_proj = proj == proj_esp
        if not (ok_cli and ok_proj):
            falhou += 1
            print(f'✗ {subject!r}')
            print(f'  Esperado: cliente={cli_esp!r} projeto={proj_esp!r}')
            print(f'  Recebido: cliente={cli!r} projeto={proj!r}')
        else:
            print(f'✓ {subject[:60]}')
            print(f'  → cliente={cli!r} projeto={proj!r}')

    if falhou == 0:
        print(f'\n✓ {len(casos)} testes passaram!')
    else:
        print(f'\n✗ {falhou}/{len(casos)} falharam')

    # Testes de eh_subject_ruido
    print('\nTeste eh_subject_ruido:')
    assert eh_subject_ruido('RES: ALINHAMENTO DISPLAY FRIENDS - QDB/BOTICÁRIO')
    assert eh_subject_ruido('AGENDAMENTO REUNIAO')
    assert eh_subject_ruido('REEDIÇÃO - ACHÉ')
    assert eh_subject_ruido('FYI: produção')
    assert not eh_subject_ruido('PEDIDO FECHADO VAREJO - RENNER AGOSTO')
    print('✓ eh_subject_ruido OK')


if __name__ == '__main__':
    _teste()
