# Lead Time Antilhas — v2

Dashboard de acompanhamento de pedidos do Pedido Fechado até a Produção,
medindo lead time entre etapas vs cronograma previsto no email.

## Estrutura

```
.
├── parser/                    Parser em Python (modular)
│   ├── papeis.py              Pessoas e papéis (comercial/engenharia)
│   ├── utils.py               HTML→texto, datas, normalizações
│   ├── cronograma.py          Extrai tabela CRONOGRAMA do email
│   ├── marcos.py              Detecta marcos (pedido_fechado, ferts_criados, …)
│   ├── skus.py                Extrai FERTs e HALBs
│   ├── threads.py             Split de quotes aninhados (RES: …)
│   ├── processar.py           Processa uma thread → pedido
│   ├── apontamentos.py        Cruza com apontamentos.xlsx
│   ├── overrides.py           Aplica cancelados/ocultos
│   └── main.py                Orquestrador (entrypoint)
│
├── .github/workflows/
│   └── processar.yml          GitHub Action: roda parser quando arquivos mudam
│
├── emails-2026-MM-DD.json     Emails do dia (criados pelo Power Automate)
├── apontamentos.xlsx          Exportado do shop floor (upload manual)
├── overrides.json             Cancelados/ocultos manuais (com senha)
│
├── dados.json                 Saída do parser (lido pelo frontend)
└── auditoria.json             Marcos rejeitados, threads sem pedido_fechado, etc.
```

## Fluxo

1. **Power Automate** roda todo dia 7h:
   - Lê emails do Outlook (pasta `PCP_Dashboard`)
   - Cria um arquivo `emails-YYYY-MM-DD.json` por dia (nunca sobrescreve)
   - Commit no GitHub via API

2. **GitHub Action** dispara automaticamente quando arquivo muda:
   - Roda `python -m parser.main`
   - Lê todos os `emails-*.json` (glob)
   - Gera `dados.json` consolidado
   - Commit do resultado

3. **Frontend** (Netlify, repo separado):
   - Lê `dados.json` direto do raw.githubusercontent.com
   - Renderiza dashboard

## Como rodar localmente

```bash
pip install -r requirements.txt
python -m parser.main "emails-*.json" dados.json apontamentos.xlsx
```

## Status do pedido (5 estados)

| Status              | Quando                                  |
|---------------------|-----------------------------------------|
| `aguardando_fert`   | Pedido fechado, sem FERT criado         |
| `aguardando_op`     | FERT criado, sem OP liberada            |
| `em_producao`       | OP liberada / apontamento iniciado      |
| `concluido`         | Produção finalizada                     |
| `cancelado`         | Override manual com senha               |

## Marcos do pedido (5 marcos)

| Marco              | Quem        | Como detectar                              |
|--------------------|-------------|--------------------------------------------|
| Pedido fechado     | Comercial   | Email com "SETOR DE ATIVIDADE"             |
| FERT criado        | Engenharia  | "@cadastrar" / "transferir plano"          |
| OP liberada        | Engenharia  | "OPs liberadas"                            |
| Produção           | PCP/Fábrica | 1º apontamento do FERT ou HALB             |
| Data vitrine       | Cliente     | Campo "Data Vitrine" do CRONOGRAMA         |

## Cronograma

A partir de 15/05/2026, emails de pedido fechado têm uma tabela
**CRONOGRAMA — PEDIDO FECHADO VAREJO** com as 5 datas previstas:

```
# MARCO            DATA PREVISTA   OBSERVAÇÕES
1 Data Vitrine     17/07/2026      Quando o produto precisa estar em loja
2 Pedido Fechado   14/05/2026      Data prevista de envio pela Comercial
3 FERT criado      15/05/2026      Cadastro / transferência de plano
4 OP liberada      26/05/2026      Liberação da Ordem de Produção
5 Produção         19/06/2026      Conclusão da produção pelo PCP/Fábrica
```

O parser extrai essas datas e as compara com as datas reais (vindas dos
marcos detectados nos emails + apontamentos), calculando aderência ao plano.

## Lead times

Calculados entre etapas consecutivas (não cumulativo):

- Pedido → FERT
- FERT → OP
- OP → Produção
- Produção → Vitrine

Cada lead time tem: `previsto` (do cronograma), `real` (das datas detectadas),
`desvio` (real − previsto).

## Testes

```bash
python -m parser.cronograma   # testes do cronograma
python -m parser.marcos       # testes da detecção de marcos
python -m parser.skus         # testes de extração de SKUs
python -m parser.threads      # testes do split de threads
python test_friends.py        # teste integrado end-to-end
```
