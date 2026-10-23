# Follow-up de peças para manutenção (TracOS)

Cruza as 3 exportações do TracOS (requisição, fluxo e pedido de compra) e gera uma planilha Excel que mostra:
- em que etapa da compra está cada peça de cada OS;
- o risco de a peça não chegar até a data de necessidade e quem cobrar;
- o controle de recebimento dos materiais e quais OS estão **aptas para programar**, ou seja, com todos os itens disponíveis.

## Como usar

1. Exporte do TracOS os 3 relatórios e salve na pasta `bases`:
   - `requisição de compra *.csv`
   - `fluxo de compras *.csv`
   - `pedido de compra *.csv`

   O número no fim do nome pode mudar. Se houver mais de um arquivo do mesmo tipo, o script usa o mais recente.
2. Dê dois cliques em **`atualizar_followup.bat`**. Também dá para rodar `python atualizar_followup.py` no terminal.
3. A planilha abre sozinha. Ela fica salva em `saida/followup_preventivas_AAAA-MM-DD.xlsx`.

Na primeira vez, o `.bat` instala as bibliotecas `pandas` e `openpyxl`. Para isso, o Python precisa estar instalado com a opção "Add python.exe to PATH" marcada.

## Rotina de gestão dos materiais

| Quando | Onde | O que fazer |
|---|---|---|
| Material chegou e foi separado para a OS | Aba **Recebimento** | Em `Recebido?`, escolha **SIM**. Preencha data e local/kit se quiser. Use **PARCIAL** se chegou só parte e **NÃO** se o TracOS mostra entrada mas o material não está aqui. |
| A OS não tem data de necessidade (só está em requisição) | Aba **Por OS** | Preencha `Data de necessidade (manual)`. A data vale para todos os itens da OS e manda sobre a do TracOS. |
| A OS ficou ✅ APTA PARA PROGRAMAR | Aba **Por OS** | Programe a OS e preencha `Liberada para a equipe em`. Se faltar item, a OS fica em vermelho: ⚠ LIBERADA FALTANDO. |

A OS só fica **APTA** quando **todos** os itens estão disponíveis. Um item está disponível quando você marcou SIM no Recebimento, ou quando o TracOS mostra entrada e não há marca PARCIAL ou NÃO. A coluna `Itens que faltam` lista o que ainda falta em cada OS.

Tudo recalcula na hora no Excel. Não é preciso rodar o script de novo depois de marcar.

## Painel clicável

- **Menu no topo:** os botões azuis abrem cada aba. Em todas as abas, a célula A1 tem **⬅ Voltar ao Painel**.
- **Textos e números sublinhados:** levam direto ao primeiro item do grupo.
  - Exemplo: "🚚 A CAMINHO – ATRASADO 22" abre o Recebimento nessa linha, já na coluna `Recebido?`.
  - Grupo vazio leva ao início da aba.
- **OS aptas para programar agora:** a lista se atualiza conforme você marca o recebimento. Clique na OS para abri-la.
- **✉ Cobrar:** abre o e-mail pronto no Outlook.
  - Fornecedor: já com os pedidos SAP. Cadastre o e-mail na aba Por Fornecedor.
  - Requisição parada: já com o nº SAP, a OS e desde quando está pendente. Cadastre os e-mails do gestor e do almox na aba Parâmetros.
  - O texto do e-mail vai sem acentos, por causa do limite de 255 caracteres dos links no Excel.
- **Dentro das abas:**
  - Por OS: `Ir para os itens` abre o Recebimento (ou o Follow-up) daquela OS.
  - Recebimento: `Itens que faltam na OS` abre a OS na aba Por OS.

Não há macros: o arquivo é um `.xlsx` comum e abre sem aviso de segurança. Filtrar a tabela automaticamente ao clicar exigiria macro (`.xlsm`). Para ver todos os itens de um grupo, use o filtro do cabeçalho.

## O que é preservado entre atualizações

- **Células amarelas:** Recebimento, datas e liberação das OS, observações e parâmetros voltam na próxima versão.
  - No Recebimento e no Follow-up, a chave é *material | requisição | OS*. Na aba Por OS, é o nº da OS.
  - Se o item sumir das bases, a anotação vai para Divergências (`ANOTAÇÃO SEM ITEM ATUAL`) e volta sozinha quando ele reaparecer.
- **Histórico de etapas** (aba oculta `_historico`): guarda desde quando cada item está em cada etapa, porque o TracOS não informa a data de autorização.

O script sempre lê a planilha mais recente da pasta `saida`. **Faça as marcações na versão mais nova** antes de atualizar.

## Abas

| Aba | Conteúdo |
|---|---|
| Painel | Menu de navegação e, em seções clicáveis: OS aptas para programar (com lista), recebimento, funil por etapa, status de risco, OS preventivas com itens faltando, fornecedores atrasados e requisições paradas (com ✉ Cobrar) |
| Por OS | APTA PARA PROGRAMAR?, itens que faltam, data de necessidade manual e liberação para a equipe |
| Recebimento | Itens com pedido (inclusive pedidos sem OS), para marcar o que chegou |
| Follow-up | Uma linha por material × requisição × OS, ordenada por risco e data de necessidade |
| Por Fornecedor | Pedidos abertos, valor e atraso mais antigo, para a cobrança |
| Divergências | Itens não casados, vínculos de baixa confiança, duplicidades, alertas e anotações sem item |
| Parâmetros | Limites editáveis, legenda e conciliação de linhas |
| Bases tratadas | As 3 bases já normalizadas, para auditoria |

## Arquivos

- `atualizar_followup.py`: gera a planilha (abas, fórmulas e preservação das anotações).
- `cruzamento.py`: regras de casamento entre as bases, etapa, status de risco, recebimento e situação da OS.
- `tracos_bases.py`: leitura dos CSVs do TracOS (UTF-16, TAB, "-" = vazio) e extração de códigos.
- `reconhecimento.py`: relatório de diagnóstico das bases. Opcional.

Os CSVs e as planilhas geradas ficam fora do Git (`.gitignore`), porque têm dados de compra.
