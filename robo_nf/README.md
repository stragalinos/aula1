# Robô de leitura de Notas Fiscais escaneadas

Lê as NFs escaneadas (PDF, JPG, PNG, TIF) e monta uma planilha Excel com:

| Fornecedor | Nº NF | Pedido | Valor Total | Série | CNPJ Fornecedor | Chave de Acesso | Arquivo | Página | Status |
|---|---|---|---|---|---|---|---|---|---|
| FORNECEDOR EXEMPLO LTDA | 12345 | 4500012345 | 3.062,50 | 1 | 12.345.678/0001-95 | 3526…0979 | nf_01.pdf | 1 | OK |

As linhas que precisam de conferência ficam **amarelas**, e a coluna *Status* diz o motivo
(pedido não encontrado, mais de um pedido, NF repetida etc.).

## Opção 1 — Sem instalar nada (Windows 10/11) ✅

Usa só o que já vem no Windows: o **PowerShell** e o **OCR do próprio Windows**.
Não precisa de Python, Tesseract nem permissão de administrador.

1. Copie para uma pasta do seu computador os arquivos **`robo_nf.ps1`** e **`executar_robo_windows.bat`**.
2. Crie, nessa mesma pasta, uma pasta chamada **`notas`** e coloque nela as NFs escaneadas
   (pode ser um arquivo por NF ou um PDF com várias folhas; folhas em branco são ignoradas).
3. Dê dois cliques em **`executar_robo_windows.bat`**.
4. A planilha **`planilha_nfs.xlsx`** aparece na pasta. Na pasta **`textos_ocr`** fica o que o robô
   leu de cada página: o texto (`.txt`) e a posição de cada palavra (`.json`). Se alguma NF vier
   errada, mande essa pasta (compactada) junto com a planilha para ajustar o robô.

Cada folha leva alguns segundos: o robô lê a folha inteira e, se faltar alguma informação, lê de novo
em 6 pedaços ampliados (o OCR do Windows encolhe a folha inteira e a letra miúda fica ilegível).

Se o Windows perguntar se deseja executar o arquivo baixado, clique em **Executar**
(ou: botão direito no arquivo → Propriedades → marque **Desbloquear**).

Opções (pelo Prompt de Comando, na pasta do robô):

```
powershell -ExecutionPolicy Bypass -File robo_nf.ps1 -Pasta "C:\Scans\Outubro"
powershell -ExecutionPolicy Bypass -File robo_nf.ps1 -Saida "C:\Scans\NFs_outubro.xlsx"
powershell -ExecutionPolicy Bypass -File robo_nf.ps1 -SalvarTexto      # salva o texto lido (textos_ocr/)
```

Observações:
- Se o Windows estiver em português, o OCR em português já vem instalado. Em outro idioma,
  o robô usa o OCR do idioma do sistema (números e nomes continuam sendo lidos, só os acentos podem falhar).
- Se a empresa bloquear scripts do PowerShell, o robô avisa e não roda. Nesse caso use a opção 2
  (pedindo ao TI para instalar) ou envie os scans para o Claude no chat.
- Esta versão não lê o código de barras do DANFE; o nº da NF vem da chave de acesso impressa
  ou do "Nº 000.012.345".

## Opção 2 — Versão Python (precisa instalar)

Um pouco mais robusta (lê também o código de barras do DANFE e tenta mais de um tratamento de
imagem). Requer instalar:

1. **Python 3.9 ou mais novo**: https://www.python.org/downloads/
   (no instalador, marque *"Add Python to PATH"*).
2. **Tesseract OCR**:
   - Windows: https://github.com/UB-Mannheim/tesseract/wiki — em *Additional language data*, marque **Portuguese**.
   - Linux: `sudo apt install tesseract-ocr tesseract-ocr-por libzbar0`
   - Mac: `brew install tesseract tesseract-lang zbar`
3. **Bibliotecas Python**: `pip install -r requirements.txt`

Se o Tesseract foi instalado em uma pasta diferente da padrão, informe o caminho na variável
de ambiente `TESSERACT_CMD`.

Para usar: coloque as NFs na pasta `notas` e dê dois cliques em **`executar_robo.bat`**
(ou rode `python robo_nf.py`). Opções:

```
python robo_nf.py "C:\Scans\Outubro"          # ler outra pasta
python robo_nf.py notas -o NFs_outubro.xlsx    # escolher o nome da planilha
python robo_nf.py notas --salvar-texto         # salvar o texto lido de cada página (textos_ocr/)
```

Nas duas versões, se a planilha estiver aberta no Excel, o robô salva uma cópia com data e hora no nome.

## Como o robô encontra cada informação

- **Etiqueta de recebimento**: se a folha tiver a etiqueta impressa pelo recebimento (`NF 12345` e, na
  linha de baixo, o fornecedor), o número da NF e o fornecedor vêm dela: a letra é grande e o OCR lê bem.
  Se a etiqueta disser `(continuação)`, a folha é juntada à NF principal, mesmo escaneada em outro arquivo.
- **Nº da NF**: primeiro pela **chave de acesso** (os 44 números impressos ou, na versão Python,
  o código de barras do DANFE). A chave tem dígito verificador, então quando ela é lida o número está certo.
  Se não conseguir ler a chave, usa o número impresso (`Nº 000.012.345`, `Nº 47158 SÉRIE 1`...),
  corrigindo zeros lidos como letra O (`OOO.O47.158`).
  A inscrição estadual (que em SC tem o mesmo formato `999.999.999`) é ignorada.
  Se a chave veio com algum dígito ilegível, o número dela é usado só para conferir o impresso
  (ou, se não houver outro, entra na planilha marcado para conferência).
- **Fornecedor**: pela frase do canhoto *"RECEBEMOS DE <fornecedor> OS PRODUTOS…"*; se não achar,
  pelo bloco *Identificação do Emitente*, e por último pela primeira linha com LTDA / S.A. / EIRELI / ME
  antes do destinatário. Também funciona com NFS-e (bloco *Prestador de Serviços*).
  Nomes ilegíveis (lixo do OCR), endereços e linhas de produto são descartados: é melhor a célula
  vazia e marcada para conferir do que um nome errado. O mesmo fornecedor lido de jeitos diferentes
  em NFs diferentes (ex.: `MARVIN DO BRASL`) passa a usar a leitura completa (`MARVIN DO BRASIL
  FERRAMENTAS INDUSTRIAIS LTDA`), e NFs do mesmo CNPJ ficam com o mesmo nome.
- **Valor total**: o valor que fica logo abaixo de *VALOR TOTAL DA NOTA* (pela posição na folha, para não
  pegar o valor da coluna vizinha, como o IPI). Aceita os erros comuns do OCR no rótulo (`'ALOR TOTPA. DA`,
  `VALOR NOTA`) e no valor (ponto no lugar da vírgula, `777 58` partido em dois).
  Fica em amarelo quando a leitura é duvidosa (sem a vírgula, como `487`, ou com o começo perdido, como
  `031.27`) ou quando só o *VALOR TOTAL DOS PRODUTOS* foi lido. Se nada for lido, a célula fica vazia
  (o robô não inventa valor).
- **Pedido**: qualquer número de 10 dígitos começando com **45** (ex.: `4500012345`), em qualquer
  lugar da folha. Corrige trocas comuns do OCR (`45000I2345` → `4500012345`). Se uma NF tiver
  mais de um pedido, eles aparecem separados por ` / `.

Se os seus pedidos tiverem outro tamanho, altere `DIGITOS_PEDIDO` no começo do `robo_nf.py`
(ou `$DigitosPedido` no `robo_nf.ps1`).

## Opcional: cadastro de fornecedores

Para que o nome do fornecedor saia sempre igual (e não do jeito que o OCR leu), crie um arquivo
**`fornecedores.csv`** nesta pasta com o CNPJ e o nome que você quer na planilha (pode salvar
direto do Excel como *CSV separado por ponto e vírgula*):

```
CNPJ;Fornecedor
12.345.678/0001-95;Fornecedor Exemplo Ind. e Com.
98.765.432/0001-98;Metalúrgica Silva
```

Quando o CNPJ do emitente for encontrado na NF, o robô usa o nome do cadastro.

## Dicas para uma boa leitura

- Escaneie em **300 dpi ou mais, em tons de cinza**. Esta é a configuração que mais melhora a leitura:
  nos DANFEs em paisagem a letra é miúda, e com resolução baixa o OCR do Windows troca letras e perde
  vírgulas (é o que mais faz o valor total ficar em branco).
- Folhas tortas ou de cabeça para baixo são corrigidas automaticamente, mas quanto mais reta, melhor.
- Se alguma NF vier errada, rode com `-SalvarTexto` (PowerShell) ou `--salvar-texto` (Python) e veja
  em `textos_ocr/` o que o OCR leu.

## Testes

```
powershell -ExecutionPolicy Bypass -File test_robo_nf.ps1
python -m unittest test_robo_nf.py
```
