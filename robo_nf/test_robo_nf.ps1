# Testes da leitura do texto das NFs (nao usam o OCR).
# Rodar:  powershell -ExecutionPolicy Bypass -File test_robo_nf.ps1

. (Join-Path $PSScriptRoot 'robo_nf.ps1')

$script:total = 0
$script:falhas = 0

function Igual($esperado, $obtido, [string]$teste) {
    $script:total++
    if ("$esperado" -cne "$obtido") {
        $script:falhas++
        Write-Host "FALHOU: $teste`n   esperado: $esperado`n   obtido:   $obtido"
    }
}

function MontarChave([string]$cnpj, [int]$numero, [int]$serie = 1) {
    $base = '352610' + $cnpj + '55' + $serie.ToString('000') + $numero.ToString('000000000') + '1' + '87654321'
    $base + (DvMod11 (-join $base.ToCharArray()[42..0]) (@(2, 3, 4, 5, 6, 7, 8, 9) * 6))
}

function Agrupar([string]$chave) { (0..10 | ForEach-Object { $chave.Substring($_ * 4, 4) }) -join ' ' }

$CNPJ = '12345678000195'
$DANFE = @'
RECEBEMOS DE FORNECEDOR EXEMPLO INDÚSTRIA E COMÉRCIO LTDA OS PRODUTOS E/OU SERVIÇOS
CONSTANTES DA NOTA FISCAL ELETRÔNICA INDICADA AO LADO          NF-e
DATA DE RECEBIMENTO  IDENTIFICAÇÃO E ASSINATURA DO RECEBEDOR   Nº 000.012.345
                                                               SÉRIE 001
IDENTIFICAÇÃO DO EMITENTE
FORNECEDOR EXEMPLO INDÚSTRIA E COMÉRCIO LTDA       DANFE
RUA DAS INDÚSTRIAS, 1500                           Nº 000.012.345  SÉRIE 001
CHAVE DE ACESSO
{chave}
INSCRIÇÃO ESTADUAL 123.456.789.110    CNPJ 12.345.678/0001-95
DESTINATÁRIO / REMETENTE
NOME / RAZÃO SOCIAL
MINHA EMPRESA COMPRADORA S.A.        CNPJ 11.222.333/0001-81
DADOS ADICIONAIS
Pedido de compra: 4500012345   Valor aprox. tributos R$ 45,32
'@

# --- chave de acesso ---
$chave = MontarChave $CNPJ 12345
Igual $true (ChavePlausivel $chave) 'chave valida'
Igual $chave (EncontrarChave "CHAVE DE ACESSO`n$(Agrupar $chave)`n") 'chave agrupada'
$errada = $chave.Substring(0, 43) + (([int]$chave.Substring(43, 1) + 1) % 10)
Igual $false (ChavePlausivel $errada) 'chave com digito errado'
Igual '' (EncontrarChave (Agrupar $errada)) 'chave errada ignorada'
Igual $true (CnpjValido '12ABC34501DE35') 'CNPJ alfanumerico (exemplo da Receita)'
$alfa = MontarChave '12ABC34501DE35' 777
$d = ExtrairDados "CHAVE DE ACESSO $(Agrupar $alfa)`nPEDIDO 4500000001"
Igual '777' $d.NumeroNF 'NF pela chave com CNPJ alfanumerico'
Igual '12ABC34501DE35' $d.Cnpj 'CNPJ alfanumerico da chave'

# --- DANFE completo ---
$d = ExtrairDados $DANFE.Replace('{chave}', (Agrupar $chave))
Igual 'FORNECEDOR EXEMPLO INDÚSTRIA E COMÉRCIO LTDA' $d.Fornecedor 'fornecedor pelo canhoto'
Igual '12345' $d.NumeroNF 'numero pela chave'
Igual '1' $d.Serie 'serie'
Igual $CNPJ $d.Cnpj 'cnpj'
Igual '4500012345' ($d.Pedidos -join '|') 'pedido'
Igual 'chave' $d.OrigemNF 'origem chave'

$d = ExtrairDados $DANFE.Replace('{chave}', '(ilegível)')
Igual '12345' $d.NumeroNF 'numero impresso sem chave'
Igual 'danfe' $d.OrigemNF 'origem danfe'
Igual $CNPJ $d.Cnpj 'cnpj do emitente (nao do destinatario)'

$d = ExtrairDados "DANFE`nNº 000.0I2.345 SÉRIE 1`nPEDIDO 4500012345"
Igual '12345' $d.NumeroNF 'numero com letra trocada pelo OCR'

# --- pedidos ---
Igual '4500099887|4500099888' ((EncontrarPedidos 'PEDIDOS: 4500099887, 4500099888 e novamente 4500099887') -join '|') 'varios pedidos'
Igual '4500012345' ((EncontrarPedidos (CorrigirDigitos (Normalizar 'Seu pedido nº 4500 0I2345'))) -join '|') 'pedido quebrado'
Igual '4500012345' ((EncontrarPedidos (CorrigirDigitos (Normalizar 'Ped. compra: 45OOO12345'))) -join '|') 'pedido com letras O'
$outros = "CNPJ 45.123.456/0001-00  CNPJ 45123456000100  FONE (45) 3333-4444`nEAN 7894500012345  VALOR 4.500.123,45  PROTOCOLO 145000123456789"
Igual '' ((EncontrarPedidos $outros) -join '|') 'nao confunde com outros numeros'
$c2 = '35261045000123450001550010000012341000000017'
Igual '' ((EncontrarPedidos "CHAVE $c2" $c2) -join '|') 'ignora chave continua'
Igual '' ((EncontrarPedidos (Agrupar $c2) $c2) -join '|') 'ignora chave agrupada'
Igual '' ((EncontrarPedidos 'PEDIDO 45000123456') -join '|') 'pedido com 11 digitos'

# --- fornecedor ---
function Fornecedor([string]$t) { EncontrarFornecedor $t (Normalizar $t) }
Igual 'METALÚRGICA SILVA S/A' (Fornecedor "IDENTIFICAÇÃO DO EMITENTE`n`nMETALÚRGICA SILVA S/A          DANFE`nAV. BRASIL, 100`nDESTINATÁRIO`nMINHA EMPRESA LTDA") 'bloco do emitente'
Igual 'PAPELARIA CENTRAL LTDA - ME' (Fornecedor "DANFE  0-ENTRADA 1-SAÍDA`nPAPELARIA CENTRAL LTDA - ME   CNPJ 11.111.111/0001-11`nDESTINATÁRIO / REMETENTE`nMINHA EMPRESA COMPRADORA LTDA") 'linha com LTDA'
$nfse = "PREFEITURA MUNICIPAL`nNÚMERO DA NOTA: 1234`nPRESTADOR DE SERVIÇOS`nRazão Social: SERVIÇOS TÉCNICOS ALFA LTDA`nTOMADOR DE SERVIÇOS`nRazão Social: MINHA EMPRESA S.A.`nPedido 4500001111"
$d = ExtrairDados $nfse
Igual 'SERVIÇOS TÉCNICOS ALFA LTDA' $d.Fornecedor 'NFS-e prestador'
Igual '1234' $d.NumeroNF 'NFS-e numero'
Igual 'texto' $d.OrigemNF 'NFS-e origem'
$d = ExtrairDados $DANFE.Replace('{chave}', (Agrupar $chave)) @{ $CNPJ = 'Fornecedor Exemplo (cód. SAP 100200)' }
Igual 'Fornecedor Exemplo (cód. SAP 100200)' $d.Fornecedor 'cadastro padroniza nome'
Igual 'ACME SOLUCOES S.A.' (LimparNome ' ACME SOLUCOES S.A. ') 'mantem ponto de S.A.'

# --- casos reais (primeiras NFs lidas com o OCR do Windows) ---
Igual '' (ExtrairDados "INSCRIÇÃO ESTADUAL`n252.405.749`nCNPJ 05.283.785/0001-70`nPEDIDO 4501216027").NumeroNF 'IE nao vira numero da NF'
Igual '93269' (ExtrairDados 'INSCRIÇÃO ESTADUAL 252.405.749   NF-e Nº 000.093.269 SÉRIE 1').NumeroNF 'IE ao lado do numero'
Igual '|' ((EncontrarNumeroNF 'DANFE 252.405.749') -join '|') 'sem rotulo precisa de zeros a esquerda'
Igual '93269|danfe' ((EncontrarNumeroNF 'DANFE 000.093.269') -join '|') 'sem rotulo com zeros'
Igual '93269|danfe' ((EncontrarNumeroNF (CorrigirDigitos (Normalizar 'Nº 000. 093 .269'))) -join '|') 'espacos do OCR no numero'
foreach ($t in "NF-e`nNº 93269`nSÉRIE 1", 'Nº. 000093269 SÉRIE: 001') {
    Igual '93269|danfe' ((EncontrarNumeroNF (CorrigirDigitos (Normalizar $t))) -join '|') "numero antes da serie: $t"
}
$grupos = Agrupar (MontarChave $CNPJ 85482)
Igual '85482' (ExtrairDados "CHAVE DE ACESSO`n$($grupos.Substring(0, 27))`n$($grupos.Substring(27))`nConsulta de autenticidade").NumeroNF 'chave em duas linhas'
$boa = MontarChave $CNPJ 85482
$errada = (0..9 | ForEach-Object { $boa.Substring(0, 40) + $_ + $boa.Substring(41) } | Where-Object { -not (ChavePlausivel $_) } | Select-Object -First 1)
$d = ExtrairDados "CHAVE DE ACESSO $(Agrupar $errada)"
Igual "85482|chave_parcial|$CNPJ|" ("$($d.NumeroNF)|$($d.OrigemNF)|$($d.Cnpj)|$($d.Chave)") 'chave com digito ilegivel'
$d = ExtrairDados "Nº 000.085.482 SÉRIE 1`nCHAVE DE ACESSO $(Agrupar $errada)"
Igual '85482|danfe' ("$($d.NumeroNF)|$($d.OrigemNF)") 'chave parcial confirma numero impresso'
$d = ExtrairDados "Nº 000.085.483 SÉRIE 1`nCHAVE DE ACESSO $(Agrupar $errada)"
Igual '85483|divergente' ("$($d.NumeroNF)|$($d.OrigemNF)") 'chave parcial diverge do impresso'
foreach ($lixo in 'trtVtE a 1.1-snrv oagoav sa', 'eoyssuw oavt ov sa', '•v•s sa', 'IV ayJ.sa',
                  'svax•UN00Nd a sa.', 'bd.Remget•gçi0 Ltda', 'van wu.st501 SA.', 'OL18LSta•a-m ¿•z sa') {
    Igual '' (Fornecedor "$lixo`nDESTINATÁRIO / REMETENTE`nMINHA EMPRESA LTDA") "lixo antes do destinatario: $lixo"
    Igual '' (Fornecedor "IDENTIFICAÇÃO DO EMITENTE`n$lixo`nDESTINATÁRIO / REMETENTE") "lixo no bloco do emitente: $lixo"
}
foreach ($nome in 'DAL PINO INDUSTRIA DE SERRAS LTDA', 'Frigostrella do Brasil Ind.Refrigeracao Ltda',
                  'BETTCHER DO BRASIL COMERCIO DE MAQUINAS LTDA', 'METALÚRGICA SILVA S/A',
                  'PAPELARIA CENTRAL LTDA - ME', 'JBT MAREL BRASIL LTDA', 'FORTUNCERES S.A.') {
    Igual $nome (NomePlausivel $nome) "nome real aceito: $nome"
}
foreach ($linha in 'RUA DAS INDÚSTRIAS, 1500 - DISTRITO INDUSTRIAL', 'AV. BRASIL, 100', 'SÃO PAULO - SP CEP 01000-000',
                   '000123 PARAFUSO SEXTAVADO M8 73181500 100 1,50', 'ossaovadaavHS — WIVHTOS TOO IIHAS') {
    Igual '' (Fornecedor "IDENTIFICAÇÃO DO EMITENTE`n$linha`nDESTINATÁRIO / REMETENTE") "nao e fornecedor: $linha"
}
Igual 'COMERCIO DE VALVULAS LTDA' (Fornecedor 'RECEBEMOS DE sn«ox COMERCIO DE VALVULAS LTDA OS PRODUTOS CONSTANTES DA NOTA') 'tira pedaco ilegivel'

# --- leitura melhor: zeros lidos como O, numero sem "N.", valor total, canhoto com erro ---
$num = CorrigirDigitos (Normalizar 'Nº OOO.O93.269  SC-401  LTDA  ISO  S/A')
Igual $true ($num.Contains('000.093.269') -and $num.Contains('SC-401  LTDA  ISO  S/A')) 'zeros lidos como letra'
Igual '93269|danfe' ((EncontrarNumeroNF $num) -join '|') 'numero com zeros lidos como letra'
foreach ($t in 'Nº 000,093,269', 'N° 000 093 269', 'NQ 000.093.269', "000093269`nSÉRIE 1") {
    Igual '93269|danfe' ((EncontrarNumeroNF (CorrigirDigitos (Normalizar $t))) -join '|') "numero: $t"
}
foreach ($t in 'VALOR TOTAL DA NOTA R$ 1.234,56', 'V. TOTAL DA NOTA: 1234,56', 'Valor total da NF-e 1.234,56',
               'VALOR TOTALDA NOTA 1.234,56', 'VALOR TOTAL. DA NOTA 1.234,56') {
    Igual '1234.56|rotulo' ((EncontrarValorTotal (CorrigirDigitos (Normalizar $t))) -join '|') "valor na mesma linha: $t"
}
$t = "VALOR DO FRETE VALOR DO SEGURO DESCONTO OUTRAS DESP. VALOR DO IPI VALOR TOTAL DA NOTA`n0,00 0,00 0,00 0,00 120,00 2.520,00"
Igual '2520.00|rotulo' ((EncontrarValorTotal (Normalizar $t)) -join '|') 'valor na linha de baixo'
$t = "VALOR TOTAL DOS PRODUTOS 2.400,00`nTRIBUTOS R$ 45,32 (19,70%)`nPESO 3.500,000"
Igual '2400.00|maior' ((EncontrarValorTotal (Normalizar $t)) -join '|') 'valor estimado sem rotulo'

function Palavra($texto, $x, $y) { , @($texto, $x, $y, (11 * $texto.Length), 20) }
$quadro = @(
    (Palavra 'VALOR' 600 40), (Palavra 'TOTAL' 670 40), (Palavra 'DOS' 735 40), (Palavra 'PRODUTOS' 775 40),
    (Palavra '2.400,00' 800 70),
    (Palavra 'VALOR' 300 100), (Palavra 'DO' 365 100), (Palavra 'IPI' 395 100),
    (Palavra 'VALOR' 600 100), (Palavra 'TOTAL' 670 100), (Palavra 'DA' 735 100), (Palavra 'NOTA' 765 100),
    (Palavra '120,00' 380 130), (Palavra '2.520,00' 800 130))
Igual '2520.00' (ValorPeloRotulo $quadro) 'valor pela posicao na folha'
$visual = (TextoVisual $quadro).Split("`n")
Igual 'VALOR DO IPI | VALOR TOTAL DA NOTA' $visual[2] 'texto visual: linha dos rotulos'
Igual '120,00 | 2.520,00' $visual[3] 'texto visual: linha dos valores'
$d = ExtrairDados (TextoVisual $quadro)
Igual '2520.00|rotulo' "$($d.ValorTotal)|$($d.OrigemValor)" 'valor pelo texto visual'
$ipiPerto = @(
    , @('VALOR', 1395, 1037, 46, 21); , @('DO', 1450, 1037, 30, 21); , @('IPI.', 1490, 1037, 40, 21)
    , @('VALOR', 1660, 1042, 90, 19); , @('TOTALDA', 1758, 1042, 98, 18); , @('NOTA', 1868, 1042, 56, 19)
    , @('120,00', 1554, 1078, 99, 28); , @('4.025,00', 1926, 1079, 130, 33))
Igual 5 $ipiPerto[0].Count 'montagem da lista de palavras'
Igual '4025.00' (ValorPeloRotulo $ipiPerto) 'valor do IPI mais perto nao e o total'

# folha torta (0,6 grau): o fim da linha fica mais alto que o comeco
$frase = 'RECEBEMOS DE DISTRIBUIDORA BOA VISTA EIRELI OS PRODUTOS E/OU SERVIÇOS'.Split(' ')
$torta = New-Object 'System.Collections.Generic.List[object]'
$x = 60
foreach ($t in $frase) { $torta.Add(@($t, $x, (100 - 0.0105 * $x), (11 * $t.Length), 24, 1)); $x += 11 * $t.Length + 12 }
$torta.Insert(0, @('CONSTANTES', $x, (100 - 0.0105 * $x - 9), 110, 18, 1))  # caixa mais alta (caso real)
$torta.Add(@('NOTA', 60, 128, 44, 24, 2)); $torta.Add(@('FISCAL', 116, 128, 66, 24, 2))
$visual = (TextoVisual $torta).Split("`n")
Igual (($frase -join ' ') + ' CONSTANTES') $visual[0] 'folha torta: frase inteira na mesma linha'
Igual 'DISTRIBUIDORA BOA VISTA EIRELI' (Fornecedor $visual[0]) 'folha torta: fornecedor'
foreach ($caso in @(
        @("RFEBEMOS DE DIMENSIONAL BRASIL SOLUCOES LTDA OS PRODUTOS E/OU SERVIÇOS", 'DIMENSIONAL BRASIL SOLUCOES LTDA'),
        @("RECEBEM(S DE DAL PINO INDUSTRIA DE SERRAS LTDA`nOS PRODUT0S CONSTANTES", 'DAL PINO INDUSTRIA DE SERRAS LTDA'))) {
    Igual $caso[1] (Fornecedor $caso[0]) "canhoto com erro de OCR: $($caso[1])"
}
Igual 'JARVIS DO BRASIL FERRAMENTAS INDUSTRIAIS LTDA' (NomePlausivel 'DE JARVIS DO BRASIL FERRAMENTAS INDUSTRIAIS LTDA') 'tira o DE que sobrou'
Igual 'COMERCIAL DE FERRAGENS NOVA ERA' (NomePlausivel 'COMERCIAL DE FERRAGENS NOVA ERA auxiliar da') 'tira sobra do fim do nome'

$certo = 'JARVIS DO BRASIL FERRAMENTAS INDUSTRIAIS LTDA'
$nomes = @(@($certo, ''), @($certo, ''), @('JARVIS DO BRASL', '46537536000141'), @('JARVIS DO BRASIL FERRAMTXMS', ''),
           @('JARVLS DO BRASIL FERRAP,mT4S', ''), @('NDUSIRIAIS LTDA', '46537536000141'),
           @('BETTCHER DO BRASIL COMERCIO DE MAQUINAS LTDA', ''), @('DAL PENO INDUSTRIA DE SERRAS LTDA', ''),
           @('COMERCIAL ELETRICA PJ LTDA', ''), @('COMERCIAL ELETRICA SC LTDA', ''))
$regs = @(for ($i = 0; $i -lt $nomes.Count; $i++) {
    $d = NovoDados; $d.Fornecedor = $nomes[$i][0]; $d.Cnpj = $nomes[$i][1]; NovoRegistro "$i.pdf" @(1) $d })
PadronizarFornecedores $regs
$esperado = @($certo) * 6 + @($nomes[6..9] | ForEach-Object { $_[0] })
Igual ($esperado -join '|') (($regs | ForEach-Object { $_.Dados.Fornecedor }) -join '|') 'padroniza grafias do mesmo fornecedor'

# --- cadastro e planilha ---
$tmp = Join-Path ([IO.Path]::GetTempPath()) ("robo_nf_" + [guid]::NewGuid())
[void](New-Item -ItemType Directory -Path $tmp)
try {
    $csv = Join-Path $tmp 'fornecedores.csv'
    [IO.File]::WriteAllBytes($csv, [Text.Encoding]::GetEncoding(28591).GetBytes("CNPJ;Fornecedor`r`n12.345.678/0001-95;Fornecedor Exemplo Ind. e Com.`r`n"))
    $cad = CarregarCadastro $csv
    Igual 'Fornecedor Exemplo Ind. e Com.' $cad[$CNPJ] 'cadastro CSV do Excel'

    function Reg($arquivo, $paginas, $forn, $cnpj, $nf, $pedidos, $origem = 'danfe') {
        $d = NovoDados
        $d.Fornecedor = $forn; $d.Cnpj = $cnpj; $d.NumeroNF = $nf; $d.OrigemNF = $origem
        foreach ($p in $pedidos) { $d.Pedidos.Add($p) }
        NovoRegistro $arquivo $paginas $d
    }
    $okValor = Reg 'a.pdf' @(1) 'FORN A LTDA' $CNPJ '10' @('4500000001')
    $okValor.Dados.ValorTotal = '2520.00'; $okValor.Dados.OrigemValor = 'rotulo'
    $registros = @(
        $okValor,
        (Reg 'b.pdf' @(1, 2) 'FORN B & CIA LTDA' '' '20' @('4500000002', '4500000003')),
        (Reg 'c.jpg' @(1) 'FORN C LTDA' '' '30' @()),
        (Reg 'd.jpg' @(1) 'FORN A LTDA' $CNPJ '10' @('4500000001')))
    $semNome = Reg '19.pdf' @(1) '' '06913480002616' '2' @('4501229433')
    PadronizarFornecedores @((Reg '20.pdf' @(1) 'DIMENSIONAL BRASIL LTDA' '06913480002616' '1' @()), $semNome)
    Igual 'DIMENSIONAL BRASIL LTDA' $semNome.Dados.Fornecedor 'fornecedor pelo CNPJ de outra NF'

    MarcarAvisos $registros
    Igual $true ($registros[1].Avisos.Contains('mais de um pedido')) 'aviso mais de um pedido'
    Igual $true ($registros[2].Avisos.Contains((U 'pedido n\u00e3o encontrado'))) 'aviso sem pedido'
    Igual ('NF repetida em outro arquivo|' + (U 'valor total n\u00e3o encontrado')) ($registros[3].Avisos -join '|') 'aviso NF repetida'
    $xlsx = GerarPlanilha $registros (Join-Path $tmp 'nfs.xlsx')
    Igual $true (Test-Path $xlsx) 'planilha criada'
    if ($env:ROBO_NF_COPIAR_PLANILHA) { Copy-Item $xlsx $env:ROBO_NF_COPIAR_PLANILHA }
} finally {
    Remove-Item -Recurse -Force $tmp
}

Write-Host ''
if ($script:falhas) { Write-Host "$($script:falhas) de $($script:total) testes FALHARAM"; exit 1 }
Write-Host "OK: $($script:total) testes passaram"
