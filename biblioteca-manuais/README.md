# Biblioteca de Manuais

Biblioteca de manuais para a equipe de manutenção mecânica e elétrica, que roda num
computador da empresa. O administrador envia os manuais. Mecânicos e eletricistas abrem
o endereço da biblioteca no navegador do celular, tablet ou computador, na mesma rede,
sem login e sem conta em nenhum serviço.

## O que a página faz

- **Buscar** por equipamento, modelo, fabricante, setor, tag ou parte do título,
  sem diferenciar acentos nem maiúsculas.
- **Filtrar** por área (mecânica ou elétrica), tipo de documento e setor, e ordenar
  por data, título ou equipamento.
- **Abrir** PDFs, imagens e vídeos direto no navegador, e **Baixar** qualquer arquivo.
- Na **área do administrador** (com senha): enviar, editar, trocar o arquivo por uma
  revisão nova e excluir manuais.
- A lista atualiza sozinha em todas as telas abertas quando um manual entra ou sai.

Arquivos aceitos: PDF, JPG, PNG, WEBP, GIF, MP4, WEBM, TXT, Word, Excel, DWG, DXF e ZIP,
até 200 MB cada (dá para mudar, veja abaixo).

## Instalar no computador da biblioteca (Windows)

1. Instale o **Node.js** versão LTS: https://nodejs.org (Avançar até o fim).
2. Copie a pasta `biblioteca-manuais` para o computador, por exemplo em `C:\biblioteca-manuais`.
3. Dê dois cliques em **`iniciar.bat`**.
4. Na primeira vez, o Windows pergunta se libera o acesso pela rede. Marque
   **Redes privadas** (e **Redes de domínio**, se aparecer) e clique em **Permitir acesso**.
5. A janela preta mostra:
   - o endereço para a equipe, por exemplo `http://192.168.0.25:3000`;
   - a senha da área do administrador (só na primeira vez).

**Deixe essa janela aberta.** Fechar a janela desliga a biblioteca.

Em Linux ou macOS, rode `node servidor.js` dentro da pasta.

## Passar o endereço para a equipe

Mande o endereço que aparece em "Para a equipe na rede". Cada pessoa abre no navegador
e pode salvar na tela inicial do celular (no Chrome: menu ⋮ → Adicionar à tela inicial).

Para o endereço não mudar, peça à TI para **fixar o IP** desse computador. Às vezes o nome
do computador também funciona, como `http://NOME-DO-PC:3000`.

## Deixar a biblioteca sempre ligada

- **Iniciar junto com o Windows:** aperte `Win + R`, digite `shell:startup` e coloque ali
  um atalho para o `iniciar.bat`.
- **Não deixar o computador dormir:** Configurações → Sistema → Energia → Suspensão: **Nunca**.

## Configurações

Ficam em `dados/config.json`, criado na primeira vez que a biblioteca liga:

```json
{
  "senhaAdmin": "a senha gerada",
  "porta": 3000,
  "limiteMb": 200
}
```

- `senhaAdmin`: senha da área do administrador. Troque por uma sua.
- `porta`: o número no fim do endereço.
- `limiteMb`: tamanho máximo de cada arquivo, em MB.

Feche a janela e abra o `iniciar.bat` de novo depois de mudar.

## Backup

Tudo fica na pasta **`dados`**:

- `manuais.json` guarda as fichas;
- `arquivos/` guarda os arquivos enviados;
- `manuais.json.bak` é a versão anterior das fichas, salva a cada alteração.

Copie a pasta `dados` inteira para um pendrive ou para a rede de tempos em tempos. Para
restaurar, feche a biblioteca, coloque a pasta `dados` de volta e abra o `iniciar.bat`.

## Segurança

- Só quem está na rede da empresa acessa a biblioteca. Não libere a porta para a internet.
- Consultar e baixar não pedem senha. Enviar, editar e excluir pedem.
- O endereço usa `http://`, sem criptografia. Isso é comum dentro da rede interna, mas
  evite usar como senha de administrador uma senha que você usa em outros lugares.

## Tipos de documento

| Código | Tipo |
| --- | --- |
| MNT | Manual de manutenção |
| OPR | Manual de operação |
| DIA | Diagrama elétrico |
| PEC | Catálogo de peças |
| POP | Procedimento (POP) |
| DOC | Outro documento |

## Paleta de cores

| Cor | Pantone | Hex | Onde aparece |
| --- | --- | --- | --- |
| Vermelho | 4058C | `#E84752` | Faixa do cabeçalho, contorno do selo de administrador |
| Vermelho escuro | 703C | `#BF404D` | Filtro selecionado, área elétrica, botões ao passar o mouse, excluir |
| Rosa | 2029C | `#EB7580` | Sobretítulo do cabeçalho, foco no tema escuro |
| Azul petróleo | 432C | `#2B3D4A` | Cartões no tema escuro |
| Azul noite | 4280C | `#24303B` | Cabeçalho, texto, botões Abrir e Publicar |
| Azul aço | 7545C | `#385463` | Área mecânica, textos secundários |
| Creme médio | 7406C | `#E3E0B0` | Tags e área de envio de arquivo |
| Cáqui | 5855C | `#BDB58C` | Bordas e linhas, textos secundários no tema escuro |
| Creme claro | P 2-1 C | `#F5F2D4` | Fundo da página, texto no tema escuro |

A fonte é a do próprio sistema (Segoe UI no Windows, Roboto no Android, San Francisco no
iPhone), então a página funciona mesmo sem internet.

## Arquivos do projeto

- `servidor.js`: o servidor. Não precisa instalar pacotes, só o Node.js 18 ou mais novo.
- `public/`: a página (`index.html`, `estilo.css`, `app.js`).
- `iniciar.bat`: atalho para ligar no Windows.
- `dados/`: criada na primeira vez. Não vai para o Git.
