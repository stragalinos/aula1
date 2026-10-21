# Biblioteca de Manuais

Biblioteca virtual de manuais para a equipe de manutenção mecânica e elétrica.
Quem administra envia os manuais. Mecânicos e eletricistas buscam, abrem e baixam
pelo celular, tablet ou computador.

Página publicada: https://claude.ai/artifact/15LXD8g7UsdzxGAihBqxDD

## O que a página faz

- **Enviar manual** (só quem tem acesso de edição): PDF, JPG, PNG, WEBP ou MP4 de até 20 MB,
  com título, área (mecânica, elétrica ou as duas), tipo de documento, equipamento,
  setor, fabricante, modelo, revisão, tags e observações.
- **Buscar**: por equipamento, modelo, fabricante, setor, tag ou parte do título,
  sem diferenciar acentos nem maiúsculas.
- **Filtrar** por área, tipo de documento e setor, e ordenar por data, título ou equipamento.
- **Abrir** o arquivo em outra aba e **Baixar** para usar sem internet.
- **Editar** os dados ou trocar o arquivo por uma revisão nova, e **Excluir** (com confirmação).

Tipos de documento e os códigos que aparecem na plaqueta de cada ficha:

| Código | Tipo |
| --- | --- |
| MNT | Manual de manutenção |
| OPR | Manual de operação |
| DIA | Diagrama elétrico |
| PEC | Catálogo de peças |
| POP | Procedimento (POP) |
| DOC | Outro documento |

## Como dar acesso à equipe

1. Abra a página publicada e use o botão **Compartilhar** do Claude.
2. Dê acesso de **Leitor** aos mecânicos e eletricistas. Eles podem buscar, abrir e baixar,
   mas não alteram nada.
3. Dê acesso de **Editor** a quem também vai enviar manuais (por exemplo, o supervisor).

Cada pessoa precisa entrar com a própria conta do Claude para ver os manuais.

## Como funciona por dentro

O arquivo `index.html` é uma página de Artifact do Claude. Ela usa recursos que o
Claude fornece quando a página é aberta pelo link publicado:

- `assets` guarda os arquivos enviados (limite de 20 MB por arquivo);
- `db` guarda a ficha de cada manual na coleção `manuais`, com leitura liberada a todos
  que têm acesso e escrita só para editores;
- `user` identifica quem enviou cada manual e quem pode editar;
- `downloads` oferece o botão **Baixar**.

Aberto direto do disco ou do GitHub, o arquivo mostra apenas o aviso para abrir pelo
link do Claude, porque esses recursos não existem fora dele.
