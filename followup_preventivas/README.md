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

   - **Opcional:** a IWBK do SAP (`*IWBK*.xlsx`, exportada com o layout completo de colunas).

   O número no fim do nome pode mudar. Se o arquivo for salvo com outro nome (ex.: `EXPORT.XLSX` do SAP), o script o reconhece pelas colunas.

   **Mais de um arquivo do mesmo tipo:**
   - O script usa o arquivo **novo**, isto é, o que não estava na pasta na última atualização.
   - Os antigos vão sozinhos para `bases/antigos`.
   - A data de modificação sozinha não serve: um arquivo copiado ou descompactado pode ficar com data mais nova que a de uma exportação recente.
   - Os arquivos usados aparecem no topo do Painel e na aba Parâmetros.
2. Dê dois cliques em **`atualizar_followup.bat`**. Também dá para rodar `python atualizar_followup.py` no terminal.
3. A planilha abre sozinha. Ela fica salva em `saida/followup_preventivas_AAAA-MM-DD.xlsx`.

Na primeira vez, o `.bat` instala as bibliotecas `pandas` e `openpyxl`. Para isso, o Python precisa estar instalado com a opção "Add python.exe to PATH" marcada.

## IWBK do SAP (RC e itens que só existem no SAP)

Com a IWBK na pasta `bases`, cada componente de ordem do SAP é casado com o TracOS nesta ordem: OS + material + RC, OS + material + pedido, OS + material, material + RC, material + pedido. Quando casa, a linha do TracOS ganha a data de necessidade e a situação do SAP.

O que não casa entra no Follow-up com **Origem = SAP**:

| Situação na IWBK | Etapa |
|---|---|
| Item de estoque (L) em falta | **0 - Falta em estoque** (cobrar o almoxarifado) |
| RC não liberada | 1 |
| RC liberada sem pedido | 3 |
| Com pedido | 4 (a IWBK não traz o fornecedor: cobrar o comprador) |
| Entrada registrada, disponível em estoque ou retirado para a OS | 5 |

Outros efeitos da IWBK:
- **OS pelo nº SAP:** as OS passam a ser identificadas pelo nº SAP, porque há OS que só existem no SAP.
- **Data de necessidade:** a da IWBK vale também para os itens do TracOS da mesma OS.
- **Material já retirado:** itens já retirados ou baixados para a ordem vão para a aba **Histórico SAP**. Saem do Follow-up, do Recebimento e da Por OS, mas contam como disponíveis no total da OS.
- **OS com todo o material retirado:** aparece no Painel como **✔ MATERIAL JÁ RETIRADO (SAP)**, com link para o histórico.
- **Reservas antigas:** reservas com necessidade de mais de 180 dias vão para Divergências e ficam no fim de cada grupo no Follow-up.

## Itens cancelados, excluídos ou encerrados

- **TracOS:** requisição, item do fluxo ou pedido com status cancelado, excluído ou reprovado sai do Follow-up.
  - Esses registros aparecem em Divergências como `FORA DO FOLLOW-UP`.
  - Os reprovados aparecem como gravidade Média: se a OS ainda precisa do item, abra uma nova requisição.
- **SAP:** se o layout da IWBK tiver a coluna de item eliminado (ex.: `Eliminado`) ou o status do sistema da ordem, ficam de fora:
  - os componentes eliminados;
  - os componentes de OS encerradas (ENTE / ENCE) ou marcadas para eliminação (MREL / MAEL).
- **Item que sumiu da exportação:** sai do Follow-up na próxima atualização. As anotações dele ficam guardadas (veja abaixo).

## Rotina de gestão dos materiais: tudo na aba Follow-up

Você só preenche a aba **Follow-up**, nas colunas amarelas do fim da parte visível. As outras abas e o Painel só mostram o resultado e se atualizam na hora.

| Quando | Coluna do Follow-up | O que fazer |
|---|---|---|
| O material chegou e foi separado para a OS | `Recebido?` | Escolha **SIM**. Use **PARCIAL** se chegou só parte e **NÃO** se o TracOS mostra entrada mas o material não está aqui. `Data do recebimento` e `Local / kit de separação` são opcionais. |
| Cobrança, previsão, combinado com o fornecedor | `Observação / Follow-up` | Texto livre, por item. |
| A OS não tem data de necessidade, ou a data é outra | `Data de necessidade da OS` | Digite na **1ª linha da OS**, a célula amarela. A data vale para todos os itens da OS e manda sobre a do TracOS/SAP. |
| A OS ficou ✅ APTA PARA PROGRAMAR e você passou para a equipe | `OS liberada para a equipe em` | Digite a data na 1ª linha da OS. Se faltar item, a OS fica em vermelho: ⚠ LIBERADA FALTANDO. |

- **Campos da OS em outra linha:** digitar `Data de necessidade da OS` ou `OS liberada` em outra linha da mesma OS também funciona; vale a maior data. Na próxima atualização o valor volta para a 1ª linha da OS.
- **Atalhos para a linha certa:**
  - Recebimento: `✎ marcar` leva ao `Recebido?` do item no Follow-up.
  - Por OS: `✎ Preencher` leva à 1ª linha da OS no Follow-up.
- **E-mails dos fornecedores:** são cadastro, não acompanhamento. Ficam na aba **Parâmetros**, junto com os do gestor e do almox. Digite uma vez e o e-mail fica salvo. O link `✎ cadastrar e-mail` leva à linha do fornecedor.

A OS só fica **APTA** quando **todos** os itens estão disponíveis. Um item está disponível quando você marcou SIM, ou quando o TracOS/SAP mostra entrada e não há marca PARCIAL ou NÃO. A coluna `Itens que faltam`, na aba Por OS, lista o que ainda falta em cada OS.

Tudo recalcula na hora no Excel. Não é preciso rodar o script de novo depois de marcar.

## Como as tabelas estão organizadas

- **Follow-up:** 11 colunas de consulta e as 6 colunas amarelas, que são as únicas que você preenche. As colunas técnicas (chaves, linhas de origem, dados do SAP, preço etc.) ficam recolhidas: clique no **+** acima das colunas para abrir.
- **Follow-up em blocos por OS:** os itens de cada OS ficam juntos, com faixas de cor alternadas. As OS mais urgentes vêm primeiro.
- **Recebimento por situação, fornecedor e pedido,** que é como o material chega. Os itens em falta no estoque vêm agrupados por OS.
- **Só OS preventivas nas abas de trabalho.** Corretivas, compras e giro de estoque ficam na aba **Outras OS**.
  - Para ver todas, mude o parâmetro "Abas de trabalho só com OS preventivas?" para **NÃO** na aba Parâmetros e atualize.

## Painel

- **Faixa de título:** data de referência, hora da geração e, se houver, o link para os avisos sobre as bases.
- **Menu:** o botão azul **✎ Follow-up (preencher)** abre as colunas amarelas. Os outros botões abrem as demais abas. Em todas as abas, a célula A1 tem **⬅ Voltar ao Painel**.
- **Indicadores no topo:**
  - OS aptas para programar (o número em destaque);
  - OS aguardando itens;
  - itens atrasados;
  - itens em falta no estoque;
  - itens parados na aprovação.

  Cada número leva ao primeiro item do grupo.
- **Cartões:**
  - situação das OS;
  - recebimento;
  - OS aptas agora (lista);
  - OS com itens faltando por janela de necessidade;
  - status de risco;
  - funil de compras;
  - fornecedores atrasados;
  - requisições paradas.

  As cores seguem o estado: verde = ok, amarelo = atenção, laranja = sério, vermelho = crítico, azul = em andamento, cinza = encerrado. Cada linha também tem ícone e texto, e as barras mostram o tamanho de cada grupo.
- **✉ Cobrar:** abre o e-mail pronto no Outlook.
  - Fornecedor: já com os pedidos SAP.
  - Requisição parada: já com o nº SAP, a OS e desde quando está pendente.
  - O texto do e-mail vai sem acentos, por causa do limite de 255 caracteres dos links no Excel.

Não há macros: o arquivo é um `.xlsx` comum e abre sem aviso de segurança. Filtrar a tabela automaticamente ao clicar exigiria macro (`.xlsm`). Para ver todos os itens de um grupo, use o filtro do cabeçalho.

## O que é preservado entre atualizações

- **Células amarelas:** o que você digitou no Follow-up, os parâmetros e os e-mails voltam na próxima versão.
  - Itens: a chave é *material | requisição | OS*. Campos da OS: a chave é o nº SAP da OS.
  - Se o item ou a OS sumir das bases, a anotação vai para Divergências (`ANOTAÇÃO SEM ITEM ATUAL`) e volta sozinha quando ele reaparecer.
- **Planilhas da versão anterior:** na primeira atualização, o que estava digitado nas abas Recebimento, Por OS, Por Fornecedor e Divergências é levado sozinho para o Follow-up e para Parâmetros.
  - As observações da OS e das divergências entram na observação do item, com o prefixo "OS:" ou "Divergência".
  - A qtd e a observação do recebimento também entram na observação do item.
- **Histórico de etapas** (aba oculta `_historico`): guarda desde quando cada item está em cada etapa, porque o TracOS não informa a data de autorização.

O script sempre lê a planilha mais recente da pasta `saida`. **Faça as marcações na versão mais nova** antes de atualizar.

## Abas

| Aba | Conteúdo |
|---|---|
| Painel | Indicadores e cartões clicáveis (ver acima) |
| Follow-up | **Onde você preenche.** Uma linha por material × requisição × OS, em blocos por OS, as mais urgentes primeiro |
| Por OS | APTA PARA PROGRAMAR?, itens que faltam, data de necessidade usada e liberação (consulta) |
| Recebimento | Itens com pedido e em falta no estoque, por situação e fornecedor (consulta, com `✎ marcar`) |
| Por Fornecedor | Pedidos abertos, valor e atraso mais antigo, para a cobrança |
| Divergências | Itens não casados, vínculos de baixa confiança, duplicidades, reservas antigas do SAP, alertas e anotações sem item |
| Histórico SAP | Itens da IWBK já retirados ou baixados para a ordem (sem ação pendente) |
| Outras OS | Itens de OS não preventivas (quando o parâmetro "só preventivas" está SIM) |
| Parâmetros | Limites editáveis, e-mails (gestor, almox e fornecedores), legenda e conciliação de linhas |
| Bases tratadas | As 3 bases já normalizadas, para auditoria |

## Arquivos

- `atualizar_followup.py`: gera a planilha (abas, fórmulas e preservação das anotações).
- `cruzamento.py`: regras de casamento entre as bases, etapa, status de risco, recebimento e situação da OS.
- `tracos_bases.py`: leitura dos CSVs do TracOS (UTF-16, TAB, "-" = vazio) e da IWBK do SAP, e extração de códigos.
- `reconhecimento.py`: relatório de diagnóstico das bases. Opcional.

Os CSVs e as planilhas geradas ficam fora do Git (`.gitignore`), porque têm dados de compra.
