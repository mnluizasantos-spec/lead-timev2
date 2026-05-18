"""
Teste integrado: processa o email REAL do FRIENDS e verifica saída.
"""
import json
import sys
from pathlib import Path

# Adiciona o diretório pai pra importar o parser
sys.path.insert(0, str(Path(__file__).parent.parent))

from parser.processar import processar_thread


def teste_friends():
    # Carrega o email real exportado do .msg do FRIENDS
    emails_path = Path(__file__).parent / 'test_data' / 'emails-2026-05-15.json'
    with open(emails_path, encoding='utf-8') as f:
        emails = json.load(f)

    print(f'Carregados {len(emails)} email(s) do FRIENDS')

    auditoria = {
        'marcos_rejeitados': [],
        'threads_sem_pedido_fechado': [],
        'remetentes_desconhecidos': set(),
    }

    pedido = processar_thread(emails, auditoria)

    print('\n=== PEDIDO PROCESSADO ===')
    if pedido is None:
        print('❌ Retornou None')
        print(f'\nAuditoria: {json.dumps(auditoria, default=list, indent=2, ensure_ascii=False)}')
        return False

    print(json.dumps(pedido, indent=2, ensure_ascii=False))

    print('\n=== ASSERÇÕES ===')

    # 1. Detectou cliente
    assert pedido['cliente'] is not None, 'cliente'
    assert 'BERENISSE' in pedido['cliente'].upper() or 'FRIENDS' in pedido['cliente'].upper(), pedido['cliente']
    print('✓ cliente detectado:', pedido['cliente'])

    # 2. Tem CRONOGRAMA
    assert pedido['tem_cronograma'], 'cronograma não detectado'
    print('✓ cronograma detectado')

    # 3. Datas previstas corretas (extraídas do CRONOGRAMA do email)
    assert pedido['marcos']['data_vitrine']['previsto']   == '2026-07-17'
    assert pedido['marcos']['pedido_fechado']['previsto'] == '2026-05-14'
    assert pedido['marcos']['fert_criado']['previsto']    == '2026-05-15'
    assert pedido['marcos']['op_liberada']['previsto']    == '2026-05-27'
    assert pedido['marcos']['producao']['previsto']       == '2026-06-19'
    print('✓ datas previstas do cronograma corretas')

    # 4. Tem datas reais de pedido_fechado e fert_criado
    assert pedido['marcos']['pedido_fechado']['real'] is not None, 'pedido real None'
    assert pedido['marcos']['fert_criado']['real'] is not None, 'fert real None'
    print('✓ datas reais detectadas:',
          'pedido', pedido['marcos']['pedido_fechado']['real'],
          '/ fert', pedido['marcos']['fert_criado']['real'])

    # 5. Status: aguardando OP (tem fert, não tem op)
    assert pedido['status'] == 'aguardando_op', pedido['status']
    print('✓ status:', pedido['status'])

    # 6. SKUs: o email do FRIENDS tem múltiplas tabelas (10 SKUs ao todo)
    # Verifica que detectou pelo menos os 3 primeiros (FERT + 2 HALBs).
    codigos = [s['codigo'] for s in pedido['skus']]
    assert len(codigos) >= 3, f'esperava 3+ SKUs, achou {len(codigos)}'
    ferts = [s['codigo'] for s in pedido['skus'] if s['tipo'] == 'FERT']
    halbs = [s['codigo'] for s in pedido['skus'] if s['tipo'] == 'HALB']
    assert len(ferts) >= 1, f'sem FERT: {codigos}'
    assert len(halbs) >= 1, f'sem HALB: {codigos}'
    print(f'✓ SKUs detectados: {len(ferts)} FERT + {len(halbs)} HALB = {len(codigos)} total')

    # 7. Lead times calculados (a partir do CRONOGRAMA do email)
    lt = pedido['lead_times']
    assert lt['pedido_para_fert']['previsto'] == 1, f'pedido→fert previsto: {lt["pedido_para_fert"]}'
    assert lt['pedido_para_fert']['real'] == 1, f'pedido→fert real: {lt["pedido_para_fert"]}'
    assert lt['fert_para_op']['previsto'] == 12, f'fert→op previsto: {lt["fert_para_op"]}'
    assert lt['op_para_producao']['previsto'] == 23, f'op→prod previsto: {lt["op_para_producao"]}'
    print('✓ lead times:',
          'pedido→fert', lt['pedido_para_fert'],
          '· fert→op', lt['fert_para_op'])

    print('\n🎉 TODOS OS TESTES PASSARAM ✓')
    return True


if __name__ == '__main__':
    sucesso = teste_friends()
    sys.exit(0 if sucesso else 1)
