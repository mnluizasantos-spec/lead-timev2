"""
Utilidades comuns: HTML→texto, parse de datas, normalizações.
"""
import re
from datetime import datetime
from html.parser import HTMLParser
from html import unescape

MESES_PT = {
    'janeiro': 1, 'fevereiro': 2, 'março': 3, 'marco': 3, 'abril': 4,
    'maio': 5, 'junho': 6, 'julho': 7, 'agosto': 8,
    'setembro': 9, 'outubro': 10, 'novembro': 11, 'dezembro': 12
}


# ============================================================
# HTML → TEXTO
# ============================================================
class _HTMLToText(HTMLParser):
    """
    Converte HTML em texto preservando estrutura básica (linhas, tabs).
    Tags <p>, <div>, <tr>, <li>, <br> viram quebra de linha; <td>/<th> viram tab.
    """
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip = False
        self.last_was_block = True

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in ('style', 'script', 'head'):
            self.skip = True
        if tag in ('p', 'div', 'br', 'tr', 'li'):
            if not self.last_was_block:
                self.text.append('\n')
                self.last_was_block = True
        if tag in ('td', 'th'):
            self.text.append('\t')

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ('style', 'script', 'head'):
            self.skip = False
        if tag in ('p', 'div', 'tr', 'li'):
            self.text.append('\n')
            self.last_was_block = True

    def handle_data(self, data):
        if self.skip:
            return
        d = data.strip()
        if d:
            self.text.append(d)
            self.text.append(' ')
            self.last_was_block = False

    def get_text(self):
        s = ''.join(self.text)
        s = unescape(s)
        s = re.sub(r'[ \t]+', ' ', s)
        s = re.sub(r'\n[ \t]+', '\n', s)
        s = re.sub(r'\n{3,}', '\n\n', s)
        # Junta dígitos isolados que ficaram separados por espaços/quebras
        # devido a HTML mal formatado (ex: "<span>1</span><span>8</span>/05/2026"
        # vira "1 8 /05/2026" → corrige pra "18/05/2026"):
        # 1) "DD / DD / YYYY" (com espaços ao redor das barras) → "DD/DD/YYYY"
        s = re.sub(r'(\d)\s*/\s*(\d)', r'\1/\2', s)
        # 2) Junta dígitos adjacentes separados só por espaço, dentro de uma
        #    sequência numérica (data ou número): "1 8/05/2026" → "18/05/2026"
        #    Aplicamos só quando o resultado seria uma data válida.
        s = re.sub(r'\b(\d)\s+(\d)(/\d{1,2}/\d{4})', r'\1\2\3', s)
        s = re.sub(r'(\d{1,2}/)(\d)\s+(\d)(/\d{4})', r'\1\2\3\4', s)
        s = re.sub(r'(\d{1,2}/\d{1,2}/)(\d)\s+(\d{3})', r'\1\2\3', s)
        return s.strip()


def html_to_text(html: str) -> str:
    """Converte HTML em texto. Fallback robusto em caso de HTML mal formado."""
    if not html:
        return ''
    try:
        p = _HTMLToText()
        p.feed(html)
        return p.get_text()
    except Exception:
        s = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        s = re.sub(r'<script[^>]*>.*?</script>', '', s, flags=re.DOTALL | re.IGNORECASE)
        s = re.sub(r'<[^>]+>', ' ', s)
        s = unescape(s)
        s = re.sub(r'\s+', ' ', s)
        return s.strip()


# ============================================================
# PARSE DE DATAS
# ============================================================
def parse_data_pt(texto: str):
    """
    Parse de data em formato 'Enviada em: 14 de maio de 2026 15:54'.
    Retorna datetime ou None.
    """
    if not texto:
        return None
    m = re.search(r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})\s+(\d{1,2}):(\d{2})',
                  texto, re.IGNORECASE)
    if not m:
        return None
    dia, mes_nome, ano, hora, minuto = m.groups()
    mes = MESES_PT.get(mes_nome.lower())
    if not mes:
        return None
    try:
        return datetime(int(ano), mes, int(dia), int(hora), int(minuto))
    except ValueError:
        return None


def parse_iso(s):
    """Parse de data ISO 8601 (com ou sem timezone). Retorna datetime naive."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace('Z', '+00:00'))
        # Remove tzinfo pra trabalhar sempre em naive
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    except Exception:
        return None


def parse_data_curta(texto: str):
    """
    Parse de data em formato DD/MM/YYYY (usado no CRONOGRAMA do email).
    Retorna date (sem hora) ou None.
    """
    if not texto:
        return None
    m = re.search(r'(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{4})', texto)
    if not m:
        return None
    dia, mes, ano = m.groups()
    try:
        return datetime(int(ano), int(mes), int(dia)).date()
    except ValueError:
        return None


# ============================================================
# NORMALIZAÇÕES
# ============================================================
def limpar_remetente(s):
    """Remove '<email@dominio>' do nome do remetente."""
    if not s:
        return ""
    s = str(s)
    m = re.match(r'^([^<]+?)\s*<', s)
    return (m.group(1) if m else s).strip()


def normalizar_remetente_dedup(r: str) -> str:
    """Normaliza pra dedup: lowercase + remove sufixo de domínio."""
    if not r:
        return ''
    s = str(r).lower().strip()
    s = re.sub(r'@antilhas\.com\.br$', '', s)
    s = re.sub(r'\s+', ' ', s)
    return s


def extrair_cliente_do_subject(subject: str):
    """
    Extrai nome do cliente de 'PEDIDO FECHADO VAREJO - NOME DO CLIENTE'.
    Retorna string ou None.
    """
    if not subject:
        return None
    s = re.sub(r'^(RES:|RE:|FW:|ENC:)\s*', '', subject, flags=re.IGNORECASE).strip()
    m = re.search(r'PEDIDO\s+FECHADO\s+VAREJO\s*[-–—]\s*(.+)', s, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def diferenca_dias(dt_inicio, dt_fim) -> int:
    """
    Retorna diferença em DIAS CORRIDOS (não úteis) entre 2 datas/datetimes.
    Aceita date ou datetime. Retorna 0 se algum for None.
    """
    if dt_inicio is None or dt_fim is None:
        return 0
    # Normaliza pra date (ignora hora)
    if hasattr(dt_inicio, 'date'):
        dt_inicio = dt_inicio.date()
    if hasattr(dt_fim, 'date'):
        dt_fim = dt_fim.date()
    return (dt_fim - dt_inicio).days
