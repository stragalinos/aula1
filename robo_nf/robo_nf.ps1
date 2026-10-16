<#
.SYNOPSIS
    Robo de leitura de Notas Fiscais escaneadas - versao que NAO precisa instalar nada.

.DESCRIPTION
    Usa apenas o que ja vem no Windows 10/11: o Windows PowerShell e o OCR do proprio Windows.
    Le os PDFs/imagens da pasta "notas" e gera a planilha planilha_nfs.xlsx com:

        Fornecedor | No NF | Pedido (45...) | + colunas para conferencia

.EXAMPLE
    Dois cliques em executar_robo_windows.bat

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File robo_nf.ps1 -Pasta "C:\Scans" -Saida "C:\Scans\nfs.xlsx"
#>
param(
    [string]$Pasta,
    [string]$Saida,
    [string]$Cadastro,
    [switch]$SalvarTexto
)

if ($ExecutionContext.SessionState.LanguageMode -ne 'FullLanguage') {
    Write-Host 'O PowerShell deste computador esta em modo restrito (bloqueado pela empresa),'
    Write-Host 'entao o robo nao consegue usar o OCR do Windows aqui.'
    exit 1
}

# ----------------------------------------------------------------------------
# Configuracoes
# ----------------------------------------------------------------------------

# Pedido de compra: comeca com "45" e tem 10 digitos (padrao SAP, ex.: 4500012345).
# Se os seus pedidos tiverem outro tamanho, e so ajustar aqui.
$PrefixoPedido = '45'
$DigitosPedido = 10

$Extensoes = '.pdf', '.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp'
$DpiPdf = 300
$CodigosUF = 11, 12, 13, 14, 15, 16, 17, 21, 22, 23, 24, 25, 26, 27, 28, 29,
             31, 32, 33, 35, 41, 42, 43, 50, 51, 52, 53

function U([string]$s) { [regex]::Unescape($s) }  # textos com acento (o arquivo fica so em ASCII)

# ----------------------------------------------------------------------------
# Expressoes usadas na leitura do texto
# ----------------------------------------------------------------------------

function NovaRegex([string]$padrao, [string]$opcoes = 'None') {
    [regex]::new($padrao, [System.Text.RegularExpressions.RegexOptions]$opcoes)
}

$RestoPedido = $DigitosPedido - $PrefixoPedido.Length
$RePedido = NovaRegex "(?<!\d)$PrefixoPedido\d{$RestoPedido}(?!\d)"
$RePedidoInteiro = NovaRegex "^$PrefixoPedido\d{$RestoPedido}\z"
# "Pedido: 4500 012345", "PED. 45000I2345", "Ordem de compra no ..." (numeros quebrados pelo OCR)
$RePedidoRotulo = NovaRegex ('(?:PEDIDO|\bPED\b|\bP\.?\s?O\b|XPED|ORDEM\s+DE\s+COMPRA|\bO\.?C\b)' +
                     '[^\d\n]{0,25}?([0-9OQDIL|][0-9OQDIL| .\-/]{8,20})')

# Chave de acesso impressa em 11 grupos de 4 (aceita CNPJ alfanumerico)
$ReChaveAgrupada = NovaRegex '(?<![0-9A-Z])(?:[0-9A-Z]{4}[ .]{0,2}){10}[0-9A-Z]{4}(?![0-9A-Z])'
$ReSeqDigitos = NovaRegex '\d(?:[ .]{0,2}\d){43,}'

# Numero da NF no DANFE: "N. 000.012.345"
$ReRotuloChave = NovaRegex 'CHAVE\s+DE\s+ACESSO'

# (o OCR as vezes poe espaco junto dos pontos)
$NfPontuado = '\d{3}\s?[.,]\s?\d{3}\s?[.,]\s?\d{3}'
$NfEspacado = '\d{3}\s?[.,\s]\s?\d{3}\s?[.,\s]\s?\d{3}'
$ReNfDanfeRotulo = NovaRegex ('\bN\s*[O0\u00B0Q.:\-\u2022*]{0,3}\s*[:.]?\s*(' + $NfEspacado + ')(?!\d|[.,/-]\d)')
# "NO 000061234": numero sem pontos, com zeros a esquerda
$ReNfRotuloZeros = NovaRegex '\bN\s*[O0\u00B0Q.:\-\u2022*]{0,3}\s*[:.]?\s*(0\d{5,8})(?!\d)'
# Etiqueta de recebimento colada na folha: "NF 12345" e, na linha de baixo, o fornecedor
$ReEtiquetaNF = NovaRegex '(?:^|\|[ \t])NF[ \t]*[:.]?[ \t]*(\d{3,9})(?=[ \t]*(?:$|\||\())' 'Multiline'
# "000047158" logo antes de "SERIE" (sem o "N.")
$ReNfZerosSerie = NovaRegex '(?<![\d.,])(0\d{5,8})\s*[-|]?\s*\n?\s*SERIE\b'
# "N. 47158  SERIE 1" / "N. 000047158" e na linha de baixo "SERIE 001"
$ReNfAntesSerie = NovaRegex '\bN\s*[O0\u00B0.:\-]{0,3}\s*[:.]?\s*(\d{1,9}|\d{1,3}(?:\.\d{3}){1,2})\s*[-|]?\s*\n?\s*SERIE\b'
$ReNfDanfe = NovaRegex ('(?<![\d./,-])(' + $NfPontuado + ')(?!\d|[.,/-]\d)')
# A inscricao estadual de SC (e de outros estados) tem o mesmo formato 999.999.999
$ReContextoIE = NovaRegex 'INSCRI|\bI\.?\s?E\b'
$ReNfOutros = @(  # outros layouts (NFS-e, notas antigas...)
    (NovaRegex 'NUMERO\s+DA\s+(?:NOTA|NFS?-?E|NF)\b[^\d\n]{0,25}(\d[\d.]{0,10})'),
    (NovaRegex '\bN[O0\u00B0.]*\s*(?:DA\s+)?(?:NOTA|NFS?-?E|NF)\b[^\d\n]{0,10}(\d[\d.]{0,10})'),
    (NovaRegex 'NOTA\s+FISCAL[^\d\n]{0,30}?\bN[O0\u00B0.:]+\s*(\d[\d.]{0,10})')
)
# Valor total da NF: "VALOR TOTAL DA NOTA" (o valor fica logo abaixo, no DANFE)
# (o OCR troca a virgula por ponto: "1.905.42", "618.30")
$Dinheiro = '(?:\d{1,3}(?:[.,]\d{3})+|\d+)[.,]\d{2}'
$ReDinheiro = NovaRegex ('(?<![\d.,])(' + $Dinheiro + ')(?!\d|[.,]\d|%)')
$ReDinheiroPalavra = NovaRegex ('^(?:R\$|RS)?(' + $Dinheiro + ')\z')
$ReMilharPalavra = NovaRegex '^(?:R\$|RS)?(\d{1,3}(?:[.,]\d{3})*|\d+)[.,]?\z'  # "777" de "777 58"
$ReCentavosPalavra = NovaRegex '^\d{2}\z'
$ReSoDigitos = NovaRegex '^\d{3,8}\z'  # "487": a virgula sumiu
$RotuloTotal = '(?:\b(?:VALOR|VLR|V)\b\.?\s*)?\bTOTAL\.?\s*(?:DA\s*)?(?:NOTA|NF-?E?)\b'
$ReRotuloTotal = NovaRegex $RotuloTotal
$ReTotalMesmaLinha = NovaRegex ($RotuloTotal + '[ \t:=|]*(?:R\s?\$)?[ \t]*(' + $Dinheiro + ')(?![\d,%])')
$ReValorTotalRS = NovaRegex ('\bVALOR\s+T[A-Z]{3,4}\.?\s*:?\s*R\s?[$S]\s*(' + $Dinheiro + ')(?!\d|[.,]\d|%)')
$ReLetras = NovaRegex '[A-Z]{2}'
$PrioridadeValor = @{ 'rotulo' = 3; 'rotulo_duvidoso' = 2; 'produtos' = 1; '' = 0 }

$ReSerie = NovaRegex '\bSERIE\s*[:.]?\s*(\d{1,3})(?!\d)'

$ReCnpj = NovaRegex '(?<![0-9A-Z])([0-9A-Z]{2})\.?([0-9A-Z]{3})\.?([0-9A-Z]{3})\s?/\s?([0-9A-Z]{4})\s?-?\s?(\d{2})(?!\d)'

$RePalavra = NovaRegex '\S+'
$FimDoCanhoto = 'PRODUTOS', 'PRODUTO', 'SERVICOS', 'MERCADORIAS', 'MERCADORIA', 'ITENS'
$ReEmitente = NovaRegex 'IDENTIFICA\w*\s+DO\s+EMITENTE'
$RePrestador = NovaRegex 'PRESTADOR'
$ReRazaoSocial = NovaRegex '(?:NOME\s*/\s*)?RAZAO\s+SOCIAL\s*[:.]?\s*'
$ReFimEmitente = NovaRegex 'DESTINAT|TOMADOR'
$ReSufixo = NovaRegex '\b(?:LTDA|EIRELI|EPP|ME|S[./]?\s?A)\b\.?'
$ReSufixoFinal = NovaRegex '\b(?:LTDA|EIRELI|EPP|ME|S[./]?\s?A)\b\.?\s*\z'
$ReTokenLegivel = NovaRegex "^[\w&.,'/()\-]+\z"
$Conectores = 'DE', 'DO', 'DA', 'DOS', 'DAS', 'E', 'EM'
$SufixosEmpresa = 'LTDA', 'LTD', 'LT', 'SA', 'ME', 'EPP', 'EIRELI', 'CIA'
$ReEndereco = NovaRegex '^\s*(?:RUA|AV|AVENIDA|RODOVIA|ROD|ESTRADA|ALAMEDA|TRAVESSA|PRACA|LARGO)\b'
$ReCidadeUF = NovaRegex '[-/]\s*(?:AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)\s*\z'
$ReRotulos = NovaRegex ('\b(?:DANFE|DOCUMENTO\s+AUXILIAR|NOTA\s+FISCAL|CNPJ|INSCRICAO|CHAVE\s+DE\s+ACESSO|' +
                'ENTRADA|SAIDA|NATUREZA|IDENTIFICACAO|PROTOCOLO|FOLHA|SERIE|ENDERECO|FONE|CEP|' +
                'DESTINAT\w*|REMETENTE|CODIGO|DESCRICAO|NCM|CFOP|QTDE?|QUANTIDADE|VALOR\s+TOTAL|' +
                'DADOS\s+(?:DOS?|ADICIONAIS)|CALCULO\s+DO\s+IMPOSTO|TRANSPORTADOR\w*|FATURA|DUPLICATAS?)\b')
$Pedacos = foreach ($faixaV in @(@(0.0, 0.37, 0.0, 0.345), @(0.32, 0.37, 0.345, 0.66), @(0.63, 0.37, 0.66, 1.0))) {
    foreach ($faixaH in @(@(0.0, 0.55, 0.0, 0.5), @(0.45, 0.55, 0.5, 1.0))) {
        [pscustomobject]@{
            Recorte = @($faixaH[0], $faixaV[0], $faixaH[1], $faixaV[1])
            Nucleo = @($faixaH[2], $faixaV[2], $faixaH[3], $faixaV[3])
        }
    }
}

# Palavras que aparecem em qualquer DANFE: servem para saber se a folha foi lida na posicao certa
$RePalavrasDanfe = NovaRegex ('\b(?:DANFE|NOTA|FISCAL|CNPJ|EMITENTE|DESTINAT\w*|PRODUTOS?|VALOR|TOTAL|ICMS|' +
    'DATA|SERIE|CHAVE|ACESSO|NATUREZA|OPERACAO|INSCRICAO|ESTADUAL|ENDERECO|MUNICIPIO|QUANTIDADE|PEDIDO|' +
    'TRANSPORTADOR|FRETE|RECEBEMOS|EMISSAO|BAIRRO|CEP|FONE|PESO|IMPOSTO|DESCRICAO|CODIGO)\b')

# Letras que o OCR costuma confundir com numeros
$ReLetraEntreDigitos = NovaRegex '(?<=\d)[OQDILS|B]{1,3}(?=[\d.])|(?<=[\d.])[OQDILS|B]{1,3}(?=\d)'

# ----------------------------------------------------------------------------
# Leitura do texto
# ----------------------------------------------------------------------------

function NovoDados {
    [pscustomobject]@{
        Fornecedor = ''; Cnpj = ''; NumeroNF = ''; Serie = ''
        Pedidos = (New-Object 'System.Collections.Generic.List[string]')
        Chave = ''; OrigemNF = ''  # OrigemNF: "chave", "danfe", "texto", "chave_parcial" ou "divergente"
        ValorTotal = ''; OrigemValor = ''  # "1234.56"; "rotulo", "rotulo_duvidoso" ou "produtos"
        Continuacao = $false  # etiqueta diz "(continuacao)": folha seguinte de outra NF
    }
}

function Completo($d) {
    [bool]($d.Fornecedor -and $d.NumeroNF -and $d.Pedidos.Count -gt 0 -and $d.OrigemValor -eq 'rotulo')
}

function Vazio($d) { -not ($d.Fornecedor -or $d.NumeroNF -or $d.Pedidos.Count -gt 0 -or $d.Chave) }

function CompletarCom($d, $outro) {
    # Preenche o que estiver faltando com os dados de outra pagina da mesma NF
    foreach ($campo in 'Fornecedor', 'Cnpj', 'NumeroNF', 'Serie', 'Chave', 'OrigemNF', 'ValorTotal', 'OrigemValor') {
        if (-not $d.$campo) { $d.$campo = $outro.$campo }
    }
    if ($PrioridadeValor[$outro.OrigemValor] -gt $PrioridadeValor[$d.OrigemValor]) {
        $d.ValorTotal = $outro.ValorTotal; $d.OrigemValor = $outro.OrigemValor
    }
    foreach ($p in $outro.Pedidos) { if (-not $d.Pedidos.Contains($p)) { $d.Pedidos.Add($p) } }
}

function Normalizar([string]$texto) {
    # Maiusculas e sem acentos, mantendo cada caractere na mesma posicao
    $sb = New-Object System.Text.StringBuilder $texto.Length
    foreach ($c in $texto.ToCharArray()) {
        if ([int]$c -lt 128) { [void]$sb.Append([char]::ToUpperInvariant($c)); continue }
        $base = New-Object System.Text.StringBuilder
        foreach ($x in ([string]$c).Normalize([System.Text.NormalizationForm]::FormKD).ToCharArray()) {
            if ([Globalization.CharUnicodeInfo]::GetUnicodeCategory($x) -ne 'NonSpacingMark') { [void]$base.Append($x) }
        }
        $base = $base.ToString().ToUpperInvariant()
        if ($base.Length -eq 1) { [void]$sb.Append($base) } else { [void]$sb.Append($c) }
    }
    $sb.ToString()
}

$TrocaDigitos = ('O', '0'), ('Q', '0'), ('D', '0'), ('I', '1'), ('L', '1'), ('|', '1'), ('S', '5'), ('B', '8'), ('Z', '2')
$LetrasConfusas = 'OQDILSBZ|'
$ReTokenNumerico = NovaRegex '[0-9OQDILSBZ|][0-9OQDILSBZ|.,/\-]*'

function TrocarDigitos([string]$s) {
    foreach ($par in $TrocaDigitos) { $s = $s.Replace($par[0], $par[1]) }
    $s
}

function CorrigirToken([string]$token) {
    # Token quase todo numerico com letras parecidas com numeros: OOO.O47.158 -> 000.047.158
    $digitos = 0; $letras = 0; $todasConfusas = $true
    foreach ($c in $token.ToCharArray()) {
        if ([char]::IsDigit($c)) { $digitos++ }
        elseif ([char]::IsLetter($c) -or $c -eq '|') {
            $letras++
            if ($LetrasConfusas.IndexOf($c) -lt 0) { $todasConfusas = $false }
        }
    }
    if ($digitos -ge 3 -and $letras -gt 0 -and $digitos -ge $letras -and $todasConfusas) { return TrocarDigitos $token }
    $token
}

function CorrigirDigitos([string]$texto) {
    # Troca letras confundidas pelo OCR em numeros (OOO.O47.158, 45000I2345)
    $texto = $ReTokenNumerico.Replace($texto, { param($m) CorrigirToken $m.Value })
    for ($i = 0; $i -lt 3; $i++) {
        $novo = $ReLetraEntreDigitos.Replace($texto, { param($m) TrocarDigitos $m.Value })
        if ($novo -ceq $texto) { break }
        $texto = $novo
    }
    $texto
}

function DvMod11([string]$base, [int[]]$pesos) {
    $soma = 0
    for ($i = 0; $i -lt $base.Length -and $i -lt $pesos.Length; $i++) {
        $soma += ([int]$base[$i] - 48) * $pesos[$i]  # digitos 0-9 e letras do CNPJ alfanumerico
    }
    $resto = $soma % 11
    if ($resto -lt 2) { 0 } else { 11 - $resto }
}

function ChavePlausivel([string]$chave) {
    # Confere estrutura e digito verificador da chave de acesso (44 posicoes)
    if (-not $chave -or $chave -cnotmatch '^\d{6}[0-9A-Z]{12}\d{26}\z') { return $false }
    if ($CodigosUF -notcontains [int]$chave.Substring(0, 2)) { return $false }
    $mes = [int]$chave.Substring(4, 2)
    if ($mes -lt 1 -or $mes -gt 12) { return $false }
    if ('55', '65' -notcontains $chave.Substring(20, 2)) { return $false }  # 55 = NF-e, 65 = NFC-e
    $invertida = -join $chave.Substring(0, 43).ToCharArray()[42..0]
    (DvMod11 $invertida (@(2, 3, 4, 5, 6, 7, 8, 9) * 6)) -eq [int]$chave.Substring(43, 1)
}

function ChaveEstruturaOk([string]$chave) {
    # Chave com estrutura e CNPJ validos, sem conferir o ultimo digito (o OCR errou algum numero)
    if (-not $chave -or $chave -cnotmatch '^\d{6}[0-9A-Z]{12}\d{26}\z') { return $false }
    if ($CodigosUF -notcontains [int]$chave.Substring(0, 2)) { return $false }
    $mes = [int]$chave.Substring(4, 2)
    if ($mes -lt 1 -or $mes -gt 12) { return $false }
    if ('55', '65' -notcontains $chave.Substring(20, 2)) { return $false }
    CnpjValido $chave.Substring(6, 14)
}

function CnpjValido([string]$cnpj) {
    if ($cnpj -cnotmatch '^[0-9A-Z]{12}\d{2}\z' -or $cnpj -cmatch '^(.)\1*\z') { return $false }
    $pesos = 6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2
    ((DvMod11 $cnpj.Substring(0, 12) $pesos[1..12]) -eq [int]$cnpj.Substring(12, 1)) -and
    ((DvMod11 $cnpj.Substring(0, 13) $pesos) -eq [int]$cnpj.Substring(13, 1))
}

function FormatarCnpj([string]$cnpj) {
    if ($cnpj.Length -ne 14) { return $cnpj }
    '{0}.{1}.{2}/{3}-{4}' -f $cnpj.Substring(0, 2), $cnpj.Substring(2, 3), $cnpj.Substring(5, 3),
                             $cnpj.Substring(8, 4), $cnpj.Substring(12, 2)
}

function EncontrarChave([string]$texto, [string]$validar = 'ChavePlausivel') {
    foreach ($m in $ReChaveAgrupada.Matches($texto)) {
        $chave = $m.Value -creplace '[ .]', ''
        if (& $validar $chave) { return $chave }
    }
    $trechos = New-Object 'System.Collections.Generic.List[string]'
    foreach ($m in $ReSeqDigitos.Matches($texto)) { $trechos.Add($m.Value) }
    # chave quebrada em mais de uma linha: junta os digitos logo depois de "CHAVE DE ACESSO"
    foreach ($m in $ReRotuloChave.Matches($texto)) {
        $depois = $m.Index + $m.Length
        $trechos.Add($texto.Substring($depois, [Math]::Min(250, $texto.Length - $depois)))
    }
    foreach ($trecho in $trechos) {
        $digitos = $trecho -creplace '\D', ''
        for ($i = 0; $i -le $digitos.Length - 44; $i++) {
            if (& $validar $digitos.Substring($i, 44)) { return $digitos.Substring($i, 44) }
        }
    }
    ''
}

function SoNumero([string]$trecho) {
    $digitos = $trecho -creplace '[^0-9]', ''
    if ($digitos.Length -eq 0 -or $digitos.Length -gt 9 -or [long]$digitos -eq 0) { return '' }
    [string][long]$digitos
}

function PertoDeIE([string]$texto, [int]$inicio) {
    $de = [Math]::Max(0, $inicio - 40)
    $ReContextoIE.IsMatch($texto.Substring($de, $inicio - $de))
}

function EncontrarNumeroNF([string]$texto) {
    # Devolve @(numero, origem). Texto ja normalizado e com digitos corrigidos.
    foreach ($regex in @($ReNfDanfeRotulo, $ReNfRotuloZeros, $ReNfAntesSerie, $ReNfZerosSerie)) {
        foreach ($m in $regex.Matches($texto)) {
            $n = SoNumero $m.Groups[1].Value
            if ($n -and -not (PertoDeIE $texto $m.Index)) { return @($n, 'danfe') }
        }
    }

    # Sem o "N." na frente: so numeros com zeros a esquerda (000.012.345), que nao sao a IE
    $contagem = @{}
    $ordem = New-Object 'System.Collections.Generic.List[string]'
    foreach ($m in $ReNfDanfe.Matches($texto)) {
        if (-not $m.Groups[1].Value.StartsWith('0') -or (PertoDeIE $texto $m.Index)) { continue }
        $n = SoNumero $m.Groups[1].Value
        if (-not $n) { continue }
        if (-not $contagem.ContainsKey($n)) { $contagem[$n] = 0; $ordem.Add($n) }
        $contagem[$n]++
    }
    if ($ordem.Count -gt 0) {
        $melhor = $ordem[0]
        foreach ($n in $ordem) { if ($contagem[$n] -gt $contagem[$melhor]) { $melhor = $n } }
        return @($melhor, 'danfe')
    }
    foreach ($regex in $ReNfOutros) {
        foreach ($m in $regex.Matches($texto)) {
            $n = SoNumero $m.Groups[1].Value
            if ($n) { return @($n, 'texto') }
        }
    }
    @('', '')
}

function ValorDecimal([string]$valor) {
    # "1.234,56", "1.234.56" ou "123456" -> "1234.56" (os dois ultimos digitos sao os centavos)
    $digitos = $valor -creplace '[^0-9]', ''
    $inteiro = if ($digitos.Length -gt 2) { [string][long]$digitos.Substring(0, $digitos.Length - 2) } else { '0' }
    "$inteiro.$($digitos.Substring($digitos.Length - 2))"
}

function DecimalDe([string]$valor) { [decimal]::Parse($valor, [Globalization.CultureInfo]::InvariantCulture) }

function EncontrarValorTotal([string]$texto) {
    # Valor total da NF pelo texto. Devolve @(valor, 'rotulo') ou @('', '').
    foreach ($regex in @($ReTotalMesmaLinha, $ReValorTotalRS)) {
        foreach ($m in $regex.Matches($texto)) {
            $valor = ValorDecimal $m.Groups[1].Value
            if ((DecimalDe $valor) -gt 0) { return @($valor, 'rotulo') }
        }
    }
    # Rotulo no fim da linha e os valores na linha de baixo: o ultimo valor e o da coluna dele
    $linhas = $texto.Split("`n")
    for ($i = 0; $i -lt $linhas.Count; $i++) {
        foreach ($m in $ReRotuloTotal.Matches($linhas[$i])) {
            if ($ReLetras.IsMatch($linhas[$i].Substring($m.Index + $m.Length))) { continue }  # coluna incerta
            for ($j = $i + 1; $j -lt [Math]::Min($i + 3, $linhas.Count); $j++) {
                $valores = @($ReDinheiro.Matches($linhas[$j]) | ForEach-Object { ValorDecimal $_.Groups[1].Value })
                if ($valores.Count -gt 0) {
                    if ((DecimalDe $valores[-1]) -gt 0) { return @($valores[-1], 'rotulo') }
                    break
                }
            }
        }
    }
    @('', '')
}

function Inclinacao($palavras) {
    # Inclinacao da folha (scanner torto), medida entre palavras vizinhas da mesma linha do OCR
    $lista = New-Object 'System.Collections.Generic.List[double]'
    for ($i = 0; $i -lt $palavras.Count - 1; $i++) {
        $a = $palavras[$i]; $b = $palavras[$i + 1]
        if ($a.Count -gt 5 -and $b.Count -gt 5 -and $a[5] -eq $b[5]) {
            $dx = ([double]$b[1] + [double]$b[3] / 2) - ([double]$a[1] + [double]$a[3] / 2)
            if ($dx -gt 0) {
                $s = (([double]$b[2] + [double]$b[4] / 2) - ([double]$a[2] + [double]$a[4] / 2)) / $dx
                if ([Math]::Abs($s) -le 0.1) { $lista.Add($s) }
            }
        }
    }
    if ($lista.Count -eq 0) { return 0.0 }
    $lista.Sort()
    $lista[[int][Math]::Floor(($lista.Count - 1) / 2)]
}

function LinhasVisuais($palavras) {
    # Agrupa as palavras @(texto, x, y, largura, altura, linha do OCR) nas linhas em que aparecem
    # na folha (descontando a inclinacao de uma folha escaneada torta)
    $saida = New-Object 'System.Collections.Generic.List[object]'
    if ($palavras.Count -eq 0) { return , $saida }
    $inclinacao = Inclinacao $palavras
    $centros = New-Object 'double[]' $palavras.Count
    for ($i = 0; $i -lt $palavras.Count; $i++) {
        $p = $palavras[$i]
        $centros[$i] = [double]$p[2] + [double]$p[4] / 2 - $inclinacao * ([double]$p[1] + [double]$p[3] / 2)
    }
    $ordem = @(0..($palavras.Count - 1) | Sort-Object @{ E = { $centros[$_] } }, @{ E = { [double]$palavras[$_][1] } }, @{ E = { $_ } })
    $linhas = New-Object 'System.Collections.Generic.List[object]'
    foreach ($i in $ordem) {
        $altura = [double]$palavras[$i][4]
        $centro = $centros[$i]
        if ($linhas.Count -gt 0) {  # compara com o centro medio da linha
            $ultima = $linhas[$linhas.Count - 1]
            if ([Math]::Abs($centro - $ultima.Soma / $ultima.Indices.Count) -le 0.5 * [Math]::Max($altura, $ultima.Altura)) {
                $ultima.Soma += $centro
                $ultima.Indices.Add($i)
                continue
            }
        }
        $nova = [pscustomobject]@{ Soma = $centro; Altura = $altura; Indices = (New-Object 'System.Collections.Generic.List[int]') }
        $nova.Indices.Add($i)
        $linhas.Add($nova)
    }
    foreach ($l in $linhas) {
        $saida.Add(@($l.Indices | Sort-Object @{ E = { [double]$palavras[$_][1] } }, @{ E = { $_ } }))
    }
    , $saida
}

function TextoVisual($palavras) {
    # Texto montado pela posicao das palavras: cada rotulo fica junto do seu numero/valor
    $saida = New-Object 'System.Collections.Generic.List[string]'
    foreach ($linha in (LinhasVisuais $palavras)) {
        $sb = New-Object System.Text.StringBuilder
        $anterior = -1
        foreach ($i in $linha) {
            $p = $palavras[$i]
            if ($anterior -ge 0) {
                $a = $palavras[$anterior]
                $vao = [double]$p[1] - ([double]$a[1] + [double]$a[3])
                if ($vao -gt 2 * [Math]::Max([double]$p[4], [double]$a[4])) { [void]$sb.Append(' | ') } else { [void]$sb.Append(' ') }
            }
            [void]$sb.Append([string]$p[0])
            $anterior = $i
        }
        $saida.Add($sb.ToString())
    }
    $saida -join "`n"
}

function Letras([string]$texto) { (Normalizar $texto) -creplace '[^A-Z]', '' }

function RotulosDeValor($palavras, $linha) {
    # Rotulos "VALOR TOTAL DA NOTA" ('nota') e "VALOR TOTAL DOS PRODUTOS" ('produtos') numa linha
    # da folha, aceitando erros do OCR: "'ALOR TOTPA. DA NOTA", "VALmTOTALDAN01A", "VALOR NOTA".
    $t = @(foreach ($i in $linha) { Letras ([string]$palavras[$i][0]) })
    $achados = New-Object 'System.Collections.Generic.List[object]'
    for ($a = 0; $a -lt $t.Count; $a++) {
        $token = $t[$a]
        $prox = if ($a + 1 -lt $t.Count) { $t[$a + 1] } else { '' }
        $depois = if ($a + 2 -lt $t.Count) { $t[$a + 2] } else { '' }
        $tipo = ''; $fim = $a
        if ($token.StartsWith('P', [StringComparison]::Ordinal) -or
            ($prox -ceq 'DA' -and $depois.StartsWith('NF', [StringComparison]::Ordinal))) {
            continue  # "portal da NF-e" (texto da consulta da chave) nao e "TOTAL DA"
        }
        if ($token.Contains('TOTALDA') -or $token.Contains('TALDANOTA')) {
            $tipo = 'nota'
        } elseif ($token.Length -ge 4 -and (Parece $token 'TOTAL')) {
            if ($prox -ceq 'DA' -or $prox -ceq 'OA' -or $prox.StartsWith('DAN', [StringComparison]::Ordinal) -or (Parece $prox 'NOTA' 1)) {
                $tipo = 'nota'; $fim = $a + 1
            } elseif ($prox -ceq 'DOS' -or $prox -ceq 'BOS' -or $prox -ceq 'OOS') {
                $tipo = 'produtos'; $fim = $a + 1
            }
        } elseif ($token.Length -ge 3 -and (Parece $token 'VALOR') -and (Parece $prox 'NOTA' 1)) {
            $tipo = 'nota'; $fim = $a + 1
        }
        if ($tipo) {
            $ini = $a
            if ($a -gt 0 -and $t[$a - 1].Length -ge 3 -and (Parece $t[$a - 1] 'VALOR')) {
                $anterior = $palavras[$linha[$a - 1]]; $atual = $palavras[$linha[$a]]
                $vao = [double]$atual[1] - ([double]$anterior[1] + [double]$anterior[3])
                if ($vao -le 2 * [Math]::Max([double]$anterior[4], [double]$atual[4])) { $ini = $a - 1 }  # "VALOR" colado no "TOTAL"
            }
            $indices = @(for ($k = $ini; $k -le $fim; $k++) { $linha[$k] })
            $achados.Add([pscustomobject]@{ Tipo = $tipo; Indices = $indices })
        }
    }
    , $achados
}

function ValoresNaFolha($palavras) {
    # Valores em dinheiro lidos pelo OCR: Valor, Caixa (x, y, largura, altura), Duvidoso.
    # Junta valores partidos em duas palavras ("777 58", "2.913 47", "315, 20"). Duvidoso: sem a
    # virgula ("487") ou com o comeco perdido ("031.27" de "1.031,27").
    $norm = @($palavras | ForEach-Object { CorrigirDigitos (Normalizar ([string]$_[0])) })
    $valores = New-Object 'System.Collections.Generic.List[object]'
    foreach ($linha in (LinhasVisuais $palavras)) {
        for ($k = 0; $k -lt $linha.Count; $k++) {
            $i = $linha[$k]
            $caixa = @([double]$palavras[$i][1], [double]$palavras[$i][2], [double]$palavras[$i][3], [double]$palavras[$i][4])
            $m = $ReDinheiroPalavra.Match($norm[$i])
            if ($m.Success) {
                $g = $m.Groups[1].Value
                $cortado = $g.Length -gt 4 -and $g.StartsWith('0') -and [char]::IsDigit($g[1])
                $valores.Add([pscustomobject]@{ Valor = (ValorDecimal $g); Caixa = $caixa; Duvidoso = $cortado })
                continue
            }
            $m = $ReMilharPalavra.Match($norm[$i])
            $j = if ($k + 1 -lt $linha.Count) { $linha[$k + 1] } else { -1 }
            if ($m.Success -and $j -ge 0 -and $ReCentavosPalavra.IsMatch($norm[$j])) {
                $a = $palavras[$i]; $b = $palavras[$j]
                $vao = [double]$b[1] - ([double]$a[1] + [double]$a[3])
                if ($vao -ge 0 -and $vao -le 1.5 * [Math]::Max([double]$a[4], [double]$b[4])) {
                    $y = [Math]::Min([double]$a[2], [double]$b[2])
                    $caixa = @([double]$a[1], $y, ([double]$b[1] + [double]$b[3] - [double]$a[1]),
                               ([Math]::Max([double]$a[2] + [double]$a[4], [double]$b[2] + [double]$b[4]) - $y))
                    $valores.Add([pscustomobject]@{ Valor = (ValorDecimal ($m.Groups[1].Value + ',' + $norm[$j])); Caixa = $caixa; Duvidoso = $false })
                    continue
                }
            }
            if ($ReSoDigitos.IsMatch($norm[$i])) {
                $valores.Add([pscustomobject]@{ Valor = (ValorDecimal $norm[$i]); Caixa = $caixa; Duvidoso = $true })
            }
        }
    }
    , $valores
}

function ValorPeloRotulo($palavras) {
    # Valor logo abaixo (ou a direita) de "VALOR TOTAL DA NOTA", pela posicao na folha.
    # Sem ele, o de "VALOR TOTAL DOS PRODUTOS". Devolve @(valor, origem) - origem em $PrioridadeValor.
    if (-not $palavras -or $palavras.Count -eq 0) { return @('', '') }
    $valores = @((ValoresNaFolha $palavras) | Where-Object { (DecimalDe $_.Valor) -gt 0 })
    $melhor = @{}  # tipo -> Duvidoso, Pontos, Valor
    foreach ($linha in (LinhasVisuais $palavras)) {
        foreach ($rotulo in (RotulosDeValor $palavras $linha)) {
            $x1 = [double]::MaxValue; $y1 = [double]::MaxValue; $x2 = [double]::MinValue; $y2 = [double]::MinValue; $altura = 0.0
            foreach ($i in $rotulo.Indices) {
                $p = $palavras[$i]
                $x1 = [Math]::Min($x1, [double]$p[1]); $y1 = [Math]::Min($y1, [double]$p[2])
                $x2 = [Math]::Max($x2, [double]$p[1] + [double]$p[3]); $y2 = [Math]::Max($y2, [double]$p[2] + [double]$p[4])
                $altura = [Math]::Max($altura, [double]$p[4])
            }
            $cx = ($x1 + $x2) / 2; $cy = ($y1 + $y2) / 2
            foreach ($v in $valores) {
                $x = $v.Caixa[0]; $y = $v.Caixa[1]; $largura = $v.Caixa[2]; $alt = $v.Caixa[3]
                $jx = $x + $largura / 2; $jy = $y + $alt / 2
                # o valor fica dentro da caixa do rotulo: nunca comeca antes dele
                $abaixo = ($y -ge $y1 + 0.5 * $altura) -and ($jy - $y2 -le 4 * $altura) -and
                          ($x -ge $x1 - $altura) -and ($x -le $x2 + 6 * $altura)
                $aoLado = ([Math]::Abs($jy - $cy) -le 0.5 * $altura) -and ($x -ge $x2) -and ($x - $x2 -le 15 * $altura)
                if ($abaixo -or $aoLado) {
                    $duvida = if ($v.Duvidoso) { 1 } else { 0 }
                    $pontos = [Math]::Abs($jy - $cy) + 0.3 * [Math]::Abs($jx - $cx)
                    $atual = $melhor[$rotulo.Tipo]
                    if (-not $atual -or $duvida -lt $atual.Duvida -or ($duvida -eq $atual.Duvida -and $pontos -lt $atual.Pontos)) {
                        $melhor[$rotulo.Tipo] = [pscustomobject]@{ Duvida = $duvida; Pontos = $pontos; Valor = $v.Valor; Duvidoso = $v.Duvidoso }
                    }
                }
            }
        }
    }
    $produtos = if ($melhor['produtos'] -and -not $melhor['produtos'].Duvidoso) { $melhor['produtos'].Valor } else { '' }
    if ($melhor['nota']) {
        $valor = $melhor['nota'].Valor
        if ($produtos -and (DecimalDe $valor) -eq (DecimalDe $produtos)) { return @($valor, 'rotulo') }  # confere com os produtos
        if ($melhor['nota'].Duvidoso -or ($produtos -and (DecimalDe $valor) -lt (DecimalDe $produtos) / 2)) {
            return @($valor, 'rotulo_duvidoso')
        }
        return @($valor, 'rotulo')
    }
    if ($produtos) { return @($produtos, 'produtos') }
    @('', '')
}

function MelhorValor($candidatos) {
    # O de maior prioridade (rotulo > duvidoso > produtos); empate: o primeiro
    $escolhido = @('', '')
    foreach ($c in $candidatos) {
        if ($PrioridadeValor[$c[1]] -gt $PrioridadeValor[$escolhido[1]]) { $escolhido = @($c[0], $c[1]) }
    }
    , $escolhido
}

function EncontrarSerie([string]$texto) {
    $m = $ReSerie.Match($texto)
    if ($m.Success) { [string][int]$m.Groups[1].Value } else { '' }
}

function EncontrarCnpjEmitente([string]$norm) {
    # Primeiro CNPJ valido antes do bloco do destinatario/tomador
    $fim = $ReFimEmitente.Match($norm)
    $trecho = if ($fim.Success) { $norm.Substring(0, $fim.Index) } else { $norm }
    foreach ($m in $ReCnpj.Matches($trecho)) {
        $bruto = -join (1..5 | ForEach-Object { $m.Groups[$_].Value })
        foreach ($cnpj in @($bruto, (TrocarDigitos $bruto))) {
            if (CnpjValido $cnpj) { return $cnpj }
        }
    }
    ''
}

function JuntarPedido([string]$trecho) {
    # '4500 0I2345' -> '4500012345' (so aceita se fechar exatamente um pedido)
    $partes = [regex]::Split((TrocarDigitos $trecho).Trim(), '[ .\-/]+')
    for ($i = 0; $i -lt $partes.Count; $i++) {
        if (-not $partes[$i].StartsWith($PrefixoPedido, [StringComparison]::Ordinal)) { continue }
        $digitos = ''
        for ($j = $i; $j -lt $partes.Count; $j++) {
            if ($partes[$j] -cnotmatch '^[0-9]+\z') { break }
            $digitos += $partes[$j]
            if ($digitos.Length -ge $DigitosPedido) { break }
        }
        if ($RePedidoInteiro.IsMatch($digitos)) { return $digitos }
    }
    ''
}

function EncontrarPedidos([string]$texto, [string]$ignorar = '') {
    $achados = New-Object 'System.Collections.Generic.List[object]'
    foreach ($m in $RePedido.Matches($texto)) {
        $achados.Add([pscustomobject]@{ Pos = $m.Index; Pedido = $m.Value })
    }
    foreach ($m in $RePedidoRotulo.Matches($texto)) {
        $pedido = JuntarPedido $m.Groups[1].Value
        if ($pedido) { $achados.Add([pscustomobject]@{ Pos = $m.Groups[1].Index; Pedido = $pedido }) }
    }
    $pedidos = New-Object 'System.Collections.Generic.List[string]'
    foreach ($a in ($achados | Sort-Object Pos, Pedido)) {
        # ignora trechos da chave de acesso
        if (-not $pedidos.Contains($a.Pedido) -and -not $ignorar.Contains($a.Pedido)) { $pedidos.Add($a.Pedido) }
    }
    , $pedidos
}

function ContarLetras([string]$s) { [regex]::Matches($s, '\p{L}').Count }

function LimparNome([string]$nome) {
    $nome = ($nome -creplace '\s+', ' ').Trim(' ,:;-_|/\''"*[](){}'.ToCharArray()).TrimStart([char]'.')
    $nome = ($nome -creplace '(?<!\w)\.+\z', '').Trim()  # mantem o ponto de "S.A." e "LTDA."
    if ($nome.Length -gt 100) { $nome = $nome.Substring(0, 100) }
    $nome
}

function EhMaiusculo([string]$s) { ($s -ceq $s.ToUpperInvariant()) -and ($s -cne $s.ToLowerInvariant()) }

function EhMinusculo([string]$s) { ($s -ceq $s.ToLowerInvariant()) -and ($s -cne $s.ToUpperInvariant()) }

function PalavraBoa([string]$token) {
    # Palavra com cara de nome: MAIUSCULA, Capitalizada ou conector (de, da, e...)
    foreach ($parte in [regex]::Split($token, "[.,'/()\-&]+")) {
        if (-not $parte -or $parte -cmatch '^[0-9]+\z') { continue }
        if ($parte -cnotmatch '^\p{L}+\z') { return $false }  # letras e numeros misturados: "st501"
        $capitalizada = $parte.Length -gt 1 -and [char]::IsUpper($parte[0]) -and (EhMinusculo $parte.Substring(1))
        $conector = (EhMinusculo $parte) -and $Conectores -contains $parte.ToUpperInvariant()
        if (-not ((EhMaiusculo $parte) -or $capitalizada -or $conector)) { return $false }
    }
    $true
}

function Distancia([string]$a, [string]$b) {
    # Quantas letras e preciso trocar, tirar ou por para ir de a ate b (Levenshtein)
    $anterior = [int[]](0..$b.Length)
    for ($i = 1; $i -le $a.Length; $i++) {
        $atual = New-Object 'int[]' ($b.Length + 1)
        $atual[0] = $i
        for ($j = 1; $j -le $b.Length; $j++) {
            $custo = if ($a[$i - 1] -ceq $b[$j - 1]) { 0 } else { 1 }
            $atual[$j] = [Math]::Min([Math]::Min($anterior[$j] + 1, $atual[$j - 1] + 1), $anterior[$j - 1] + $custo)
        }
        $anterior = $atual
    }
    $anterior[$b.Length]
}

function Parece([string]$palavra, [string]$alvo, [int]$maximo = 2) {
    ([Math]::Abs($palavra.Length - $alvo.Length) -le $maximo) -and ((Distancia $palavra $alvo) -le $maximo)
}

function PareceRecebemos([string]$token) { Parece ((Normalizar $token) -creplace '[^A-Z]', '') 'RECEBEMOS' }

function NomePlausivel([string]$nome) {
    # Tira pedacos ilegiveis e descarta o nome se ele for "lixo" do OCR
    $todos = @($nome -split '\s+' | Where-Object { $_ })
    while ($todos.Count -gt 0 -and ($todos[0].ToUpperInvariant() -ceq 'DE' -or (PareceRecebemos $todos[0]))) {
        $todos = @($todos | Select-Object -Skip 1)  # sobra do canhoto: "RECEBEMOS DE ..."
    }
    while ($todos.Count -gt 0 -and ($Conectores -contains $todos[-1] -or -not (PalavraBoa $todos[-1]))) {
        $todos = @($todos | Select-Object -First ($todos.Count - 1))  # nome nao termina em "da" nem em lixo
    }
    $nome = $todos -join ' '
    $tokens = @($todos | Where-Object { $ReTokenLegivel.IsMatch($_) })
    $boas = @($tokens | Where-Object { PalavraBoa $_ })
    $principais = @($boas | Where-Object {
        (ContarLetras $_) -ge 3 -and
        ($SufixosEmpresa + $Conectores) -notcontains ($_ -creplace '\W', '').ToUpperInvariant() })
    $comNumero = @($tokens | Where-Object { $_ -cmatch '\d' }).Count
    $norm = Normalizar $nome
    if ($principais.Count -eq 0 -or $boas.Count -lt 0.7 * $todos.Count -or $comNumero -gt 1 -or  # lixo / produto
        $ReEndereco.IsMatch($norm) -or $ReCidadeUF.IsMatch($norm)) { return '' }  # endereco / cidade - UF
    LimparNome ($tokens -join ' ')
}

function Sufixos([string]$linha, [string]$linhaNorm) {
    # LTDA, S.A., ME... (ignora "sa", "me" minusculos, que costumam ser lixo do OCR)
    $lista = New-Object 'System.Collections.Generic.List[object]'
    foreach ($m in $ReSufixo.Matches($linhaNorm)) {
        if (-not (EhMinusculo $linha.Substring($m.Index, $m.Length))) { $lista.Add($m) }
    }
    , $lista
}

function NomeDaLinha([string]$linha, [string]$linhaNorm) {
    # Corta rotulos do DANFE que o OCR juntou na mesma linha do nome
    $corte = $ReRotulos.Match($linhaNorm)
    $fim = if ($corte.Success) { $corte.Index } else { $linha.Length }
    $sufixos = Sufixos $linha.Substring(0, $fim) $linhaNorm.Substring(0, $fim)
    if ($sufixos.Count -gt 0) { $fim = $sufixos[$sufixos.Count - 1].Index + $sufixos[$sufixos.Count - 1].Length }
    $nome = NomePlausivel (LimparNome $linha.Substring(0, $fim))
    if ((ContarLetras $nome) -ge 4) { $nome } else { '' }
}

function NomeDoCanhoto([string]$texto, [string]$norm) {
    # "RECEBEMOS DE <FORNECEDOR> OS PRODUTOS..." (aceita erros do OCR nessas palavras)
    $tokens = @($RePalavra.Matches($norm))
    for ($i = 0; $i -lt $tokens.Count - 2; $i++) {
        if ($tokens[$i + 1].Value -cne 'DE' -or -not (PareceRecebemos $tokens[$i].Value)) { continue }
        for ($j = $i + 3; $j -lt [Math]::Min($i + 30, $tokens.Count); $j++) {
            $palavra = $tokens[$j].Value -creplace '[^A-Z]', ''
            $ehFim = $false
            if ($palavra.Length -ge 5) {
                foreach ($fim in $FimDoCanhoto) { if (Parece $palavra $fim) { $ehFim = $true; break } }
            }
            if ($ehFim) {
                $k = $j - 1
                if ('OS', 'O', 'AS', 'A' -ccontains $tokens[$k].Value) { $k-- }
                if ($k -ge $i + 2) {
                    $ini = $tokens[$i + 2].Index
                    $nome = NomePlausivel (LimparNome $texto.Substring($ini, $tokens[$k].Index + $tokens[$k].Length - $ini))
                    if ((ContarLetras $nome) -ge 4) { return $nome }
                }
                break
            }
        }
    }
    ''
}

function EncontrarFornecedor([string]$texto, [string]$norm) {
    # 1) Canhoto: "RECEBEMOS DE <FORNECEDOR> OS PRODUTOS..."
    $nome = NomeDoCanhoto $texto $norm
    if ($nome) { return $nome }

    $linhas = $texto.Split("`n")
    $linhasNorm = $norm.Split("`n")
    $inicio = New-Object 'System.Collections.Generic.List[int]'
    $inicio.Add(0)
    foreach ($l in $linhas) { $inicio.Add($inicio[$inicio.Count - 1] + $l.Length + 1) }
    $linhaDe = { param($pos) $i = 0; while ($inicio[$i + 1] -le $pos) { $i++ }; $i }

    # 2) Bloco "IDENTIFICACAO DO EMITENTE" -> proxima linha com um nome
    $m = $ReEmitente.Match($norm)
    if ($m.Success) {
        $depois = $m.Index + $m.Length
        $i = & $linhaDe $depois
        $tamanho = $inicio[$i + 1] - 1 - $depois
        $nome = NomeDaLinha $texto.Substring($depois, $tamanho) $norm.Substring($depois, $tamanho)
        if ($nome) { return $nome }
        for ($j = $i + 1; $j -lt [Math]::Min($i + 7, $linhas.Count); $j++) {
            if ($ReFimEmitente.IsMatch($linhasNorm[$j])) { break }
            $nome = NomeDaLinha $linhas[$j] $linhasNorm[$j]
            if ($nome) { return $nome }
        }
    }

    # 3) NFS-e: "PRESTADOR DE SERVICOS ... Razao Social: <nome>"
    $m = $RePrestador.Match($norm)
    if ($m.Success) {
        $depois = $m.Index + $m.Length
        $r = $ReRazaoSocial.Match($norm, $depois, [Math]::Min(400, $norm.Length - $depois))
        if ($r.Success) {
            $fimR = $r.Index + $r.Length
            $j = & $linhaDe $fimR
            $col = $fimR - $inicio[$j]
            $nome = NomeDaLinha $linhas[$j].Substring($col) $linhasNorm[$j].Substring($col)
            if ($nome) { return $nome }
        }
    }

    # 4) Primeira linha com LTDA / S.A. / EIRELI... antes do destinatario
    $fim = $ReFimEmitente.Match($norm)
    $ultima = if ($fim.Success) { & $linhaDe $fim.Index } else { $linhas.Count }
    for ($j = 0; $j -lt $ultima; $j++) {
        if ($linhasNorm[$j].Contains('RECEBEMOS') -or (Sufixos $linhas[$j] $linhasNorm[$j]).Count -eq 0) { continue }
        $nome = NomeDaLinha $linhas[$j] $linhasNorm[$j]
        if ($nome) { return $nome }
    }
    ''
}

function Etiqueta([string]$texto, [string]$num) {
    # Etiqueta de recebimento colada na folha: "NF 12345" e, na linha de baixo, o fornecedor.
    # Devolve @(numero, fornecedor, continuacao).
    $m = $ReEtiquetaNF.Match($num)
    if (-not $m.Success -or -not (SoNumero $m.Groups[1].Value)) { return @('', '', $false) }
    $depois = $m.Index + $m.Length
    $fim = $num.IndexOf([char]10, $depois)
    if ($fim -lt 0) { $fim = $num.Length }
    $continuacao = $num.Substring($depois, $fim - $depois).Contains('CONTINUA')
    $nome = ''
    if ($fim -lt $texto.Length) {
        $fimProx = $texto.IndexOf([char]10, $fim + 1)
        if ($fimProx -lt 0) { $fimProx = $texto.Length }
        $candidato = NomePlausivel (LimparNome $texto.Substring($fim + 1, $fimProx - $fim - 1))
        $palavras = @($candidato -split '\s+' | Where-Object { $_ }).Count
        if ((ContarLetras $candidato) -ge 4 -and ((TemSufixo $candidato) -or $palavras -ge 3)) { $nome = $candidato }
    }
    @((SoNumero $m.Groups[1].Value), $nome, $continuacao)
}

function ExtrairDados([string]$texto, $cadastro = $null, $valorGeometria = $null) {
    # Extrai fornecedor, numero da NF, pedidos e valor total do texto de uma pagina
    $texto = $texto.Replace("`r`n", "`n").Replace("`r", "`n")
    $norm = Normalizar $texto
    $num = CorrigirDigitos $norm
    $d = NovoDados
    $parcial = ''
    $etiqueta = Etiqueta $texto $num
    $d.Continuacao = $etiqueta[2]

    $d.Chave = EncontrarChave $num
    if (-not $d.Chave) { $d.Chave = EncontrarChave $norm }

    if ($d.Chave) {
        $d.Cnpj = $d.Chave.Substring(6, 14)
        $d.Serie = [string][int]$d.Chave.Substring(22, 3)
        $d.NumeroNF = [string][long]$d.Chave.Substring(25, 9)
        $d.OrigemNF = 'chave'
        if ($etiqueta[0] -and $etiqueta[0] -cne $d.NumeroNF) { $d.OrigemNF = 'divergente' }
    } else {
        $numero = EncontrarNumeroNF $num
        $d.NumeroNF = $numero[0]
        $d.OrigemNF = $numero[1]
        $d.Serie = EncontrarSerie $num
        $d.Cnpj = EncontrarCnpjEmitente $norm
        # Chave com algum digito ilegivel: o CNPJ dela e confiavel; o numero precisa de conferencia
        $parcial = EncontrarChave $num 'ChaveEstruturaOk'
        if ($parcial) {
            $d.Cnpj = $parcial.Substring(6, 14)
            if (-not $d.Serie) { $d.Serie = [string][int]$parcial.Substring(22, 3) }
            $numeroChave = [string][long]$parcial.Substring(25, 9)
            if (-not $d.NumeroNF) { $d.NumeroNF = $numeroChave; $d.OrigemNF = 'chave_parcial' }
            elseif ($d.NumeroNF -cne $numeroChave) { $d.OrigemNF = 'divergente' }
        }
        if ($etiqueta[0]) { $d.NumeroNF = $etiqueta[0]; $d.OrigemNF = 'etiqueta' }  # letra grande: o OCR le bem
    }

    $ignorar = if ($d.Chave) { $d.Chave } else { $parcial }
    $d.Pedidos = EncontrarPedidos $num $ignorar
    # Pela posicao (rotulo e valor na mesma coluna) > pelo texto > pela posicao, com menos certeza
    if (-not $valorGeometria) { $valorGeometria = @('', '') }
    $valor = if ($valorGeometria[1] -eq 'rotulo') { $valorGeometria } else { MelhorValor @((EncontrarValorTotal $num), $valorGeometria) }
    $d.ValorTotal = $valor[0]; $d.OrigemValor = $valor[1]

    if ($cadastro -and $d.Cnpj -and $cadastro.ContainsKey($d.Cnpj)) {
        $d.Fornecedor = $cadastro[$d.Cnpj]
    } elseif ($etiqueta[1]) {
        $d.Fornecedor = $etiqueta[1]
    } else {
        $d.Fornecedor = EncontrarFornecedor $texto $norm
    }
    $d
}

# ----------------------------------------------------------------------------
# OCR do Windows (Windows.Media.Ocr) e leitura de PDF (Windows.Data.Pdf)
# ----------------------------------------------------------------------------

function IniciarOcr {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
    $null = [Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
    $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType = WindowsRuntime]

    $metodos = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 }
    $script:AsTaskOperacao = $metodos | Where-Object { $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } |
        Select-Object -First 1
    $script:AsTaskAcao = $metodos | Where-Object { $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction' } |
        Select-Object -First 1

    $portugues = [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages |
        Where-Object { $_.LanguageTag -like 'pt*' } | Select-Object -First 1
    if ($portugues) {
        $script:MotorOcr = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($portugues)
    } else {
        $script:MotorOcr = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
        Write-Host (U 'AVISO: o OCR em portugu\u00eas n\u00e3o est\u00e1 dispon\u00edvel neste Windows; usando o idioma do sistema.')
    }
    if (-not $script:MotorOcr) { throw (U 'O OCR do Windows n\u00e3o est\u00e1 dispon\u00edvel neste computador.') }
}

function Aguardar($operacao, [type]$tipo) {
    $tarefa = $script:AsTaskOperacao.MakeGenericMethod($tipo).Invoke($null, @($operacao))
    [void]$tarefa.Wait(-1)
    $tarefa.Result
}

function AguardarAcao($acao) {
    [void]$script:AsTaskAcao.Invoke($null, @($acao)).Wait(-1)
}

function AbrirPaginas([string]$caminho) {
    # Devolve uma lista de imagens (uma por pagina) prontas para o OCR
    $arquivo = Aguardar ([Windows.Storage.StorageFile]::GetFileFromPathAsync($caminho)) ([Windows.Storage.StorageFile])
    $paginas = New-Object 'System.Collections.Generic.List[object]'
    if ([IO.Path]::GetExtension($caminho).ToLower() -eq '.pdf') {
        $pdf = Aguardar ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($arquivo)) ([Windows.Data.Pdf.PdfDocument])
        for ($i = 0; $i -lt $pdf.PageCount; $i++) {
            $pagina = $pdf.GetPage([uint32]$i)
            $opcoes = [Windows.Data.Pdf.PdfPageRenderOptions]::new()
            $opcoes.DestinationWidth = [uint32][Math]::Round($pagina.Size.Width * $DpiPdf / 96)
            $fluxo = [Windows.Storage.Streams.InMemoryRandomAccessStream]::new()
            AguardarAcao ($pagina.RenderToStreamAsync($fluxo, $opcoes))
            $fluxo.Seek(0)
            $paginas.Add((Aguardar ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($fluxo)) ([Windows.Graphics.Imaging.BitmapDecoder])))
        }
    } else {
        $fluxo = Aguardar ($arquivo.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        $decoder = Aguardar ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($fluxo)) ([Windows.Graphics.Imaging.BitmapDecoder])
        if ($decoder.FrameCount -le 1) {
            $paginas.Add($decoder)
        } else {  # TIFF com varias paginas
            for ($i = 0; $i -lt $decoder.FrameCount; $i++) {
                $paginas.Add((Aguardar ($decoder.GetFrameAsync([uint32]$i)) ([Windows.Graphics.Imaging.BitmapFrame])))
            }
        }
    }
    , $paginas
}

function LerTexto($imagem, [int]$rotacao, [double]$escala = 1.0, $recorte = $null) {
    # Le a folha (ou so um pedaco dela: $recorte = x, y, largura, altura em fracoes da folha ja girada).
    # Devolve o texto e as palavras com a posicao na folha: @(texto, x, y, largura, altura).
    $t = [Windows.Graphics.Imaging.BitmapTransform]::new()
    $t.Rotation = [Windows.Graphics.Imaging.BitmapRotation]@{
        0 = 'None'; 90 = 'Clockwise90Degrees'; 180 = 'Clockwise180Degrees'; 270 = 'Clockwise270Degrees' }[$rotacao]
    $deLado = $rotacao -eq 90 -or $rotacao -eq 270
    $w0 = [double]$(if ($deLado) { $imagem.PixelHeight } else { $imagem.PixelWidth })
    $h0 = [double]$(if ($deLado) { $imagem.PixelWidth } else { $imagem.PixelHeight })
    $fx = 0.0; $fy = 0.0; $fw = 1.0; $fh = 1.0
    if ($recorte) { $fx = $recorte[0]; $fy = $recorte[1]; $fw = $recorte[2]; $fh = $recorte[3] }

    # Amplia (digitalizacao em baixa resolucao / pedacos) sem passar do tamanho maximo do OCR
    $maior = [Math]::Max($w0, $h0)
    $fator = if ($maior -lt 2400) { 3000.0 / $maior } else { 1.0 }
    $fator = [Math]::Min($fator * $escala, [double][Windows.Media.Ocr.OcrEngine]::MaxImageDimension / [Math]::Max($w0 * $fw, $h0 * $fh))
    $largura = $w0; $altura = $h0
    if ($fator -ne 1.0) {
        $t.ScaledWidth = [uint32][Math]::Floor($imagem.PixelWidth * $fator)
        $t.ScaledHeight = [uint32][Math]::Floor($imagem.PixelHeight * $fator)
        $t.InterpolationMode = [Windows.Graphics.Imaging.BitmapInterpolationMode]::Fant
        $largura = [Math]::Floor($w0 * $fator); $altura = [Math]::Floor($h0 * $fator)
    }
    $bx = 0.0; $by = 0.0
    if ($recorte) {
        $b = New-Object Windows.Graphics.Imaging.BitmapBounds
        $b.X = [uint32][Math]::Floor($fx * $largura)
        $b.Y = [uint32][Math]::Floor($fy * $altura)
        $b.Width = [uint32][Math]::Min([Math]::Floor($fw * $largura), $largura - $b.X)
        $b.Height = [uint32][Math]::Min([Math]::Floor($fh * $altura), $altura - $b.Y)
        $t.Bounds = $b
        $bx = [double]$b.X; $by = [double]$b.Y
    }

    $bitmap = Aguardar ($imagem.GetSoftwareBitmapAsync(
            [Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8,
            [Windows.Graphics.Imaging.BitmapAlphaMode]::Premultiplied, $t,
            [Windows.Graphics.Imaging.ExifOrientationMode]::IgnoreExifOrientation,
            [Windows.Graphics.Imaging.ColorManagementMode]::DoNotColorManage)) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $resultado = Aguardar ($script:MotorOcr.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

    $palavras = New-Object 'System.Collections.Generic.List[object]'
    $numLinha = 0
    foreach ($linha in $resultado.Lines) {
        $numLinha++
        foreach ($w in $linha.Words) {
            $r = $w.BoundingRect
            $palavras.Add(@([string]$w.Text, (($r.X + $bx) / $fator), (($r.Y + $by) / $fator),
                            ($r.Width / $fator), ($r.Height / $fator), $numLinha))
        }
    }
    [pscustomobject]@{
        Texto = ($resultado.Lines | ForEach-Object { $_.Text }) -join "`n"
        Palavras = $palavras; Largura = $w0; Altura = $h0
    }
}

function Legibilidade([string]$texto) { $RePalavrasDanfe.Matches((Normalizar $texto)).Count }

function MontarDados($leituras, $cadastro) {
    $textos = New-Object 'System.Collections.Generic.List[string]'
    foreach ($l in $leituras) { $textos.Add($l.Texto) }
    foreach ($l in $leituras) { if ($l.Palavras.Count -gt 0) { $textos.Add((TextoVisual $l.Palavras)) } }
    $candidatos = New-Object 'System.Collections.Generic.List[object]'
    for ($k = $leituras.Count - 1; $k -ge 0; $k--) { $candidatos.Add((ValorPeloRotulo $leituras[$k].Palavras)) }
    $valor = MelhorValor $candidatos
    $texto = $textos -join "`n"
    [pscustomobject]@{ Dados = (ExtrairDados $texto $cadastro $valor); Texto = $texto }
}

function LerPagina($imagem, $cadastro) {
    # 1) Descobre a posicao da folha (em pe, de cabeca para baixo ou de lado) pelo texto mais legivel.
    #    So o texto dessa posicao e usado: o das outras posicoes e lixo e atrapalha.
    $melhor = $null
    $pontosMelhor = -1
    foreach ($rotacao in 0, 180, 90, 270) {
        $leitura = LerTexto $imagem $rotacao
        $pontos = Legibilidade $leitura.Texto
        if ($pontos -gt $pontosMelhor) { $melhor = $leitura; $pontosMelhor = $pontos; $rotacaoMelhor = $rotacao }
        if ($pontos -ge 8) { break }
    }
    $leituras = New-Object 'System.Collections.Generic.List[object]'
    $leituras.Add($melhor)
    $montado = MontarDados $leituras $cadastro

    # 2) Faltou algo: le a folha em 6 pedacos ampliados (a letra miuda fica legivel para o OCR).
    #    Folha em branco (verso) nao precisa.
    if (-not (Completo $montado.Dados) -and $melhor.Palavras.Count -ge 5) {
        $palavras = New-Object 'System.Collections.Generic.List[object]'
        $k = 0
        foreach ($pedaco in $Pedacos) {
            $k++
            $leitura = LerTexto $imagem $rotacaoMelhor 2.0 $pedaco.Recorte
            $n = $pedaco.Nucleo
            foreach ($p in $leitura.Palavras) {
                $cx = ([double]$p[1] + [double]$p[3] / 2) / $leitura.Largura
                $cy = ([double]$p[2] + [double]$p[4] / 2) / $leitura.Altura
                if ($cx -ge $n[0] -and $cx -lt $n[2] -and $cy -ge $n[1] -and $cy -lt $n[3]) {
                    $palavras.Add(@($p[0], $p[1], $p[2], $p[3], $p[4], ($k * 100000 + $p[5])))  # linha unica por pedaco
                }
            }
        }
        # So as palavras de cada pedaco (sem as cortadas na borda); o texto sai montado pela posicao
        $leituras.Add([pscustomobject]@{ Texto = ''; Palavras = $palavras })
        $montado = MontarDados $leituras $cadastro
    }
    [pscustomobject]@{ Dados = $montado.Dados; Texto = $montado.Texto; Leituras = $leituras }
}

function NovoRegistro([string]$arquivo, $paginas, $dados) {
    $lista = New-Object 'System.Collections.Generic.List[int]'
    foreach ($p in $paginas) { $lista.Add($p) }
    [pscustomobject]@{ Arquivo = $arquivo; Paginas = $lista; Dados = $dados
                       Avisos = (New-Object 'System.Collections.Generic.List[string]') }
}

function ProcessarArquivo([string]$caminho, [string]$nome, $cadastro, [string]$pastaTextos) {
    $registros = New-Object 'System.Collections.Generic.List[object]'
    $n = 0
    foreach ($imagem in (AbrirPaginas $caminho)) {
        $n++
        $lido = LerPagina $imagem $cadastro
        $dados = $lido.Dados
        if ($pastaTextos) {
            $base = $nome -creplace '[\\/:]', '_'
            [IO.File]::WriteAllText((Join-Path $pastaTextos "$($base)_pag$n.txt"), $lido.Texto, [Text.UTF8Encoding]::new($false))
            $json = ConvertTo-Json -Compress -Depth 5 -InputObject @(
                foreach ($l in $lido.Leituras) { @{ palavras = $l.Palavras.ToArray() } })
            [IO.File]::WriteAllText((Join-Path $pastaTextos "$($base)_pag$n.json"), $json, [Text.UTF8Encoding]::new($false))
        }

        if (Vazio $dados) {
            if (($lido.Texto -creplace '\s', '').Length -ge 30) { $registros.Add((NovoRegistro $nome @($n) $dados)) }
            continue  # folha em branco (verso) e ignorada
        }

        # A mesma NF em varias paginas vira uma linha so
        $juntou = $false
        foreach ($reg in $registros) {
            $mesmoEmitente = (-not ($reg.Dados.Cnpj -and $dados.Cnpj)) -or $reg.Dados.Cnpj -ceq $dados.Cnpj
            if ($dados.NumeroNF -and $reg.Dados.NumeroNF -ceq $dados.NumeroNF -and $mesmoEmitente) {
                $reg.Paginas.Add($n)
                CompletarCom $reg.Dados $dados
                $juntou = $true
                break
            }
        }
        if (-not $juntou) { $registros.Add((NovoRegistro $nome @($n) $dados)) }
    }
    , $registros
}

# ----------------------------------------------------------------------------
# Cadastro de fornecedores e planilha
# ----------------------------------------------------------------------------

function CarregarCadastro([string]$caminho) {
    # Le o CSV opcional 'CNPJ;Fornecedor' para padronizar os nomes
    $cadastro = @{}
    if (-not $caminho -or -not (Test-Path -LiteralPath $caminho -PathType Leaf)) { return $cadastro }
    $bytes = [IO.File]::ReadAllBytes($caminho)
    try {
        $conteudo = [Text.UTF8Encoding]::new($false, $true).GetString($bytes)
    } catch {
        $conteudo = [Text.Encoding]::GetEncoding(28591).GetString($bytes)  # CSV salvo pelo Excel (ANSI)
    }
    $linhas = @($conteudo.TrimStart([char]0xFEFF) -split "`r?`n" | Where-Object { $_.Trim() })
    if ($linhas.Count -eq 0) { return $cadastro }
    $separador = if ($linhas[0].Contains(';')) { ';' } else { ',' }
    foreach ($item in ($linhas | ConvertFrom-Csv -Delimiter $separador -Header 'Cnpj', 'Nome')) {
        if (-not $item.Cnpj -or -not $item.Nome) { continue }
        $cnpj = $item.Cnpj.ToUpperInvariant() -creplace '[^0-9A-Z]', ''
        if ($cnpj.Length -eq 14 -and $item.Nome.Trim()) { $cadastro[$cnpj] = $item.Nome.Trim() }
    }
    $cadastro
}

function JuntarContinuacoes($registros) {
    # Folha com "(continuacao)" na etiqueta, escaneada em outro arquivo: junta com a NF principal
    $principais = @($registros | Where-Object { -not $_.Dados.Continuacao })
    $juntados = New-Object 'System.Collections.Generic.HashSet[object]'
    foreach ($r in $registros) {
        if (-not ($r.Dados.Continuacao -and $r.Dados.NumeroNF)) { continue }
        foreach ($alvo in $principais) {
            $mesmoEmitente = (-not ($alvo.Dados.Cnpj -and $r.Dados.Cnpj)) -or $alvo.Dados.Cnpj -ceq $r.Dados.Cnpj
            if ($alvo.Dados.NumeroNF -ceq $r.Dados.NumeroNF -and $mesmoEmitente) {
                if ($r.Arquivo -cne $alvo.Arquivo) { $alvo.Arquivo += ' + ' + $r.Arquivo }
                foreach ($pagina in $r.Paginas) { $alvo.Paginas.Add($pagina) }
                CompletarCom $alvo.Dados $r.Dados
                [void]$juntados.Add($r)
                break
            }
        }
    }
    $saida = New-Object 'System.Collections.Generic.List[object]'
    foreach ($r in $registros) { if (-not $juntados.Contains($r)) { $saida.Add($r) } }
    , $saida
}

function TemSufixo([string]$nome) { $ReSufixoFinal.IsMatch((Normalizar $nome)) }

function Semelhanca([string]$a, [string]$b, [switch]$PeloFim) {
    # 0 a 1. Um nome cortado pelo OCR tambem e comparado com o comeco (ou o fim) do outro.
    $a = Normalizar $a; $b = Normalizar $b
    if (-not $a -or -not $b) { return 0.0 }
    $s = 1 - (Distancia $a $b) / [Math]::Max($a.Length, $b.Length)
    if ($a.Length -ge 12 -and $a.Length -lt $b.Length) {
        $s = [Math]::Max([double]$s, 1 - (Distancia $a $b.Substring(0, $a.Length)) / $a.Length)
        if ($PeloFim) { $s = [Math]::Max([double]$s, 1 - (Distancia $a $b.Substring($b.Length - $a.Length)) / $a.Length) }
    }
    $s
}

function ContarFornecedores($registros) {
    $contagem = New-Object 'System.Collections.Generic.Dictionary[string,int]'
    $primeira = New-Object 'System.Collections.Generic.Dictionary[string,int]'
    for ($i = 0; $i -lt $registros.Count; $i++) {
        $nome = $registros[$i].Dados.Fornecedor
        if (-not $nome) { continue }
        if ($contagem.ContainsKey($nome)) { $contagem[$nome]++ } else { $contagem[$nome] = 1; $primeira[$nome] = $i }
    }
    [pscustomobject]@{ Contagem = $contagem; Primeira = $primeira }
}

function MelhorQue([string]$a, [string]$b, $info) {
    # Ordem de preferencia: tem LTDA/S.A., aparece em mais NFs, e mais comprido, apareceu antes
    foreach ($par in @(@([int](TemSufixo $a), [int](TemSufixo $b)), @($info.Contagem[$a], $info.Contagem[$b]),
                      @($a.Length, $b.Length), @(-$info.Primeira[$a], -$info.Primeira[$b]))) {
        if ($par[0] -ne $par[1]) { return $par[0] -gt $par[1] }
    }
    $false
}

function PadronizarFornecedores($registros) {
    # O mesmo fornecedor lido de jeitos diferentes em NFs diferentes passa a ter um nome so

    # 1) Nome cortado ou mal lido (sem LTDA/S.A.) parecido com um nome completo de outra NF
    $info = ContarFornecedores $registros
    $completos = New-Object 'System.Collections.Generic.List[string]'
    foreach ($nome in @($info.Contagem.Keys)) {
        if (-not (TemSufixo $nome)) { continue }
        $pos = 0
        while ($pos -lt $completos.Count -and (MelhorQue $completos[$pos] $nome $info)) { $pos++ }
        $completos.Insert($pos, $nome)
    }
    foreach ($r in $registros) {
        $nome = $r.Dados.Fornecedor
        if ($nome -and -not (TemSufixo $nome)) {
            foreach ($completo in $completos) {
                if ((Semelhanca $nome $completo) -ge 0.8) { $r.Dados.Fornecedor = $completo; break }
            }
        }
    }

    # 2) Mesmo CNPJ = mesmo fornecedor: usa a melhor leitura do grupo
    $info = ContarFornecedores $registros
    $grupos = [ordered]@{}
    foreach ($r in $registros) {
        if (-not $r.Dados.Cnpj) { continue }
        if (-not $grupos.Contains($r.Dados.Cnpj)) { $grupos[$r.Dados.Cnpj] = New-Object 'System.Collections.Generic.List[object]' }
        $grupos[$r.Dados.Cnpj].Add($r)
    }
    foreach ($grupo in $grupos.Values) {
        $melhor = ''
        foreach ($r in $grupo) {
            $nome = $r.Dados.Fornecedor
            if ($nome -and (-not $melhor -or (MelhorQue $nome $melhor $info))) { $melhor = $nome }
        }
        if (-not $melhor) { continue }
        foreach ($r in $grupo) {
            $nome = $r.Dados.Fornecedor
            if (-not $nome -or -not (TemSufixo $nome) -or (Semelhanca $nome $melhor -PeloFim) -ge 0.8) {
                $r.Dados.Fornecedor = $melhor
            }
        }
    }
}

function MarcarAvisos($registros) {
    $chave = { param($d) $emitente = if ($d.Cnpj) { $d.Cnpj } else { $d.Fornecedor }; "$emitente|$($d.NumeroNF)" }
    $contagem = @{}
    foreach ($r in $registros) {
        if ($r.Dados.NumeroNF) { $k = & $chave $r.Dados; $contagem[$k] = 1 + [int]$contagem[$k] }
    }
    foreach ($r in $registros) {
        $d = $r.Dados
        if ($r.Avisos.Count -gt 0) { continue }  # erro ao abrir o arquivo
        if (Vazio $d) { $r.Avisos.Add((U 'nada identificado na p\u00e1gina')); continue }
        if (-not $d.Fornecedor) { $r.Avisos.Add((U 'fornecedor n\u00e3o encontrado')) }
        if (-not $d.NumeroNF) { $r.Avisos.Add((U 'n\u00ba da NF n\u00e3o encontrado')) }
        elseif ($d.OrigemNF -eq 'texto') { $r.Avisos.Add((U 'n\u00ba da NF lido fora do padr\u00e3o DANFE')) }
        elseif ($d.OrigemNF -eq 'chave_parcial') { $r.Avisos.Add((U 'n\u00ba da NF lido da chave de acesso com d\u00edgito ileg\u00edvel')) }
        elseif ($d.OrigemNF -eq 'divergente') { $r.Avisos.Add((U 'n\u00ba impresso diferente do n\u00ba da chave de acesso')) }
        elseif ($contagem[(& $chave $d)] -gt 1) { $r.Avisos.Add('NF repetida em outro arquivo') }
        if (-not $d.ValorTotal) { $r.Avisos.Add((U 'valor total n\u00e3o encontrado')) }
        elseif ($d.OrigemValor -eq 'rotulo_duvidoso') { $r.Avisos.Add('valor total com leitura duvidosa') }
        elseif ($d.OrigemValor -eq 'produtos') { $r.Avisos.Add((U 'valor total da nota n\u00e3o lido: usado o total dos produtos')) }
        if ($d.Pedidos.Count -eq 0) { $r.Avisos.Add((U 'pedido n\u00e3o encontrado')) }
        elseif ($d.Pedidos.Count -gt 1) { $r.Avisos.Add('mais de um pedido') }
    }
}

function EscaparXml([string]$s) {
    [System.Security.SecurityElement]::Escape(($s -creplace '[\x00-\x08\x0B\x0C\x0E-\x1F]', ''))
}

function GerarPlanilha($registros, [string]$caminho) {
    # Monta o .xlsx direto (sem precisar do Excel nem de bibliotecas)
    $colunas = @(
        @('Fornecedor', 45), @((U 'N\u00ba NF'), 12), @('Pedido', 14), @('Valor Total', 14), @((U 'S\u00e9rie'), 7),
        @('CNPJ Fornecedor', 20), @('Chave de Acesso', 48), @('Arquivo', 30), @((U 'P\u00e1gina'), 8),
        @('Status', 55))
    $letras = 'ABCDEFGHIJ'
    # estilos: 0 normal | 1 cabecalho | 2 numero | 3 amarelo | 4 numero amarelo | 5 valor | 6 valor amarelo
    $celTexto = { param($ref, $valor, $estilo)
        if ("$valor" -eq '') { "<c r=`"$ref`" s=`"$estilo`"/>" }
        else { "<c r=`"$ref`" s=`"$estilo`" t=`"inlineStr`"><is><t xml:space=`"preserve`">$(EscaparXml $valor)</t></is></c>" } }
    $celNumero = { param($ref, $valor, $estilo) "<c r=`"$ref`" s=`"$estilo`"><v>$valor</v></c>" }

    $linhas = New-Object System.Text.StringBuilder
    [void]$linhas.Append('<row r="1">')
    for ($c = 0; $c -lt $colunas.Count; $c++) { [void]$linhas.Append((& $celTexto "$($letras[$c])1" $colunas[$c][0] 1)) }
    [void]$linhas.Append('</row>')

    $linha = 1
    foreach ($r in $registros) {
        $linha++
        $d = $r.Dados
        $amarelo = $r.Avisos.Count -gt 0
        $sTexto = if ($amarelo) { 3 } else { 0 }
        $sNumero = if ($amarelo) { 4 } else { 2 }
        $sValor = if ($amarelo) { 6 } else { 5 }
        $status = if ($amarelo) { 'CONFERIR: ' + ($r.Avisos -join '; ') } else { 'OK' }
        [void]$linhas.Append("<row r=`"$linha`">")
        [void]$linhas.Append((& $celTexto "A$linha" $d.Fornecedor $sTexto))
        if ($d.NumeroNF) { [void]$linhas.Append((& $celNumero "B$linha" $d.NumeroNF $sNumero)) }
        else { [void]$linhas.Append((& $celTexto "B$linha" '' $sTexto)) }
        if ($d.Pedidos.Count -eq 1) { [void]$linhas.Append((& $celNumero "C$linha" $d.Pedidos[0] $sNumero)) }
        else { [void]$linhas.Append((& $celTexto "C$linha" ($d.Pedidos -join ' / ') $sTexto)) }
        if ($d.ValorTotal) { [void]$linhas.Append((& $celNumero "D$linha" $d.ValorTotal $sValor)) }
        else { [void]$linhas.Append((& $celTexto "D$linha" '' $sTexto)) }
        [void]$linhas.Append((& $celTexto "E$linha" $d.Serie $sTexto))
        [void]$linhas.Append((& $celTexto "F$linha" (FormatarCnpj $d.Cnpj) $sTexto))
        [void]$linhas.Append((& $celTexto "G$linha" $d.Chave $sTexto))
        [void]$linhas.Append((& $celTexto "H$linha" $r.Arquivo $sTexto))
        [void]$linhas.Append((& $celTexto "I$linha" ($r.Paginas -join ', ') $sTexto))
        [void]$linhas.Append((& $celTexto "J$linha" $status $sTexto))
        [void]$linhas.Append('</row>')
    }

    $larguras = for ($c = 0; $c -lt $colunas.Count; $c++) {
        "<col min=`"$($c + 1)`" max=`"$($c + 1)`" width=`"$($colunas[$c][1])`" customWidth=`"1`"/>" }
    $ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    $nsRel = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    $xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    $partes = [ordered]@{
        '[Content_Types].xml' = $xml + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
            '<Default Extension="xml" ContentType="application/xml"/>' +
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' +
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' +
            '</Types>'
        '_rels/.rels' = $xml + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
            "<Relationship Id=`"rId1`" Type=`"$nsRel/officeDocument`" Target=`"xl/workbook.xml`"/></Relationships>"
        'xl/workbook.xml' = $xml + "<workbook $ns xmlns:r=`"$nsRel`"><sheets>" +
            '<sheet name="Notas Fiscais" sheetId="1" r:id="rId1"/></sheets><definedNames>' +
            "<definedName name=`"_xlnm._FilterDatabase`" localSheetId=`"0`" hidden=`"1`">'Notas Fiscais'!`$A`$1:`$J`$$linha</definedName>" +
            '</definedNames></workbook>'
        'xl/_rels/workbook.xml.rels' = $xml + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
            "<Relationship Id=`"rId1`" Type=`"$nsRel/worksheet`" Target=`"worksheets/sheet1.xml`"/>" +
            "<Relationship Id=`"rId2`" Type=`"$nsRel/styles`" Target=`"styles.xml`"/></Relationships>"
        'xl/styles.xml' = $xml + "<styleSheet $ns>" +
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>' +
            '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts>' +
            '<fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>' +
            '<fill><patternFill patternType="solid"><fgColor rgb="FF1F4E78"/><bgColor indexed="64"/></patternFill></fill>' +
            '<fill><patternFill patternType="solid"><fgColor rgb="FFFFF2CC"/><bgColor indexed="64"/></patternFill></fill></fills>' +
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>' +
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>' +
            '<cellXfs count="7"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>' +
            '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1">' +
            '<alignment horizontal="center" vertical="center"/></xf>' +
            '<xf numFmtId="1" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>' +
            '<xf numFmtId="0" fontId="0" fillId="3" borderId="0" xfId="0" applyFill="1"/>' +
            '<xf numFmtId="1" fontId="0" fillId="3" borderId="0" xfId="0" applyNumberFormat="1" applyFill="1"/>' +
            '<xf numFmtId="4" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>' +
            '<xf numFmtId="4" fontId="0" fillId="3" borderId="0" xfId="0" applyNumberFormat="1" applyFill="1"/></cellXfs>' +
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'
        'xl/worksheets/sheet1.xml' = $xml + "<worksheet $ns><dimension ref=`"A1:J$linha`"/>" +
            '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>' +
            '</sheetView></sheetViews>' + "<cols>$(-join $larguras)</cols>" +
            "<sheetData>$($linhas.ToString())</sheetData><autoFilter ref=`"A1:J$linha`"/></worksheet>"
    }

    try {
        SalvarZip $caminho $partes
    } catch {  # planilha aberta no Excel
        $caminho = Join-Path ([IO.Path]::GetDirectoryName($caminho)) (
            '{0}_{1:yyyyMMdd_HHmmss}{2}' -f [IO.Path]::GetFileNameWithoutExtension($caminho), (Get-Date), [IO.Path]::GetExtension($caminho))
        SalvarZip $caminho $partes
    }
    $caminho
}

function SalvarZip([string]$caminho, $partes) {
    Add-Type -AssemblyName System.IO.Compression
    $arquivo = [IO.File]::Open($caminho, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $zip = [IO.Compression.ZipArchive]::new($arquivo, [IO.Compression.ZipArchiveMode]::Create)
        try {
            foreach ($nome in $partes.Keys) {
                $escritor = [IO.StreamWriter]::new($zip.CreateEntry($nome).Open(), [Text.UTF8Encoding]::new($false))
                try { $escritor.Write($partes[$nome]) } finally { $escritor.Dispose() }
            }
        } finally { $zip.Dispose() }
    } finally { $arquivo.Dispose() }
}

# ----------------------------------------------------------------------------
# Programa principal
# ----------------------------------------------------------------------------

function Main {
    if ($PSVersionTable.PSEdition -eq 'Core') {
        Write-Host 'Rode com o "Windows PowerShell" (powershell.exe), que ja vem no Windows.'
        Write-Host 'O PowerShell 7 (pwsh) nao tem acesso ao OCR do Windows.'
        return 1
    }
    $raiz = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
    $pastaNotas = if ($Pasta) { $Pasta } else { Join-Path $raiz 'notas' }
    $caminhoSaida = if ($Saida) { $Saida } else { Join-Path $raiz 'planilha_nfs.xlsx' }
    $caminhoCadastro = if ($Cadastro) { $Cadastro } else { Join-Path $raiz 'fornecedores.csv' }

    if (-not (Test-Path -LiteralPath $pastaNotas -PathType Container)) {
        if (-not $Pasta) {
            [void](New-Item -ItemType Directory -Path $pastaNotas)
            Write-Host "Criei a pasta $pastaNotas. Coloque as NFs escaneadas nela e rode de novo."
        } else {
            Write-Host ((U 'ERRO: pasta n\u00e3o encontrada: ') + $pastaNotas)
        }
        return 1
    }
    $pastaNotas = (Resolve-Path -LiteralPath $pastaNotas).ProviderPath
    $arquivos = @(Get-ChildItem -LiteralPath $pastaNotas -Recurse -File |
        Where-Object { $Extensoes -contains $_.Extension.ToLower() } | Sort-Object FullName)
    if ($arquivos.Count -eq 0) {
        Write-Host "Nenhum PDF ou imagem encontrado em $pastaNotas"
        return 1
    }

    try {
        IniciarOcr
    } catch {
        Write-Host ((U 'ERRO: n\u00e3o foi poss\u00edvel usar o OCR do Windows: ') + $_.Exception.GetBaseException().Message)
        return 1
    }
    $cadastroFornecedores = CarregarCadastro $caminhoCadastro
    if ($cadastroFornecedores.Count -gt 0) { Write-Host "Cadastro de fornecedores: $($cadastroFornecedores.Count) CNPJs" }

    $caminhoSaida = [IO.Path]::GetFullPath($caminhoSaida)
    [void](New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($caminhoSaida)))
    $pastaTextos = ''
    if ($SalvarTexto) {
        $pastaTextos = Join-Path ([IO.Path]::GetDirectoryName($caminhoSaida)) 'textos_ocr'
        [void](New-Item -ItemType Directory -Force -Path $pastaTextos)
    }

    $registros = New-Object 'System.Collections.Generic.List[object]'
    $i = 0
    foreach ($arquivo in $arquivos) {
        $i++
        $nome = $arquivo.FullName.Substring($pastaNotas.Length).TrimStart([char[]]'\/')
        Write-Host "[$i/$($arquivos.Count)] $nome"
        try {
            $novos = ProcessarArquivo $arquivo.FullName $nome $cadastroFornecedores $pastaTextos
        } catch {
            $mensagem = $_.Exception.GetBaseException().Message
            Write-Host "    ERRO ao ler o arquivo: $mensagem"
            $erro = NovoRegistro $nome @() (NovoDados)
            $erro.Avisos.Add("erro ao ler o arquivo: $mensagem")
            $registros.Add($erro)
            continue
        }
        foreach ($r in $novos) {
            $d = $r.Dados
            $numero = if ($d.NumeroNF) { $d.NumeroNF } else { '?' }
            $fornecedor = if ($d.Fornecedor) { $d.Fornecedor } else { '?' }
            $pedidos = if ($d.Pedidos.Count) { $d.Pedidos -join ' / ' } else { '?' }
            $valor = if ($d.ValorTotal) { $d.ValorTotal } else { '?' }
            Write-Host ('    NF {0,9} | {1} | Pedido {2} | Valor {3}' -f $numero, $fornecedor, $pedidos, $valor)
            $registros.Add($r)
        }
    }

    $registros = JuntarContinuacoes $registros
    PadronizarFornecedores $registros
    MarcarAvisos $registros
    $caminho = GerarPlanilha $registros $caminhoSaida
    $conferir = @($registros | Where-Object { $_.Avisos.Count -gt 0 }).Count
    Write-Host ''
    Write-Host "Planilha gerada: $caminho"
    Write-Host "$($registros.Count) nota(s) | $($registros.Count - $conferir) OK | $conferir para conferir"
    return 0
}

# Ao ser carregado com ". .\robo_nf.ps1" (testes), so define as funcoes
if ($MyInvocation.InvocationName -ne '.') { exit (Main) }
