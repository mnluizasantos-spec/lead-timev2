"""
Parser principal — orquestra todos os módulos.

Uso:
    python -m parser.main "emails-*.json" dados.json [apontamentos.xlsx] [auditoria.json] [overrides.json]

Por padrão:
    - Lê todos os emails-*.json com glob
    - Agrupa por conversationId em threads
    - Processa cada thread → pedido
    - Enriquece com apontamentos.xlsx (se existir)
    - Aplica overrides.json (se existir)
    - Gera dados.json + auditoria.json
"""
import glob
import json
import sys
from collections import defaultdict
from datetime import datetime

from .processar import processar_thread
from .apontamentos import indexar_apontamentos, enriquecer_com_apontamentos
from .overrides import carregar_overrides, aplicar_overrides


def carregar_emails_de_arquivos(padrao_glob: str) -> list:
    """
    Lê todos os arquivos JSON que casam com o padrão e retorna lista de emails.
    Aceita arquivos no formato:
      - [email1, email2, ...]
      - {"value": [email1, email2, ...]}
    """
    arquivos = sorted(glob.glob(padrao_glob))
    if not arquivos:
        print(f'⚠️  Nenhum arquivo encontrado pra "{padrao_glob}"')
        return []

    print(f'📂 Lendo {len(arquivos)} arquivo(s) de emails')
    emails = []
    for arq in arquivos:
        try:
            with open(arq, encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f'  ⚠️  Erro ao ler {arq}: {e}')
            continue

        if isinstance(data, list):
            lista = data
        elif isinstance(data, dict) and 'value' in data:
            lista = data['value']
        else:
            print(f'  ⚠️  Formato desconhecido em {arq}')
            continue

        print(f'  · {arq}: {len(lista)} email(s)')
        emails.extend(lista)

    print(f'📧 Total: {len(emails)} email(s)')
    return emails


def agrupar_por_thread(emails: list) -> dict:
    """
    Agrupa emails por conversationId (ou subject normalizado como fallback).
    Returns: {thread_id: [lista_de_emails]}
    """
    threads = defaultdict(list)
    for email in emails:
        tid = email.get('conversationId') or email.get('id') or ''
        if not tid:
            # Fallback: usa subject normalizado
            subj = email.get('subject', '').upper()
            subj = subj.replace('RES:', '').replace('RE:', '').replace('FW:', '').strip()
            tid = f'fallback:{subj[:80]}'
        threads[tid].append(email)
    return dict(threads)


def main(
    padrao_emails='emails-*.json',
    output_dados='dados.json',
    apontamentos_path=None,
    output_auditoria='auditoria.json',
    overrides_path='overrides.json',
):
    print('='*60)
    print(f'PARSER V2 — {datetime.now().isoformat(timespec="seconds")}')
    print('='*60)

    # 1. Carrega emails
    emails = carregar_emails_de_arquivos(padrao_emails)
    if not emails:
        print('Nenhum email pra processar.')
        return

    # 2. Agrupa por thread
    threads = agrupar_por_thread(emails)
    print(f'🧵 {len(threads)} thread(s) únicas')

    # 3. Processa cada thread
    auditoria = {
        'gerado_em': datetime.now().isoformat(timespec='seconds'),
        'total_emails': len(emails),
        'total_threads': len(threads),
        'marcos_rejeitados': [],
        'threads_sem_pedido_fechado': [],
        'remetentes_desconhecidos': set(),
        'reedicoes_ignoradas': [],
    }

    pedidos = []
    for thread_id, emails_thread in threads.items():
        pedido = processar_thread(emails_thread, auditoria)
        if pedido is not None:
            pedidos.append(pedido)

    print(f'✅ {len(pedidos)} pedido(s) com pedido_fechado válido')
    print(f'⚠️  {len(auditoria["threads_sem_pedido_fechado"])} thread(s) sem pedido_fechado (auditoria)')
    print(f'⚠️  {len(auditoria["marcos_rejeitados"])} marco(s) rejeitado(s) por papel')
    print(f'🚫 {len(auditoria["reedicoes_ignoradas"])} reedicao/revisao ignorada(s)')

    # 4. Apontamentos (se informado)
    if apontamentos_path:
        print(f'\n📊 Lendo apontamentos: {apontamentos_path}')
        indice = indexar_apontamentos(apontamentos_path)
        print(f'   {len(indice)} código(s) com apontamentos')

        pedidos_enriquecidos = []
        for p in pedidos:
            pedidos_enriquecidos.append(enriquecer_com_apontamentos(p, indice))
        pedidos = pedidos_enriquecidos

        com_producao = sum(1 for p in pedidos if p['marcos']['producao']['real'])
        print(f'   {com_producao} pedido(s) com produção identificada')

    # 5. Overrides (se informado)
    if overrides_path:
        print(f'\n🔒 Aplicando overrides: {overrides_path}')
        overrides = carregar_overrides(overrides_path)
        if overrides:
            print(f'   {len(overrides)} override(s) configurado(s)')
            pedidos = [aplicar_overrides(p, overrides) for p in pedidos]

    # 6. Ordena pedidos por data de pedido_fechado (mais recente primeiro)
    pedidos.sort(
        key=lambda p: p['marcos']['pedido_fechado']['real'] or '0000-00-00',
        reverse=True
    )

    # 7. Salva dados.json
    print(f'\n💾 Salvando {output_dados}')
    with open(output_dados, 'w', encoding='utf-8') as f:
        json.dump(pedidos, f, ensure_ascii=False, indent=2, default=str)

    # 8. Salva auditoria.json
    auditoria['remetentes_desconhecidos'] = sorted(auditoria['remetentes_desconhecidos'])
    print(f'💾 Salvando {output_auditoria}')
    with open(output_auditoria, 'w', encoding='utf-8') as f:
        json.dump(auditoria, f, ensure_ascii=False, indent=2, default=str)

    # 9. Resumo final
    print('\n' + '='*60)
    print(f'CONCLUÍDO: {len(pedidos)} pedido(s) → {output_dados}')
    print('='*60)


if __name__ == '__main__':
    args = sys.argv[1:]
    kwargs = {}

    # Args posicionais com defaults
    if len(args) >= 1: kwargs['padrao_emails'] = args[0]
    if len(args) >= 2: kwargs['output_dados'] = args[1]
    if len(args) >= 3: kwargs['apontamentos_path'] = args[2]
    if len(args) >= 4: kwargs['output_auditoria'] = args[3]
    if len(args) >= 5: kwargs['overrides_path'] = args[4]

    main(**kwargs)
