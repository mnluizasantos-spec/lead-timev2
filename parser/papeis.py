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

RESPONSAVEL_POR_STATUS = {
    STATUS_AGUARDANDO_FERT: 'Engenharia',
    STATUS_AGUARDANDO_OP:   'Engenharia',
    STATUS_EM_PRODUCAO:     'PCP/Fábrica',
    STATUS_CONCLUIDO:       '-',
    STATUS_CANCELADO:       '-',
}
