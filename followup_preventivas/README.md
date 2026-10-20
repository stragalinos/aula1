# Follow-up de peças para manutenção (TracOS)

Cruza as 3 exportações do TracOS (requisição, fluxo e pedido de compra) e gera uma planilha Excel com a etapa da compra de cada peça de cada OS, o risco de não chegar até a data de necessidade e quem cobrar.

## Como usar

1. Exporte do TracOS os 3 relatórios e salve na pasta `bases`:
   - `requisição de compra *.csv`
   - `fluxo de compras *.csv`
   - `pedido de compra *.csv`

   O número no fim do nome pode mudar. Se houver mais de um arquivo do mesmo tipo, o script usa o mais recente. Pode apagar os antigos.
2. Dê dois cliques em **`atualizar_followup.bat`**. Também dá para rodar `python atualizar_followup.py` no terminal.
3. A planilha abre sozinha. Ela fica salva em `saida/followup_preventivas_AAAA-MM-DD.xlsx`.

Na primeira vez, o `.bat` instala as bibliotecas `pandas` e `openpyxl`. Para isso, o Python precisa estar instalado com a opção "Add python.exe to PATH" marcada.

## O que é preservado entre atualizações

- **Observações:** o que você escrever na coluna amarela `Observação / Follow-up` (abas Follow-up, Por OS, Por Fornecedor e Divergências) volta na próxima versão.
  - No Follow-up, a chave é *material | requisição | OS*.
  - Se o item sumir das bases, a observação não se perde: ela vai para a aba Divergências como `OBSERVAÇÃO SEM ITEM ATUAL`.
- **Parâmetros:** os limites X, Y, Z e os nomes de quem cobrar, editados na aba Parâmetros.
- **Histórico de etapas** (aba oculta `_historico`): o TracOS não informa quando um item foi autorizado. Por isso o script guarda a primeira vez que viu cada item em cada etapa e usa essa data em "Dias na etapa atual".

O script sempre lê a planilha mais recente da pasta `saida`. **Escreva as observações na versão mais nova** antes de atualizar.

## Abas

| Aba | Conteúdo |
|---|---|
| Painel | Funil por etapa, itens por status de risco, OS preventivas com peças pendentes em 7/15/30 dias, ranking de fornecedores atrasados e de requisições paradas |
| Follow-up | Uma linha por material × requisição × OS, ordenada por risco e data de necessidade |
| Por OS | Total, entregues e pendentes por OS, mais a coluna **PRONTA PARA EXECUTAR?** |
| Por Fornecedor | Pedidos abertos, valor e atraso mais antigo, para a cobrança |
| Divergências | Itens não casados, vínculos de baixa confiança, duplicidades e alertas de carga |
| Parâmetros | Limites editáveis, legenda e conciliação de linhas da última atualização |
| Bases tratadas | As 3 bases já normalizadas, para auditoria |

Status, dias e valores são fórmulas: recalculam sozinhos com a data do dia (`=HOJE()` na aba Parâmetros).

## Arquivos

- `atualizar_followup.py`: gera a planilha (abas e fórmulas).
- `cruzamento.py`: regras de casamento entre as bases, etapa e status de risco.
- `tracos_bases.py`: leitura dos CSVs do TracOS (UTF-16, TAB, "-" = vazio) e extração de códigos.
- `reconhecimento.py`: relatório de diagnóstico das bases (casamento, casos estranhos). Opcional.

Os CSVs e as planilhas geradas ficam fora do Git (`.gitignore`), porque têm dados de compra.
