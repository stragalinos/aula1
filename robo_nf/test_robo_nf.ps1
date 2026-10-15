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
    $registros = @(
        (Reg 'a.pdf' @(1) 'FORN A LTDA' $CNPJ '10' @('4500000001')),
        (Reg 'b.pdf' @(1, 2) 'FORN B & CIA LTDA' '' '20' @('4500000002', '4500000003')),
        (Reg 'c.jpg' @(1) 'FORN C LTDA' '' '30' @()),
        (Reg 'd.jpg' @(1) 'FORN A LTDA' $CNPJ '10' @('4500000001')))
    MarcarAvisos $registros
    Igual 'mais de um pedido' ($registros[1].Avisos -join '|') 'aviso mais de um pedido'
    Igual (U 'pedido não encontrado') ($registros[2].Avisos -join '|') 'aviso sem pedido'
    Igual 'NF repetida em outro arquivo' ($registros[3].Avisos -join '|') 'aviso NF repetida'
    $xlsx = GerarPlanilha $registros (Join-Path $tmp 'nfs.xlsx')
    Igual $true (Test-Path $xlsx) 'planilha criada'
    if ($env:ROBO_NF_COPIAR_PLANILHA) { Copy-Item $xlsx $env:ROBO_NF_COPIAR_PLANILHA }
} finally {
    Remove-Item -Recurse -Force $tmp
}

Write-Host ''
if ($script:falhas) { Write-Host "$($script:falhas) de $($script:total) testes FALHARAM"; exit 1 }
Write-Host "OK: $($script:total) testes passaram"
