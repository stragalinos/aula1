# Follow-up de peças para manutenção (SAP)

Cruza a **IWBK** (componentes das ordens) e a **ME2N** (pedidos, com o fornecedor) do SAP e gera uma planilha Excel que mostra:
- em que etapa está cada peça de cada OS: falta em estoque, RC não liberada, RC sem pedido, pedido emitido ou entregue;
- o risco de a peça não chegar até a data de necessidade e quem cobrar;
- o controle de recebimento dos materiais e quais OS estão **aptas para programar**, ou seja, com todos os itens disponíveis.

O TracOS não é usado: o que é criado no TracOS cai no SAP.

## Como usar

1. Exporte do SAP e salve na pasta `bases`:
   - **IWBK** (obrigatória): o arquivo com "IWBK" no nome, exportado com o layout completo de colunas.
   - **ME2N** (opcional, mas recomendada): o arquivo com "ME2N" no nome. É ela que traz o fornecedor dos pedidos.

   Se o arquivo for salvo com outro nome (ex.: `EXPORT.XLSX`), o script o reconhece pelas colunas.
2. Dê dois cliques em **`atualizar_followup.bat`**. Também dá para rodar `python atualizar_followup.py` no terminal.
3. A planilha abre sozinha. Ela fica salva em `saida/followup_preventivas_AAAA-MM-DD.xlsx`.

Na primeira vez, o `.bat` instala as bibliotecas `pandas` e `openpyxl`. Para isso, o Python precisa estar instalado com a opção "Add python.exe to PATH" marcada.

**Mais de um arquivo da mesma base:**
- O script usa o arquivo **novo**, isto é, o que não estava na pasta na última atualização.
- Os antigos vão sozinhos para `bases/antigos`.
- Os arquivos usados aparecem no topo do Painel e na aba Parâmetros.

## O que exportar do SAP

| Base | Seleção | Colunas que o script usa |
|---|---|---|
| IWBK | As OS que você acompanha (centro, período) | Ordem, Txt.breve ordem, Material, Texto breve material, Qtd.necessária, Qtd.retirada, Qtd.entrada, UM básica, Data da necessidade, Requisição de compra, Item ReqC, Pedido, Documento de compras, Data de remessa, Categoria do item, Disponibilidade, Nº reserva, Item lis.téc. |
| ME2N | **Todos os pedidos das ordens** (classificação contábil F), e não só os pedidos que aparecem na IWBK | Documento de compras, Item, Material, Texto breve, Ordem, Fornecedor/centro fornecedor, Data do documento, Qtd.do pedido, a ser fornecida (quantidade), Preço líquido, Moeda, Grupo de compradores |

**Colunas opcionais da IWBK:**
- `Eliminado` ou o status do sistema da ordem: deixam de fora os componentes eliminados e as OS encerradas (ENTE / ENCE) ou marcadas para eliminação (MREL / MAEL).
- Equipamento ou local de instalação: preenchem a coluna Ativo.

**Colunas opcionais da ME2N:**
- `Requisição de compra`: mostra a RC dos pedidos que não têm RC na IWBK.
- `Data de remessa`: a entrega prevista do pedido.

## Como cada item é montado

- **Uma linha por componente da IWBK:** material × RC × OS.
- **Pedido de OS que não tem componente na IWBK** (ex.: uma compra pedida pelo TracOS, que cai no SAP como pedido da ordem sem virar componente dela): vira uma linha própria, com Etapa 4 ou 5.
  - Se a OS não estiver na IWBK, a descrição dela aparece como "(OS sem componente na IWBK)" e a coluna Preventiva fica como "?".
  - Essas OS continuam nas abas de trabalho.
- **Casamento com a ME2N:** pelo pedido + material, ou só pelo pedido quando o material não bate (um pedido tem um fornecedor só). O item recebe:
  - o fornecedor;
  - a data do pedido;
  - o preço (só pedidos em reais);
  - o que falta fornecer: se a ME2N diz que não falta nada, o item fica como entregue.

| Situação no SAP | Etapa | Quem cobrar |
|---|---|---|
| Item de estoque (L) em falta | 0 - Falta em estoque | Almoxarifado |
| RC não liberada | 1 - RC não liberada | Aprovador da RC |
| RC liberada sem pedido | 3 - RC liberada, sem pedido | Comprador (sem RC: criar a RC) |
| Com pedido | 4 - Pedido emitido | Fornecedor (ME2N) ou, sem ME2N, o comprador |
| Entrada registrada, disponível em estoque ou nada a fornecer | 5 - Entregue / disponível | — |

**Outras regras:**
- **Material já retirado ou baixado para a ordem:** vai para a aba **Histórico SAP**. Conta como disponível no total da OS.
- **Status ENTREGA EM RISCO:** faltam Z dias ou menos para a necessidade, ou a entrega prevista do pedido é depois da necessidade.
- **Dias na etapa:**
  - na etapa 4, contam a partir da data do pedido;
  - nas outras, a partir da 1ª vez que a atualização viu o item na etapa, porque a IWBK não traz a data da RC.
- **Reservas antigas:** reservas com necessidade de mais de 180 dias vão para Divergências e ficam no fim de cada grupo.

## Rotina de gestão dos materiais: tudo na aba Follow-up

Você só preenche a aba **Follow-up**, nas colunas amarelas do fim da parte visível. As outras abas e o Painel só mostram o resultado e se atualizam na hora.

| Quando | Coluna do Follow-up | O que fazer |
|---|---|---|
| O material chegou e foi separado para a OS | `Recebido?` | Escolha **SIM**. Use **PARCIAL** se chegou só parte e **NÃO** se o SAP mostra entrada mas o material não está aqui. `Data do recebimento` e `Local / kit de separação` são opcionais. |
| Cobrança, previsão, combinado com o fornecedor | `Observação / Follow-up` | Texto livre, por item. |
| A OS não tem data de necessidade, ou a data é outra | `Data de necessidade da OS` | Digite na **1ª linha da OS**, a célula amarela. A data vale para todos os itens da OS e manda sobre a do SAP. |
| A OS ficou ✅ APTA PARA PROGRAMAR e você passou para a equipe | `OS liberada para a equipe em` | Digite a data na 1ª linha da OS. Se faltar item, a OS fica em vermelho: ⚠ LIBERADA FALTANDO. |

- **Campos da OS em outra linha:** digitar a data ou a liberação em outra linha da mesma OS também funciona; vale a maior data.
- **Atalhos para a linha certa:**
  - Recebimento: `✎ marcar` leva ao `Recebido?` do item.
  - Por OS: `✎ Preencher` leva à 1ª linha da OS.
- **E-mails dos fornecedores e do aprovador das RC:** ficam na aba **Parâmetros**. Digite uma vez e o e-mail fica salvo.

A OS só fica **APTA** quando **todos** os itens estão disponíveis. Um item está disponível quando você marcou SIM, ou quando o SAP mostra entrada ou estoque e não há marca PARCIAL ou NÃO.

## Como as tabelas estão organizadas

- **Nº da OS, da RC e do pedido sempre à vista:** ficam nas colunas fixas da esquerda, que não saem da tela quando um link leva a outra coluna.
  - Follow-up: `OS SAP`, `RC SAP` e `Pedido SAP`; `Fornecedor` vem logo depois.
  - Recebimento: `Pedido SAP` e `OS SAP`, com a entrega prevista do pedido.
- **Colunas técnicas recolhidas:** linha na IWBK e na ME2N, preço, disponibilidade etc. Clique no **+** acima das colunas para abrir.
- **Follow-up em blocos por OS:** os itens de cada OS ficam juntos, com faixas de cor alternadas, e as OS mais urgentes vêm primeiro.
- **Só OS preventivas nas abas de trabalho:** OS com "PREV" na descrição ou iniciada por "MSI".
  - As demais ficam na aba **Outras OS**.
  - Para ver todas, mude o parâmetro "Abas de trabalho só com OS preventivas?" para **NÃO** na aba Parâmetros e atualize.

## Painel

- **Topo:** data de referência, as bases usadas e, se houver, o link para os avisos sobre as bases.
- **Menu:** o botão azul **✎ Follow-up (preencher)** abre as colunas amarelas.
- **Indicadores:** OS aptas para programar, OS aguardando itens, itens atrasados, falta em estoque e itens parados na aprovação. Cada número leva ao primeiro item do grupo.
- **Cartões:**
  - situação das OS;
  - recebimento;
  - OS aptas agora;
  - OS com itens faltando por janela de necessidade;
  - status de risco;
  - funil por etapa;
  - fornecedores atrasados (com os pedidos SAP);
  - RC paradas na aprovação.
- **✉ Cobrar:** abre o e-mail pronto no Outlook, para o fornecedor (com os pedidos) ou para o aprovador (com a RC). O texto vai sem acentos, por causa do limite de 255 caracteres dos links no Excel.

Não há macros: o arquivo é um `.xlsx` comum e abre sem aviso de segurança.

## O que é preservado entre atualizações

- **Células amarelas:** o que você digitou no Follow-up, os parâmetros e os e-mails voltam na próxima versão.
  - Itens: a chave é *material | RC SAP | OS SAP*. Campos da OS: a chave é o nº SAP da OS.
  - **A chave mudou** (o item ganhou RC, ou veio de uma versão com o TracOS): a anotação vai para o item da mesma OS + material, quando só há um.
  - **O item sumiu das bases:** a anotação vai para Divergências (`ANOTAÇÃO SEM ITEM ATUAL`) e volta sozinha quando ele reaparecer.
- **Histórico de etapas** (aba oculta `_historico`): guarda desde quando cada item está em cada etapa.

O script sempre lê a planilha mais recente da pasta `saida`. **Faça as marcações na versão mais nova** antes de atualizar.

## Abas

| Aba | Conteúdo |
|---|---|
| Painel | Indicadores e cartões clicáveis |
| Follow-up | **Onde você preenche.** Uma linha por componente, em blocos por OS, as mais urgentes primeiro |
| Por OS | APTA PARA PROGRAMAR?, itens que faltam, pedidos da OS, data de necessidade usada e liberação |
| Recebimento | Itens com pedido e em falta no estoque, por situação e fornecedor (com `✎ marcar`) |
| Por Fornecedor | Pedidos abertos, valor, atraso mais antigo e entrega prevista, para a cobrança |
| Divergências | Avisos sobre as bases, reservas antigas, pedidos fora da ME2N, itens da ME2N sem OS e anotações sem item |
| Histórico SAP | Itens já retirados ou baixados para a ordem |
| Outras OS | Itens de OS não preventivas (quando o parâmetro "só preventivas" está SIM) |
| Parâmetros | Limites editáveis, e-mails, legenda e conciliação de linhas |
| Bases tratadas | IWBK e ME2N já normalizadas, para auditoria |

## Arquivos

- `atualizar_followup.py`: gera a planilha (abas, fórmulas e preservação das anotações).
- `cruzamento.py`: monta os itens a partir da IWBK e da ME2N, define a etapa, o status de risco, o recebimento e a situação da OS.
- `bases_sap.py`: localiza e lê as exportações do SAP.

As exportações e as planilhas geradas ficam fora do Git (`.gitignore`), porque têm dados de compra.
