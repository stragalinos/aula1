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
   - **Opcional:** a ME2N do SAP (`*ME2N*.xlsx`), para ter o fornecedor dos pedidos que só existem no SAP.

   O número no fim do nome pode mudar. Se o arquivo for salvo com outro nome (ex.: `EXPORT.XLSX` do SAP), o script o reconhece pelas colunas.

   **Mais de um arquivo do mesmo tipo:**
   - O script usa o arquivo **novo**, isto é, o que não estava na pasta na última atualização.
   - Os antigos vão sozinhos para `bases/antigos`.
   - A data de modificação sozinha não serve: um arquivo copiado ou descompactado pode ficar com data mais nova que a de uma exportação recente.
   - Os arquivos usados aparecem no topo do Painel e na aba Parâmetros.
2. Dê dois cliques em **`atualizar_followup.bat`**. Também dá para rodar `python atualizar_followup.py` no terminal.
3. A planilha abre sozinha. Ela fica salva em `saida/followup_preventivas_AAAA-MM-DD.xlsx`.

Na primeira vez, o `.bat` instala as bibliotecas `pandas` e `openpyxl`. Para isso, o Python precisa estar instalado com a opção "Add python.exe to PATH" marcada.

## TracOS e SAP: duas bases que não se conversam

As compras pedidas pelo TracOS não aparecem na IWBK: a IWBK só lista os componentes planejados na ordem do SAP (estoque e RCs criadas no SAP). Por isso a planilha usa as duas bases, uma ao lado da outra:
- **Linhas do TracOS:** as compras pedidas pelo TracOS. Origem = TracOS.
- **Linhas do SAP:** os componentes da IWBK. Origem = SAP.
- **Sem duplicar:** o script tenta casar as duas bases (abaixo). Hoje elas não têm itens em comum, então cada item aparece uma vez só, na base de onde veio.
- **Onde ver o resultado:**
  - a coluna `Origem` do Follow-up, ao lado da OS, mostra `TracOS`, `SAP` ou `TracOS + SAP`, quando casou;
  - o resumo está no aviso "IWBK (SAP)" da aba Divergências.

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

## ME2N do SAP (fornecedor dos pedidos só do SAP)

**Por que alguns pedidos não têm fornecedor:**
- O fornecedor vem da base de pedidos do TracOS.
- Os pedidos que só existem no SAP vêm da IWBK, que não tem o campo fornecedor.
- Sem a ME2N, esses itens aparecem sem fornecedor e "Quem cobrar" indica o comprador.

**O que a ME2N preenche:** com a ME2N na pasta `bases`, cada item com pedido SAP é casado pelo **pedido + material**, ou só pelo pedido quando o material não bate. Com isso o item recebe:
- **o fornecedor:** aparece em "Quem cobrar", no Recebimento, na aba Por Fornecedor e no Painel, com os botões de cobrança;
- **a data do pedido:** passa a ser o início da etapa 4, que é a base de "Dias na etapa";
- **o preço:** só se o item não tiver preço e o pedido estiver em reais;
- **a RC SAP dos pedidos do TracOS:** se o layout tiver a coluna `Requisição de compra`. O TracOS só informa a RC enquanto a requisição está pendente.

**Como exportar:** a mesma seleção da IWBK (as OS em aberto), com as colunas `Documento de compras`, `Item`, `Material`, `Fornecedor/centro fornecedor`, `Data do documento`, `Qtd.do pedido`, `Preço líquido` e `Moeda`.

Quando o fornecedor vem com outro espaçamento no nome, o script usa o nome do TracOS, para não duplicar o fornecedor nem o cadastro de e-mail.

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
- **Contatos dos fornecedores:** são cadastro, não acompanhamento. Ficam na aba **Carteira de fornecedores** (veja abaixo). Os e-mails do gestor e do almox ficam na aba Parâmetros.

A OS só fica **APTA** quando **todos** os itens estão disponíveis. Um item está disponível quando você marcou SIM, ou quando o TracOS/SAP mostra entrada e não há marca PARCIAL ou NÃO. A coluna `Itens que faltam`, na aba Por OS, lista o que ainda falta em cada OS.

Tudo recalcula na hora no Excel. Não é preciso rodar o script de novo depois de marcar.

## Como as tabelas estão organizadas

- **Nº da OS e do pedido SAP sempre à vista:** ficam nas colunas fixas da esquerda, que não saem da tela quando um link leva a outra coluna.
  - Follow-up: `OS SAP`, `Origem` (TracOS / SAP), `RC SAP` e `Pedido SAP` nas colunas fixas; `Fornecedor` logo depois.
  - Recebimento: `Pedido SAP` e `OS SAP`.
  - Por Fornecedor: os pedidos SAP (com o nº TracOS entre parênteses) e as OS SAP afetadas, logo ao lado do fornecedor.
  - Por OS: `Pedidos SAP da OS`.
  - Painel: os pedidos SAP de cada fornecedor atrasado.
- **Follow-up:** 12 colunas de consulta e as 6 colunas amarelas, que são as únicas que você preenche. As colunas técnicas (chaves, linhas de origem, dados do SAP, preço etc.) ficam recolhidas: clique no **+** acima das colunas para abrir.
- **Follow-up em blocos por OS:** os itens de cada OS ficam juntos, com faixas de cor alternadas. As OS mais urgentes vêm primeiro.
- **Recebimento por situação, fornecedor e pedido,** que é como o material chega. Os itens em falta no estoque vêm agrupados por OS.
- **Só OS preventivas nas abas de trabalho.** Corretivas, compras e giro de estoque ficam na aba **Outras OS**.
  - Para ver todas, mude o parâmetro "Abas de trabalho só com OS preventivas?" para **NÃO** na aba Parâmetros e atualize.

## Cobrança do fornecedor: e-mail e WhatsApp Web

**Carteira de fornecedores (cadastro):**
- A aba lista todos os fornecedores das bases, com o código SAP (vindo da ME2N) e quantos pedidos e itens estão em aberto.
- Preencha uma vez as colunas amarelas: `Contato`, `E-mail do fornecedor` e `WhatsApp (DDD + número)`. Fica salvo nas próximas atualizações.
- **Vários e-mails:** separe com `;`.
- **WhatsApp:** pode digitar como quiser (`(11) 99999-9999`, `11999999999`, `+55 11 ...`). O script tira os símbolos e põe o 55 do Brasil.
- **Fornecedor que não está na lista:** inclua no fim da tabela, com o nome escrito igual ao das bases.

**Botões nas linhas do Follow-up:**
- Cada item com pedido emitido e ainda não disponível tem **✉ Cobrar por e-mail** e **💬 Cobrar no WhatsApp**.
- A mensagem é do pedido inteiro: todos os itens dele ainda em aberto.

**Botões nas outras abas:**
- **Por Fornecedor e Painel** (cartão de fornecedores atrasados): os mesmos botões, cobrando todos os pedidos em aberto do fornecedor de uma vez.
- **Sem contato cadastrado:** o botão mostra `✎ cadastrar` e leva à linha do fornecedor na carteira.

**Mensagem padrão:**
- Assunto: "Cobrança de entrega – pedido SAP …", com **URGENTE** na frente quando há item com a necessidade vencida.
- Saudação ("Olá, *Contato*" ou "Prezados") e um aviso de quantos itens já estão vencidos e de que a manutenção está aguardando o material.
- **Tabela dos itens em aberto:** PEDIDO, ITEM (código e descrição), QTD e NECESSIDADE. No e-mail há também a coluna SITUAÇÃO (VENCIDA / no prazo).
- Pedido de retorno em até 24 horas com:
  1. a data de entrega confirmada de cada item;
  2. a nota fiscal e a transportadora, se já faturou;
  3. qualquer impedimento, para buscarmos alternativa.
- A sua assinatura: parâmetro "Assinatura das mensagens de cobrança", na aba Parâmetros.
- **No WhatsApp:** a tabela vai num bloco de fonte de largura fixa, com as colunas alinhadas. No WhatsApp Web fica certinha; em celular de tela estreita a linha pode quebrar.
- **No e-mail:** as colunas são separadas por `|`. O link de e-mail do Excel só aceita texto simples, sem tabela formatada.

**Envio:**
- **E-mail:** abre no Outlook, ou no seu programa de e-mail, pronto para enviar. O texto do e-mail vai sem acentos, porque alguns Outlook trocam os acentos de links de e-mail.
- **WhatsApp:** abre o WhatsApp Web, já na conversa do fornecedor e com a mensagem escrita, com acentos. É preciso estar conectado ao WhatsApp Web no navegador.

**Quando a mensagem sai completa:**
- Assim que você cadastra o contato, o botão já funciona, mas com uma mensagem curta, porque links criados por fórmula no Excel têm no máximo 255 caracteres.
- Na próxima atualização (rodar o `.bat`), a mensagem sai completa, com os itens e as datas.
- Fornecedor com muitos pedidos: a mensagem lista só os números dos pedidos.

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
- **Cobrar:**
  - Fornecedores atrasados: ✉ e 💬, como no Follow-up.
  - Requisição parada: ✉ Cobrar, já com o nº SAP, a OS e desde quando está pendente. O texto vai sem acentos, por causa do limite de 255 caracteres dos links no Excel.

Não há macros: o arquivo é um `.xlsx` comum e abre sem aviso de segurança. Filtrar a tabela automaticamente ao clicar exigiria macro (`.xlsm`). Para ver todos os itens de um grupo, use o filtro do cabeçalho.

## O que é preservado entre atualizações

- **Células amarelas:** o que você digitou no Follow-up, os parâmetros e os e-mails voltam na próxima versão.
  - Itens: a chave é *material | requisição | OS*. Campos da OS: a chave é o nº SAP da OS.
  - Se a chave do item mudar (por exemplo, o item do SAP ganhou RC), a anotação vai para o item da mesma OS + material, quando só há um.
  - Se o item ou a OS sumir das bases, a anotação vai para Divergências (`ANOTAÇÃO SEM ITEM ATUAL`) e volta sozinha quando ele reaparecer.
- **Planilhas da versão anterior:** na primeira atualização, o que estava digitado nas abas Recebimento, Por OS, Por Fornecedor e Divergências é levado sozinho para o Follow-up e para Parâmetros.
  - As observações da OS e das divergências entram na observação do item, com o prefixo "OS:" ou "Divergência".
  - A qtd e a observação do recebimento também entram na observação do item.
- **Histórico de etapas** (aba oculta `_historico`): guarda desde quando cada item está em cada etapa, porque o TracOS não informa a data de autorização. Se a planilha anterior não tiver o item, o script procura nas duas planilhas antes dela.

O script sempre lê a planilha mais recente da pasta `saida`. **Faça as marcações na versão mais nova** antes de atualizar.

## Abas

| Aba | Conteúdo |
|---|---|
| Painel | Indicadores e cartões clicáveis (ver acima) |
| Follow-up | **Onde você preenche.** Uma linha por material × requisição × OS, em blocos por OS, as mais urgentes primeiro |
| Por OS | APTA PARA PROGRAMAR?, itens que faltam, data de necessidade usada e liberação (consulta) |
| Recebimento | Itens com pedido e em falta no estoque, por situação e fornecedor (consulta, com `✎ marcar`) |
| Por Fornecedor | Pedidos abertos, valor e atraso mais antigo, com ✉ / 💬 para cobrar |
| Carteira de fornecedores | Contato, e-mail e WhatsApp de cada fornecedor (cadastro) |
| Divergências | Itens não casados, vínculos de baixa confiança, duplicidades, reservas antigas do SAP, alertas e anotações sem item |
| Histórico SAP | Itens da IWBK já retirados ou baixados para a ordem (sem ação pendente) |
| Outras OS | Itens de OS não preventivas (quando o parâmetro "só preventivas" está SIM) |
| Parâmetros | Limites editáveis, e-mails do gestor e do almox, assinatura das mensagens, legenda e conciliação de linhas |
| Bases tratadas | As 3 bases já normalizadas, para auditoria |

## Arquivos

- `atualizar_followup.py`: gera a planilha (abas, fórmulas e preservação das anotações).
- `cruzamento.py`: regras de casamento entre as bases, etapa, status de risco, recebimento e situação da OS.
- `tracos_bases.py`: leitura dos CSVs do TracOS (UTF-16, TAB, "-" = vazio) e da IWBK do SAP, e extração de códigos.
- `reconhecimento.py`: relatório de diagnóstico das bases. Opcional.

Os CSVs e as planilhas geradas ficam fora do Git (`.gitignore`), porque têm dados de compra.
