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
$ReNfDanfeRotulo = NovaRegex '\bN\s*[O0\u00B0.:\-]{0,3}\s*[:.]?\s*(\d{3}\.\d{3}\.\d{3})(?!\d|[.,/-]\d)'
$ReNfDanfe = NovaRegex '(?<![\d./,-])(\d{3}\.\d{3}\.\d{3})(?!\d|[.,/-]\d)'
$ReNfOutros = @(  # outros layouts (NFS-e, notas antigas...)
    (NovaRegex 'NUMERO\s+DA\s+(?:NOTA|NFS?-?E|NF)\b[^\d\n]{0,25}(\d[\d.]{0,10})'),
    (NovaRegex '\bN[O0\u00B0.]*\s*(?:DA\s+)?(?:NOTA|NFS?-?E|NF)\b[^\d\n]{0,10}(\d[\d.]{0,10})'),
    (NovaRegex 'NOTA\s+FISCAL[^\d\n]{0,30}?\bN[O0\u00B0.:]+\s*(\d[\d.]{0,10})')
)
$ReSerie = NovaRegex '\bSERIE\s*[:.]?\s*(\d{1,3})(?!\d)'

$ReCnpj = NovaRegex '(?<![0-9A-Z])([0-9A-Z]{2})\.?([0-9A-Z]{3})\.?([0-9A-Z]{3})\s?/\s?([0-9A-Z]{4})\s?-?\s?(\d{2})(?!\d)'

$ReRecebemos = NovaRegex ('RECEBEMOS\s+DE\s+(.{3,150}?)\s+(?:OS\s+PRODUTOS|OS\s+SERVICOS|AS\s+MERCADORIAS|' +
                  'O\s+PRODUTO|OS\s+ITENS|A\s+MERCADORIA)') 'Singleline'
$ReEmitente = NovaRegex 'IDENTIFICA\w*\s+DO\s+EMITENTE'
$RePrestador = NovaRegex 'PRESTADOR'
$ReRazaoSocial = NovaRegex '(?:NOME\s*/\s*)?RAZAO\s+SOCIAL\s*[:.]?\s*'
$ReFimEmitente = NovaRegex 'DESTINAT|TOMADOR'
$ReSufixo = NovaRegex '\b(?:LTDA|EIRELI|EPP|ME|S[./]?\s?A)\b\.?'
$ReRotulos = NovaRegex ('\b(?:DANFE|DOCUMENTO\s+AUXILIAR|NOTA\s+FISCAL|CNPJ|INSCRICAO|CHAVE\s+DE\s+ACESSO|' +
                'ENTRADA|SAIDA|NATUREZA|IDENTIFICACAO|PROTOCOLO|FOLHA|SERIE|ENDERECO|FONE|CEP)\b')

# Letras que o OCR costuma confundir com numeros
$ReLetraEntreDigitos = NovaRegex '(?<=\d)[OQDILS|B]{1,3}(?=[\d.])|(?<=[\d.])[OQDILS|B]{1,3}(?=\d)'

# ----------------------------------------------------------------------------
# Leitura do texto
# ----------------------------------------------------------------------------

function NovoDados {
    [pscustomobject]@{
        Fornecedor = ''; Cnpj = ''; NumeroNF = ''; Serie = ''
        Pedidos = (New-Object 'System.Collections.Generic.List[string]')
        Chave = ''; OrigemNF = ''  # OrigemNF: "chave", "danfe" ou "texto"
    }
}

function Completo($d) { [bool]($d.Fornecedor -and $d.NumeroNF -and $d.Pedidos.Count -gt 0) }

function Vazio($d) { -not ($d.Fornecedor -or $d.NumeroNF -or $d.Pedidos.Count -gt 0 -or $d.Chave) }

function CompletarCom($d, $outro) {
    # Preenche o que estiver faltando com os dados de outra pagina da mesma NF
    foreach ($campo in 'Fornecedor', 'Cnpj', 'NumeroNF', 'Serie', 'Chave', 'OrigemNF') {
        if (-not $d.$campo) { $d.$campo = $outro.$campo }
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

$TrocaDigitos = ('O', '0'), ('Q', '0'), ('D', '0'), ('I', '1'), ('L', '1'), ('|', '1'), ('S', '5'), ('B', '8')

function TrocarDigitos([string]$s) {
    foreach ($par in $TrocaDigitos) { $s = $s.Replace($par[0], $par[1]) }
    $s
}

function CorrigirDigitos([string]$texto) {
    # Troca letras confundidas pelo OCR quando estao no meio de numeros (45000I2345)
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

function EncontrarChave([string]$texto) {
    foreach ($m in $ReChaveAgrupada.Matches($texto)) {
        $chave = $m.Value -creplace '[ .]', ''
        if (ChavePlausivel $chave) { return $chave }
    }
    foreach ($m in $ReSeqDigitos.Matches($texto)) {
        $digitos = $m.Value -creplace '\D', ''
        for ($i = 0; $i -le $digitos.Length - 44; $i++) {
            if (ChavePlausivel $digitos.Substring($i, 44)) { return $digitos.Substring($i, 44) }
        }
    }
    ''
}

function SoNumero([string]$trecho) {
    $digitos = $trecho -creplace '[^0-9]', ''
    if ($digitos.Length -eq 0 -or $digitos.Length -gt 9 -or [long]$digitos -eq 0) { return '' }
    [string][long]$digitos
}

function EncontrarNumeroNF([string]$texto) {
    # Devolve @(numero, origem). Texto ja normalizado e com digitos corrigidos.
    $m = $ReNfDanfeRotulo.Match($texto)
    if ($m.Success -and (SoNumero $m.Groups[1].Value)) { return @((SoNumero $m.Groups[1].Value), 'danfe') }

    $contagem = @{}
    $ordem = New-Object 'System.Collections.Generic.List[string]'
    foreach ($m in $ReNfDanfe.Matches($texto)) {
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

function NomeDaLinha([string]$linha, [string]$linhaNorm) {
    # Corta rotulos do DANFE que o OCR juntou na mesma linha do nome
    $corte = $ReRotulos.Match($linhaNorm)
    $fim = if ($corte.Success) { $corte.Index } else { $linha.Length }
    $sufixos = $ReSufixo.Matches($linhaNorm.Substring(0, $fim))
    if ($sufixos.Count -gt 0) { $fim = $sufixos[$sufixos.Count - 1].Index + $sufixos[$sufixos.Count - 1].Length }
    $nome = LimparNome $linha.Substring(0, $fim)
    if ((ContarLetras $nome) -ge 4) { $nome } else { '' }
}

function EncontrarFornecedor([string]$texto, [string]$norm) {
    # 1) Canhoto: "RECEBEMOS DE <FORNECEDOR> OS PRODUTOS..."
    $m = $ReRecebemos.Match($norm)
    if ($m.Success) {
        $nome = LimparNome $texto.Substring($m.Groups[1].Index, $m.Groups[1].Length)
        if ((ContarLetras $nome) -ge 4) { return $nome }
    }

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
        if ($linhasNorm[$j].Contains('RECEBEMOS') -or -not $ReSufixo.IsMatch($linhasNorm[$j])) { continue }
        $nome = NomeDaLinha $linhas[$j] $linhasNorm[$j]
        if ($nome) { return $nome }
    }
    ''
}

function ExtrairDados([string]$texto, $cadastro = $null) {
    # Extrai fornecedor, numero da NF e pedidos do texto de uma pagina
    $texto = $texto.Replace("`r`n", "`n").Replace("`r", "`n")
    $norm = Normalizar $texto
    $num = CorrigirDigitos $norm
    $d = NovoDados

    $d.Chave = EncontrarChave $num
    if (-not $d.Chave) { $d.Chave = EncontrarChave $norm }

    if ($d.Chave) {
        $d.Cnpj = $d.Chave.Substring(6, 14)
        $d.Serie = [string][int]$d.Chave.Substring(22, 3)
        $d.NumeroNF = [string][long]$d.Chave.Substring(25, 9)
        $d.OrigemNF = 'chave'
    } else {
        $numero = EncontrarNumeroNF $num
        $d.NumeroNF = $numero[0]
        $d.OrigemNF = $numero[1]
        $d.Serie = EncontrarSerie $num
        $d.Cnpj = EncontrarCnpjEmitente $norm
    }

    $d.Pedidos = EncontrarPedidos $num $d.Chave

    if ($cadastro -and $d.Cnpj -and $cadastro.ContainsKey($d.Cnpj)) {
        $d.Fornecedor = $cadastro[$d.Cnpj]
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

function LerTexto($imagem, [int]$rotacao) {
    $t = [Windows.Graphics.Imaging.BitmapTransform]::new()
    $t.Rotation = [Windows.Graphics.Imaging.BitmapRotation]@{
        0 = 'None'; 90 = 'Clockwise90Degrees'; 180 = 'Clockwise180Degrees'; 270 = 'Clockwise270Degrees' }[$rotacao]

    # Amplia digitalizacoes em baixa resolucao e respeita o tamanho maximo do OCR
    $maior = [Math]::Max($imagem.PixelWidth, $imagem.PixelHeight)
    $limite = [Windows.Media.Ocr.OcrEngine]::MaxImageDimension
    $fator = 1.0
    if ($maior -lt 2400) { $fator = 3000.0 / $maior }
    if ($maior * $fator -gt $limite) { $fator = $limite / $maior }
    if ($fator -ne 1.0 -and $imagem.OrientedPixelWidth -eq $imagem.PixelWidth) {
        $t.ScaledWidth = [uint32][Math]::Floor($imagem.PixelWidth * $fator)
        $t.ScaledHeight = [uint32][Math]::Floor($imagem.PixelHeight * $fator)
        $t.InterpolationMode = [Windows.Graphics.Imaging.BitmapInterpolationMode]::Fant
    }

    $bitmap = Aguardar ($imagem.GetSoftwareBitmapAsync(
            [Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8,
            [Windows.Graphics.Imaging.BitmapAlphaMode]::Premultiplied, $t,
            [Windows.Graphics.Imaging.ExifOrientationMode]::RespectExifOrientation,
            [Windows.Graphics.Imaging.ColorManagementMode]::DoNotColorManage)) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $resultado = Aguardar ($script:MotorOcr.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    ($resultado.Lines | ForEach-Object { $_.Text }) -join "`n"
}

function LerPagina($imagem, $cadastro) {
    # Tenta a folha em pe; se faltar algo, tenta de cabeca para baixo e de lado
    $textos = New-Object 'System.Collections.Generic.List[string]'
    $dados = NovoDados
    foreach ($rotacao in 0, 180, 90, 270) {
        $textos.Add((LerTexto $imagem $rotacao))
        $dados = ExtrairDados ($textos -join "`n") $cadastro
        if (Completo $dados) { break }
    }
    [pscustomobject]@{ Dados = $dados; Texto = ($textos -join "`n`n") }
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
        elseif ($contagem[(& $chave $d)] -gt 1) { $r.Avisos.Add('NF repetida em outro arquivo') }
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
        @('Fornecedor', 45), @((U 'N\u00ba NF'), 12), @('Pedido', 14), @((U 'S\u00e9rie'), 7),
        @('CNPJ Fornecedor', 20), @('Chave de Acesso', 48), @('Arquivo', 30), @((U 'P\u00e1gina'), 8),
        @('Status', 55))
    $letras = 'ABCDEFGHI'
    # estilos: 0 normal | 1 cabecalho | 2 numero | 3 amarelo | 4 numero amarelo
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
        $status = if ($amarelo) { 'CONFERIR: ' + ($r.Avisos -join '; ') } else { 'OK' }
        [void]$linhas.Append("<row r=`"$linha`">")
        [void]$linhas.Append((& $celTexto "A$linha" $d.Fornecedor $sTexto))
        if ($d.NumeroNF) { [void]$linhas.Append((& $celNumero "B$linha" $d.NumeroNF $sNumero)) }
        else { [void]$linhas.Append((& $celTexto "B$linha" '' $sTexto)) }
        if ($d.Pedidos.Count -eq 1) { [void]$linhas.Append((& $celNumero "C$linha" $d.Pedidos[0] $sNumero)) }
        else { [void]$linhas.Append((& $celTexto "C$linha" ($d.Pedidos -join ' / ') $sTexto)) }
        [void]$linhas.Append((& $celTexto "D$linha" $d.Serie $sTexto))
        [void]$linhas.Append((& $celTexto "E$linha" (FormatarCnpj $d.Cnpj) $sTexto))
        [void]$linhas.Append((& $celTexto "F$linha" $d.Chave $sTexto))
        [void]$linhas.Append((& $celTexto "G$linha" $r.Arquivo $sTexto))
        [void]$linhas.Append((& $celTexto "H$linha" ($r.Paginas -join ', ') $sTexto))
        [void]$linhas.Append((& $celTexto "I$linha" $status $sTexto))
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
            "<definedName name=`"_xlnm._FilterDatabase`" localSheetId=`"0`" hidden=`"1`">'Notas Fiscais'!`$A`$1:`$I`$$linha</definedName>" +
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
            '<cellXfs count="5"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>' +
            '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1">' +
            '<alignment horizontal="center" vertical="center"/></xf>' +
            '<xf numFmtId="1" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>' +
            '<xf numFmtId="0" fontId="0" fillId="3" borderId="0" xfId="0" applyFill="1"/>' +
            '<xf numFmtId="1" fontId="0" fillId="3" borderId="0" xfId="0" applyNumberFormat="1" applyFill="1"/></cellXfs>' +
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'
        'xl/worksheets/sheet1.xml' = $xml + "<worksheet $ns><dimension ref=`"A1:I$linha`"/>" +
            '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>' +
            '</sheetView></sheetViews>' + "<cols>$(-join $larguras)</cols>" +
            "<sheetData>$($linhas.ToString())</sheetData><autoFilter ref=`"A1:I$linha`"/></worksheet>"
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
            Write-Host ('    NF {0,9} | {1} | Pedido {2}' -f $numero, $fornecedor, $pedidos)
            $registros.Add($r)
        }
    }

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
