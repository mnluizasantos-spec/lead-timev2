"""
Papéis dos remetentes e constantes globais do parser.

Cada marco do pedido só é aceito se vem do papel certo:
- pedido_fechado, pedido_revisado → comercial
- ferts_criados, ops_liberadas     → engenharia

Pessoas fora do fluxo (PLD, S&OP) ficam em 'excluido'.
"""

# ============================================================
# PESSOAS POR PAPEL
# ============================================================
COMERCIAL_KEYWORDS = [
    'wesley.matheus', 'gleicy.maia', 'julio',
    'eduarda.santos', 'lucineia.rodrigues', 'neila.duarte',
    'pedidofechado_varejo', 'atendimentoaocliente', 'comercial',
]
COMERCIAL_NOMES = [
    'WESLEY', 'GLEICY', 'JULIO', 'JÚLIO',
    'EDUARDA', 'LUCINEIA', 'LUCINÉIA', 'NEILA',
    'DUARTE', 'MAIA',
]

ENGENHARIA_KEYWORDS = [
    'gabriel.alcantara', 'ariane.luz', 'leticia.santos', 'giovanna.alves',
    'engenhariadeprodutos', 'engenharia',
]
ENGENHARIA_NOMES = [
    'GABRIEL', 'ARIANE', 'LETICIA', 'LETÍCIA', 'GIOVANNA',
    'ALCANTARA', 'ALCÂNTARA', 'LUZ', 'ALVES',
]

EXCLUIDOS_KEYWORDS = [
    'cassia.cavaleiro', 'tamirys.nogueira', 'matheus.garcia',
]
EXCLUIDOS_NOMES = [
    'CASSIA', 'CÁSSIA', 'CAVALEIRO',
    'TAMIRYS', 'NOGUEIRA',
    'MATHEUS GARCIA', 'GARCIA',
]


def papel_do_remetente(remetente: str) -> str:
    """
    Retorna 'comercial', 'engenharia', 'excluido' ou 'desconhecido'.

    Excluídos têm prioridade pra não confundir 'MATHEUS GARCIA' (excluido)
    com 'WESLEY MATHEUS' (comercial).
    """
    if not remetente:
        return 'desconhecido'
    s_lower = str(remetente).lower()
    s_upper = str(remetente).upper()
    if any(kw in s_lower for kw in EXCLUIDOS_KEYWORDS):
        return 'excluido'
    if any(nome in s_upper for nome in EXCLUIDOS_NOMES):
        return 'excluido'
    if any(kw in s_lower for kw in COMERCIAL_KEYWORDS):
        return 'comercial'
    if any(nome in s_upper for nome in COMERCIAL_NOMES):
        return 'comercial'
    if any(kw in s_lower for kw in ENGENHARIA_KEYWORDS):
        return 'engenharia'
    if any(nome in s_upper for nome in ENGENHARIA_NOMES):
        return 'engenharia'
    return 'desconhecido'


# ============================================================
# MARCOS E PAPEL EXIGIDO
# ============================================================
PAPEL_EXIGIDO = {
    'pedido_fechado':  'comercial',
    'pedido_revisado': 'comercial',
    'ferts_criados':   'engenharia',
    'ops_liberadas':   'engenharia',
}

# Marcos na ordem do fluxo
ORDEM_MARCOS = ['pedido_fechado', 'ferts_criados', 'ops_liberadas', 'producao']


# ============================================================
# STATUS DO PEDIDO
# ============================================================
STATUS_AGUARDANDO_FERT = 'aguardando_fert'
STATUS_AGUARDANDO_OP   = 'aguardando_op'
STATUS_EM_PRODUCAO     = 'em_producao'
STATUS_CONCLUIDO       = 'concluido'
STATUS_CANCELADO       = 'cancelado'
STATUS_COMPRAVEL       = 'compravel'         # compra pronto, não passa por OP/produção
STATUS_AGUARDA_CRONOGRAMA = 'aguarda_crono'  # pedido fechado mas sem cronograma ainda

RESPONSAVEL_POR_STATUS = {
    STATUS_AGUARDANDO_FERT:     'Engenharia',
    STATUS_AGUARDANDO_OP:       'Engenharia',
    STATUS_EM_PRODUCAO:         'PCP/Fábrica',
    STATUS_CONCLUIDO:           '-',
    STATUS_CANCELADO:           '-',
    STATUS_COMPRAVEL:           'Compras',
    STATUS_AGUARDA_CRONOGRAMA:  'Comercial',
}

# ============================================================
# REGRAS DE TIPO DE PEDIDO POR PREFIXO DO CÓDIGO FERT
# ============================================================
# Codigo FERT formato 'XXXXXXXX-YYYY' (8 dígitos + hífen + 4 dígitos).
# Os 2 primeiros dígitos indicam o tipo de produto:
#   15 → compravel (compra pronto, sem OP/Produção)
PREFIXOS_FERT_COMPRAVEL = ('15',)


def eh_fert_compravel(codigo: str) -> bool:
    """Retorna True se o FERT é tipo 'compravel' (compra pronto)."""
    if not codigo:
        return False
    return str(codigo).startswith(PREFIXOS_FERT_COMPRAVEL)


def todos_skus_compraveis(skus: list) -> bool:
    """
    Retorna True se TODOS os FERTs do pedido são compraveis.
    HALBs não contam (são insumos).
    """
    ferts = [s for s in (skus or []) if s.get('tipo') == 'FERT']
    if not ferts:
        return False
    return all(eh_fert_compravel(s.get('codigo')) for s in ferts)
