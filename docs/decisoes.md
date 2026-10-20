# Registro de decisões técnicas

Cada decisão tem: o que foi decidido, por quê, onde mudar e a situação.

- **PROVISÓRIA**: escolhida pelo Claude a pedido do responsável técnico, aguardando confirmação.
- **CONFIRMADA**: validada pelo responsável técnico.

Ao confirmar ou mudar uma decisão, atualize esta página e o arquivo indicado em
"Onde mudar". As decisões que dependem de interpretação da norma estão marcadas
com ⚡: são as que mais precisam do seu olhar.

---

## D1. Tipo de cômodo no formulário ⚡
**Situação:** PROVISÓRIA

**Decisão:** cada cômodo tem um campo "tipo", com 15 opções: sala, dormitório,
cozinha, copa, copa-cozinha, área de serviço, lavanderia, banheiro, lavabo,
varanda, garagem, corredor/hall, escritório, área externa e outro.

**Por quê:** as regras de quantidade e potência de TUG e as exigências de DR
mudam conforme o tipo de local. Só com o nome (por exemplo, "Quarto do casal")
o sistema não saberia qual regra aplicar.

**Onde mudar:** a lista fica em `src/eletroprojeto/nucleo/vocabulario.py`. As
regras de cada tipo ficam em `data/nbr5410/previsao_cargas.yaml` e
`data/nbr5410/exigencias_dr.yaml`.

**Confira:**
- "Banheiro" quer dizer local com chuveiro ou banheira; "lavabo" é sem chuveiro.
- Lavabo e escritório estão com regra de TUG marcada como CONFERIR.
- O lavabo ficou fora do grupo de tomadas com potência maior.

## D2. Queda de tensão ⚡
**Situação:** PROVISÓRIA

**Decisão:** o método padrão é o da **resistividade**:
- ΔV = 2 · ρ · L · Ib / S, para circuitos com 2 condutores carregados (F-N ou F-F);
- ΔV = √3 · ρ · L · Ib / S, para circuitos trifásicos.

O método da queda unitária do catálogo (V/A·km) também fica disponível.

A verificação é feita em duas partes:
1. queda do alimentador (medidor→quadro) + queda do circuito terminal ≤ limite total;
2. queda do circuito terminal sozinho ≤ limite do circuito terminal.

**Por quê:**
- O método da resistividade precisa de um único valor do catálogo.
- Ele despreza a reatância e o fator de potência. Nas seções usadas em residência, isso dá uma queda igual ou um pouco maior que a real, ou seja, a favor da segurança.
- Somar a queda real do alimentador com a do circuito evita inventar uma divisão fixa do limite entre os dois.

**Atenção:** a resistividade deve ser a da temperatura de operação do condutor
(70 °C para PVC). O valor a 20 °C deixaria a conta a favor da insegurança.

**Onde mudar:** `data/criterios_projeto.yaml`, campo
`dimensionamento > metodo_queda_tensao`. Os limites ficam em
`data/nbr5410/queda_tensao.yaml`.

## D3. Agrupamento de circuitos ⚡
**Situação:** PROVISÓRIA

**Decisão:** o técnico pode cadastrar "trechos de eletroduto", com o comprimento
e os circuitos que passam em cada um. O fator de agrupamento de cada circuito é
o do trecho mais carregado do seu percurso. Se nenhum trecho for cadastrado, o
sistema considera **todos os circuitos do quadro agrupados**, que é a situação
mais desfavorável, e escreve um aviso no memorial.

**Por quê:** sem a planta, o sistema não sabe quais circuitos dividem o mesmo
eletroduto. A hipótese conservadora nunca subdimensiona o cabo e incentiva o
técnico a informar os trechos.

**Onde mudar:** `data/criterios_projeto.yaml`, campo
`agrupamento > sem_trechos_informados`.

## D4. Comprimento dos circuitos
**Situação:** PROVISÓRIA

**Decisão:** cada cômodo recebe a "distância de percurso até o quadro", em metros,
já contando subidas e descidas. O comprimento de um circuito é a maior distância
entre os cômodos que ele atende, multiplicada por `fator_percurso`, que vale 1,0.

**Onde mudar:** `data/criterios_projeto.yaml`, campo `comprimentos > fator_percurso`.

## D5. Concessionária Energisa MS
**Situação:** PROVISÓRIA (só a estrutura; todos os valores estão A_VALIDAR)

**Decisão:** `data/concessionarias/energisa_ms.yaml` tem:
- o documento de referência;
- as tensões disponíveis e o esquema de aterramento;
- o cálculo de demanda por grupos de carga (por faixas de potência acumulada ou pela quantidade de aparelhos);
- as categorias de atendimento, com disjuntor geral, ramal e aterramento.

**Confira:** se essa estrutura representa como a Energisa calcula a demanda e
define as categorias. Se a tabela deles for organizada de outro jeito, descreva
o formato (sem copiar o texto) para o sistema ser adaptado.

## D6. Ordem disjuntor × cabo ⚡
**Situação:** PROVISÓRIA

**Decisão:** primeiro o disjuntor, depois o cabo:
1. escolhe a menor corrente nominal comercial In ≥ Ib;
2. escolhe a menor seção cuja capacidade corrigida (Iz × fatores) seja ≥ In;
3. aplica os critérios de queda de tensão e de seção mínima, e vale a maior seção.

**Por quê:** é direto e garante a coordenação Ib ≤ In ≤ Iz por construção.

**Onde mudar:** `data/criterios_projeto.yaml`, campo `dimensionamento > ordem`
(a alternativa é `cabo_primeiro`).

## D7. Divisão de circuitos
**Situação:** PROVISÓRIA

**Decisão:**
- Iluminação e tomadas ficam sempre em circuitos separados. A norma admite exceção, mas ela não é usada.
- Corrente de projeto máxima de 10 A por circuito de iluminação e de TUG. É prática comum de livros didáticos, não exigência da norma.
- TUGs de cômodos diferentes podem dividir o mesmo circuito, exceto as dos cômodos de circuito exclusivo (cozinha, copa, área de serviço, lavanderia), que só se juntam entre si.
- Cada TUE tem circuito próprio.

**Onde mudar:** `data/criterios_projeto.yaml`, bloco `circuitos`.

## D8. Fatores de potência padrão
**Situação:** PROVISÓRIA

**Decisão:**
- Iluminação: 1,0. TUG: 0,8 (prática de livros didáticos).
- TUE: o fator de potência é obrigatório por equipamento, e o formulário sugere o valor de `catalogos/equipamentos_tipicos.yaml`.

**Por quê:** a previsão mínima da norma para iluminação e TUG é em VA, então a
corrente desses circuitos não depende do fator de potência. Ele só é usado para
converter VA em W, por exemplo na carga instalada em kW.

**Confira:** se a categoria da Energisa é escolhida pela carga instalada em kW,
um fator menor reduz a carga declarada. Para ficar a favor da segurança, use 1,0.

**Onde mudar:** `data/criterios_projeto.yaml`, bloco `fator_potencia_padrao`.

## D9. Dispositivos DR
**Situação:** PROVISÓRIA

**Decisão:** DR somente nos circuitos em que a norma exige (opção `todos`
disponível), agrupados com no máximo 4 circuitos por DR.

**Por quê:** é um meio-termo entre custo (um DR por circuito) e desligamentos
indesejados (um DR geral soma as fugas de toda a casa).

**Onde mudar:** `data/criterios_projeto.yaml`, bloco `protecao`.

## D10. Curva dos disjuntores
**Situação:** PROVISÓRIA

**Decisão:** curva B para iluminação, TUG e TUE resistivas (chuveiro, forno,
torneira) e curva C para equipamentos com motor (ar-condicionado, bomba,
máquinas de lavar).

**Confira:** a disponibilidade no comércio da sua região. Muita gente usa curva C
em tudo porque é a mais fácil de achar.

**Onde mudar:** `data/criterios_projeto.yaml`, bloco `protecao`.

## D11. Curto-circuito e seccionamento automático ⚡
**Situação:** PROVISÓRIA

**Decisão:** fora do MVP. O memorial vai trazer um aviso de que a verificação
da proteção contra curto-circuito e do seccionamento automático (impedância do
laço de falta) deve ser feita pelo responsável técnico.

**Por quê:** a verificação depende da corrente de curto-circuito presumida no
ponto de entrega, um dado da concessionária que o formulário ainda não pede.

## D12. Lista de materiais
**Situação:** PROVISÓRIA

**Decisão:**
- 1 interruptor simples por cômodo, editável no formulário.
- Caixa 4×2 para tomadas e interruptores; caixa octogonal 4×4 para ponto de teto.
- 10 % de folga no comprimento dos cabos.

**Onde mudar:** `data/criterios_projeto.yaml`, bloco `materiais`.

## D13. Repositório, nome e sistema operacional
**Situação:** PROVISÓRIA

**Decisão:** o projeto fica na raiz deste repositório e a pasta `Aula1/` não foi
alterada. O nome provisório é `eletroprojeto`. O README traz comandos para
Windows e para Linux/macOS.

## D14. Neutro com a mesma seção da fase
**Situação:** PROVISÓRIA (decisão nova, não estava nas perguntas)

**Decisão:** o neutro sempre tem a mesma seção da fase.

**Por quê:** é a favor da segurança e simplifica o MVP. A redução do neutro só
seria possível em circuitos trifásicos de seção grande, o que é raro em
residência.

**Onde mudar:** `data/criterios_projeto.yaml`, campo
`dimensionamento > neutro_igual_a_fase`.

## D15. Temperatura fora da tabela
**Situação:** PROVISÓRIA (decisão nova)

**Decisão:** se a temperatura do projeto não estiver na tabela de fatores, o
sistema usa a linha de temperatura imediatamente acima, sem interpolar.

**Por quê:** uma temperatura mais alta dá um fator menor, então a escolha fica a
favor da segurança.

**Onde mudar:** `data/criterios_projeto.yaml`, campo
`dimensionamento > temperatura_intermediaria`.

## D16. Tecnologias
**Situação:** PROVISÓRIA (proposta no plano, aprovada pelo responsável)

**Decisão:**
- HTMX + Jinja2 em vez de Next.js, para ter uma linguagem só e nenhum build de JavaScript.
- ReportLab para gerar PDF, que instala com `pip` no Windows.
- YAML para os dados, porque aceita comentários.
- SQLite no início, com SQLAlchemy para migrar a PostgreSQL depois.

## D17. Unidades nos nomes
**Situação:** PROVISÓRIA

**Decisão:** campos e variáveis terminam com a unidade na grafia do SI:
`_A`, `_V`, `_VA`, `_W`, `_kW`, `_kA`, `_mA`, `_mm2`, `_m`, `_m2`, `_C`, `_pct`.

Exemplos: `corrente_maxima_tug_A`, `potencia_inicial_VA`, `diametro_externo_mm`.

**Por quê:** evita confundir mA com A ou kW com W ao ler o código e os arquivos de dados.

## D18. Tabelas grandes no formato linhas × colunas
**Situação:** PROVISÓRIA

**Decisão:** capacidade de condução, fatores de temperatura, fatores de
agrupamento e queda unitária usam o formato `colunas` + `linhas`, igual ao da
norma impressa.

**Por quê:** fica fácil copiar linha por linha da norma, e o verificador avisa
se faltar ou sobrar valor numa linha.
