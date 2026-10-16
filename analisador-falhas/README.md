# 🔧 Analisador de histórico de falhas

Aplicativo que lê o histórico de **ordens de serviço (OS)** de manutenção, calcula os
indicadores do PCM e usa **IA (Claude)** para apontar os principais problemas e sugerir ações.

Feito pensando em um frigorífico (túneis de congelamento, compressores de amônia,
linhas de abate e desossa, embalagem), mas funciona com OS de qualquer indústria.

## O que ele faz

| Aba | O que mostra |
|---|---|
| **Equipamentos** | Falhas, horas paradas, **MTTR**, **MTBF** e **disponibilidade** de cada equipamento |
| **Pareto** | Os equipamentos que concentram 80% das falhas (ou das horas paradas) |
| **Falhas repetitivas** | Mesmo componente do mesmo equipamento quebrando várias vezes: candidatos a análise de causa raiz |
| **Evolução mensal** | Corretivas × preventivas × preditivas ao longo dos meses |
| **Análise com IA** | O Claude lê os indicadores e escreve um resumo com problemas e ações recomendadas |
| **Ordens de serviço** | A tabela completa, já filtrada |

Dá para filtrar por **área** e **período**, e ajustar as **horas de operação por dia**.

## Como rodar

Você precisa do **Python 3.10 ou mais novo** ([python.org](https://www.python.org/downloads/)).
No terminal, dentro da pasta `analisador-falhas`:

**Windows (Prompt de Comando):**

```bat
:: 1. Crie um ambiente virtual (uma "caixinha" só para as bibliotecas deste projeto)
python -m venv .venv

:: 2. Ative o ambiente (aparece "(.venv)" no começo da linha)
.venv\Scripts\activate

:: 3. Instale as bibliotecas
python -m pip install -r requirements.txt

:: 4. Abra o aplicativo (ele abre sozinho no navegador)
streamlit run app.py
```

**Linux / Mac:**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```

Da próxima vez, basta repetir os passos 2 e 4.

O app já vem com **dados de exemplo fictícios** (6 meses de OS de um frigorífico
inventado), então dá para explorar tudo sem ter planilha nenhuma.

### Para usar a análise com IA

1. Crie uma conta em [console.anthropic.com](https://console.anthropic.com) e gere uma **chave de API**.
2. Cole a chave na barra lateral do app, **ou** deixe ela numa variável de ambiente antes de abrir:
   ```bash
   export ANTHROPIC_API_KEY="sua-chave-aqui"     # Linux / Mac
   set ANTHROPIC_API_KEY=sua-chave-aqui          # Windows
   ```

O uso da API é pago por consumo. Cada análise envia um texto pequeno, então o custo
por análise é baixo, mas acompanhe o gasto no console da Anthropic.

## Usando a sua planilha

Escolha **"Minha planilha"** na barra lateral e envie um arquivo **CSV** ou **Excel (.xlsx)**,
com **uma OS por linha**. Se os nomes das colunas forem diferentes dos esperados, o
app pergunta qual coluna é qual.

O jeito mais fácil é usar o **modelo pronto**: [`modelo/modelo_ordens_de_servico.xlsx`](modelo/modelo_ordens_de_servico.xlsx)
(também dá para baixar pelo botão "Baixar modelo de planilha" no app). Ele já tem a
lista de tipos de manutenção, validação de data e horas e uma aba de instruções.

| Coluna | Obrigatória? | Exemplo |
|---|---|---|
| Equipamento | ✅ | Túnel de congelamento 02 |
| Tipo de manutenção | ✅ | Corretiva, Preventiva, Preditiva |
| Data | ✅ | 03/04/2026 |
| Horas apontadas | ✅ | 2,5 (= 2h30; também aceita 2:30) |
| Número da OS | | 100234567 |
| Área | | Congelamento |
| Componente | | Ventilador do evaporador |
| Descrição do serviço | | Motor do ventilador queimado, substituído |

> ⚠️ **Não suba dados reais da empresa no GitHub** e peça autorização antes de enviar
> dados internos para serviços de IA. Para o portfólio, use os dados fictícios.

## Como os indicadores são calculados

Só as OS **corretivas** contam como falha. As **horas apontadas** em cada corretiva são
consideradas tempo de equipamento parado.

> Se as horas apontadas forem **homem-hora** (soma de vários técnicos na mesma OS), o
> MTTR vai parecer maior que a parada real. Se o seu sistema tiver as horas de parada do
> equipamento, prefira essa informação na coluna "Horas apontadas".

- **Horas planejadas** = dias do período × horas de operação por dia
- **MTTR** (tempo médio para reparar) = horas paradas ÷ número de falhas
- **MTBF** (tempo médio entre falhas) = (horas planejadas − horas paradas) ÷ número de falhas
- **Disponibilidade** = (horas planejadas − horas paradas) ÷ horas planejadas
- **Pareto, classe A** = os itens que, somados do maior para o menor, chegam a 80% do total

## Como o código está organizado

```
analisador-falhas/
├── app.py                  # a tela (Streamlit): filtros, abas, gráficos
├── indicadores.py          # as contas: MTBF, MTTR, Pareto, falhas repetitivas
├── graficos.py             # os gráficos (Altair)
├── ia.py                   # o pedido para o Claude (API da Anthropic)
├── gerar_dados_exemplo.py  # cria os dados fictícios
├── dados/os_exemplo.csv    # os dados fictícios prontos
├── modelo/                 # modelo de planilha (Excel) para preencher
└── tests/                  # testes automáticos das contas
```

Cada arquivo tem uma responsabilidade. As contas ficam separadas da tela e da IA, e
por isso dá para testá-las sozinhas:

```bash
pytest
```

## Ideias para evoluir (bons exercícios)

- [ ] Adicionar **custo** (peças + mão de obra) e fazer o Pareto por custo.
- [ ] Mostrar o **backlog**: OS abertas e há quantos dias estão esperando.
- [ ] Deixar o usuário **conversar** com a IA sobre os dados ("e o compressor 01?").
- [ ] Gerar um **relatório em PDF** para a reunião semanal de manutenção.
- [ ] Publicar o app no [Streamlit Community Cloud](https://streamlit.io/cloud) e colocar o link no portfólio.
