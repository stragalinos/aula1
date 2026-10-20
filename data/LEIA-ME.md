# Como preencher a pasta `data/`

Esta pasta guarda **todos os números que vêm de fora do código**:

- tabelas da NBR 5410 (`nbr5410/`);
- dados de catálogo de fabricante (`catalogos/`);
- regras da concessionária (`concessionarias/`);
- suas escolhas de projeto (`criterios_projeto.yaml`).

O sistema nunca inventa esses valores, só lê o que está aqui. Enquanto um campo
estiver como `A_VALIDAR`, o cálculo que precisar dele para e diz exatamente
qual arquivo e qual campo preencher.

## Situação de cada arquivo (`metadados > status`)

| Situação | Significado | Efeito nos documentos gerados |
|---|---|---|
| `A_VALIDAR` | Ainda não conferido com a fonte | Saem com a marca d'água "TABELAS NÃO VALIDADAS" |
| `VALIDADO` | Conferido por você | Normal |
| `EXEMPLO` | Valores de exemplo (só em catálogos) | Saem com a marca d'água |
| `PROVISORIO` | Decisão provisória de projeto | O memorial lista os critérios como provisórios |
| `MODELO` | Modelo para copiar (`_modelo.yaml`) | Não entra nos cálculos |

Os arquivos da pasta `nbr5410/` só podem estar `A_VALIDAR` ou `VALIDADO`; um
teste automático garante isso.

## Passo a passo

1. Abra o arquivo num editor de texto simples, como Bloco de Notas, Notepad++ ou
   VS Code. **Não use Word.** Salve sempre em UTF-8.
2. Troque cada `A_VALIDAR` pelo valor da sua norma ou catálogo.
3. Nos `metadados`, preencha `referencia` (número da tabela ou item) e `edicao_norma`.
4. Confira o arquivo rodando no terminal:
   ```
   python -m eletroprojeto verificar-dados
   python -m eletroprojeto verificar-dados --detalhes
   ```
   A segunda forma lista cada campo que ainda falta preencher.
5. Quando o arquivo estiver todo conferido, troque `status: A_VALIDAR` por
   `status: VALIDADO` e preencha `validado_por` e `data_validacao`.
6. Rode os testes (`pytest`) para garantir que a estrutura continua certa.

## Cuidados com o formato YAML

- **Ponto decimal:** escreva `1.5`, não `1,5`. Com vírgula é erro.
- **Recuo com espaços**, nunca com TAB. Mantenha o alinhamento das linhas de cima.
- **Não renomeie as chaves** (o nome antes dos dois-pontos), a não ser que o comentário do arquivo diga que pode.
- **Seções entre aspas:** `"2.5": 24` (as aspas evitam confusão entre 2.5 e 2.50).
- **`#` começa um comentário**, e tudo depois dele na linha é ignorado.
- **Valor que não existe na norma:** escreva `NAO_SE_APLICA`.
- **Faixa sem limite superior:** escreva `SEM_LIMITE`.
- **Dica depois do marcador:** você pode deixar `"A_VALIDAR - nº da tabela"` como lembrete; continua contando como pendente.
- **Grafia exata:** escreva `A_VALIDAR` exatamente assim. "A VALIDAR" ou "a_validar" é erro.

## Formato "tabela" (linhas × colunas)

As tabelas grandes seguem o mesmo jeito da norma impressa: cada linha é uma
lista com um valor por coluna, na ordem da lista `colunas`.

```yaml
capacidade_A:
  PVC_70C:
    colunas: [A1-2, A1-3, B1-2, B1-3]   # exemplo reduzido
    linhas:
      "1.5": [11, 10, 12, 13]           # números inventados, só para mostrar o formato
      "2.5": [15, 14, 16, 17]
```

Se uma linha tiver valores de menos ou de mais, o verificador mostra qual linha
está errada.

## Faixas

Algumas colunas e chaves representam quantidades:

- `"3"` = exatamente 3;
- `"9-11"` = de 9 a 11;
- `"20+"` = 20 ou mais.

O verificador confere se as faixas não se sobrepõem nem deixam buracos.

## Por onde começar

Para rodar o primeiro projeto de teste, não precisa preencher tudo. Sugestão de ordem:

1. `nbr5410/previsao_cargas.yaml`: pontos e potências mínimas.
2. `nbr5410/regras_circuitos.yaml`
3. `nbr5410/metodos_instalacao.yaml`: pelo menos a forma que você mais usa.
4. `nbr5410/capacidade_conducao.yaml`: só `PVC_70C` e as duas colunas do método da forma acima.
5. `nbr5410/fator_temperatura.yaml`: coluna `PVC_70C-ar` e as temperaturas de referência.
6. `nbr5410/fator_agrupamento.yaml`: linha `feixe_ou_mesmo_eletroduto`.
7. `nbr5410/secoes_minimas.yaml`, `condutor_protecao.yaml`, `queda_tensao.yaml`,
   `taxa_ocupacao.yaml`, `exigencias_dr.yaml`, `dps.yaml`.
8. `catalogos/condutores.yaml`: resistividade e diâmetros do cabo PVC.
9. `catalogos/eletrodutos.yaml` e `catalogos/disjuntores.yaml`: confira os exemplos.
10. `concessionarias/energisa_ms.yaml`
11. `criterios_projeto.yaml`: confira as decisões provisórias (veja `docs/decisoes.md`).

## Lista dos arquivos

| Arquivo | O que contém | Etapa que usa |
|---|---|---|
| `nbr5410/previsao_cargas.yaml` | Pontos mínimos de iluminação e TUG; potência por ponto | b2 |
| `nbr5410/regras_circuitos.yaml` | Cargas com circuito próprio; tomadas com circuito exclusivo | b3 |
| `nbr5410/metodos_instalacao.yaml` | Forma de instalação → método de referência | b5 |
| `nbr5410/capacidade_conducao.yaml` | Capacidade de condução de corrente | b5 |
| `nbr5410/fator_temperatura.yaml` | Fatores de correção de temperatura | b5 |
| `nbr5410/fator_agrupamento.yaml` | Fatores de correção de agrupamento | b5 |
| `nbr5410/secoes_minimas.yaml` | Seções mínimas dos condutores de fase | b5 |
| `nbr5410/queda_tensao.yaml` | Limites de queda de tensão | b5 |
| `nbr5410/condutor_protecao.yaml` | Seção mínima do condutor de proteção | b6 |
| `nbr5410/exigencias_dr.yaml` | Onde a norma exige DR | b6 |
| `nbr5410/dps.yaml` | Características mínimas do DPS | b6 |
| `nbr5410/taxa_ocupacao.yaml` | Taxa máxima de ocupação de eletrodutos | b7 |
| `catalogos/condutores.yaml` | Resistividade, diâmetros, queda unitária | b5, b7 |
| `catalogos/eletrodutos.yaml` | Diâmetros internos dos eletrodutos | b7 |
| `catalogos/disjuntores.yaml` | Correntes nominais e curvas comerciais | b6 |
| `catalogos/equipamentos_tipicos.yaml` | Sugestões de potência para o formulário | f |
| `concessionarias/energisa_ms.yaml` | Demanda e categorias da Energisa MS | b4 |
| `concessionarias/_modelo.yaml` | Modelo para novas concessionárias | — |
| `criterios_projeto.yaml` | Suas escolhas de projeto | b3 a b7 |
