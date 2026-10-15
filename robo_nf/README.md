# Robô de leitura de Notas Fiscais escaneadas

Lê as NFs escaneadas (PDF, JPG, PNG, TIF) e monta uma planilha Excel com:

| Fornecedor | Nº NF | Pedido | Série | CNPJ Fornecedor | Chave de Acesso | Arquivo | Página | Status |
|---|---|---|---|---|---|---|---|---|
| FORNECEDOR EXEMPLO LTDA | 12345 | 4500012345 | 1 | 12.345.678/0001-95 | 3526…0979 | nf_01.pdf | 1 | OK |

As linhas que precisam de conferência ficam **amarelas**, e a coluna *Status* diz o motivo
(pedido não encontrado, mais de um pedido, NF repetida etc.).

## Instalação (uma vez só)

1. **Python 3.9 ou mais novo**: https://www.python.org/downloads/
   (no instalador, marque *"Add Python to PATH"*).
2. **Tesseract OCR** (o "leitor" de texto das imagens):
   - Windows: baixe o instalador em https://github.com/UB-Mannheim/tesseract/wiki.
     Durante a instalação, em *Additional language data*, marque **Portuguese**.
   - Linux: `sudo apt install tesseract-ocr tesseract-ocr-por libzbar0`
   - Mac: `brew install tesseract tesseract-lang zbar`
3. **Bibliotecas Python**: abra o terminal (Prompt de Comando) nesta pasta e rode:

   ```
   pip install -r requirements.txt
   ```

Se o Tesseract foi instalado em uma pasta diferente da padrão, informe o caminho na variável
de ambiente `TESSERACT_CMD` (ex.: `C:\Ferramentas\Tesseract-OCR\tesseract.exe`).

## Como usar

1. Escaneie as NFs e salve os arquivos na pasta **`notas`** (ao lado do `robo_nf.py`).
   Pode ser um arquivo por NF ou um PDF com várias folhas; folhas em branco (verso) são ignoradas.
2. No Windows, dê dois cliques em **`executar_robo.bat`**. Ou, pelo terminal:

   ```
   python robo_nf.py
   ```

3. A planilha **`planilha_nfs.xlsx`** é criada nesta pasta.

Outras opções:

```
python robo_nf.py "C:\Scans\Outubro"          # ler outra pasta
python robo_nf.py notas -o NFs_outubro.xlsx    # escolher o nome da planilha
python robo_nf.py notas --salvar-texto         # salvar o texto lido de cada página (textos_ocr/)
```

Se a planilha estiver aberta no Excel, o robô salva uma cópia com data e hora no nome.

## Como o robô encontra cada informação

- **Nº da NF**: primeiro pela **chave de acesso** (código de barras do DANFE ou os 44 números
  impressos). A chave tem dígito verificador, então quando ela é lida o número está certo.
  Se não conseguir ler a chave, usa o número impresso no formato `Nº 000.012.345`.
- **Fornecedor**: pela frase do canhoto *"RECEBEMOS DE <fornecedor> OS PRODUTOS…"*; se não achar,
  pelo bloco *Identificação do Emitente*, e por último pela primeira linha com LTDA / S.A. / EIRELI / ME
  antes do destinatário. Também funciona com NFS-e (bloco *Prestador de Serviços*).
- **Pedido**: qualquer número de 10 dígitos começando com **45** (ex.: `4500012345`), em qualquer
  lugar da folha. Corrige trocas comuns do OCR (`45000I2345` → `4500012345`). Se uma NF tiver
  mais de um pedido, eles aparecem separados por ` / `.

Se os seus pedidos tiverem outro tamanho, altere `DIGITOS_PEDIDO` no começo do `robo_nf.py`.

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

- Escaneie em **300 dpi**, preto e branco ou tons de cinza.
- Folhas tortas ou de cabeça para baixo são corrigidas automaticamente, mas quanto mais reta, melhor.
- Se alguma NF vier errada, rode com `--salvar-texto` e veja em `textos_ocr/` o que o OCR leu.

## Testes

```
python -m unittest test_robo_nf.py
```
