"""
Aplicação de overrides manuais (cancelados, ocultos).

O arquivo `overrides.json` tem a forma:

    {
      "thread_id_xyz": {
        "status_manual": "cancelado",   // ou "oculto"
        "motivo": "Cliente desistiu",
        "por": "Maria",
        "data": "2026-05-18"
      },
      ...
    }

A função `aplicar_overrides` lê esse arquivo e aplica nos pedidos:
- "cancelado" → status vira 'cancelado' (vai pra seção própria do dashboard)
- "oculto"    → adiciona flag `oculto: true` (frontend filtra)
"""
import json
import os
from .papeis import STATUS_CANCELADO, RESPONSAVEL_POR_STATUS


def carregar_overrides(overrides_path: str) -> dict:
    """
    Carrega overrides.json. Retorna {} se arquivo não existir.
    """
    if not overrides_path or not os.path.exists(overrides_path):
        return {}
    try:
        with open(overrides_path, encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f'  ⚠️  Erro ao ler {overrides_path}: {e}')
        return {}


def aplicar_overrides(pedido: dict, overrides: dict) -> dict:
    """
    Aplica override manual no pedido (se houver).

    Returns:
        Pedido (modificado se override aplicado, ou inalterado).
    """
    if not overrides:
        return pedido

    pedido_id = pedido.get('pedido_id')
    if not pedido_id:
        return pedido

    ov = overrides.get(pedido_id)
    if not ov:
        return pedido

    status_manual = ov.get('status_manual')

    if status_manual == 'cancelado':
        pedido['status'] = STATUS_CANCELADO
        pedido['responsavel_atual'] = RESPONSAVEL_POR_STATUS[STATUS_CANCELADO]
        pedido['cancelado_info'] = {
            'motivo': ov.get('motivo'),
            'por': ov.get('por'),
            'data': ov.get('data'),
        }

    elif status_manual == 'oculto':
        pedido['oculto'] = True
        pedido['oculto_info'] = {
            'por': ov.get('por'),
            'data': ov.get('data'),
        }

    return pedido
