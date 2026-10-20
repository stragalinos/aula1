# CLAUDE.md: regras do projeto eletroprojeto

Contexto para as próximas sessões. Leia antes de qualquer alteração.

## O projeto

SaaS para técnicos e eletricistas gerarem projetos elétricos residenciais de
baixa tensão conforme a ABNT NBR 5410: previsão de cargas, circuitos,
dimensionamento, quadro de cargas (.xlsx), memoriais (.docx/PDF), diagrama
unifilar (SVG/PDF/DXF) e lista de materiais.

É uma **ferramenta de apoio**. Todo documento gerado deve indicar que precisa
ser revisado e assinado por profissional habilitado (TRT/ART), com campos para
responsável técnico e número da TRT/ART na capa e no rodapé.

**Quem usa este repositório** é técnico em eletrotécnica, não programador:
- explique as decisões em linguagem simples;
- peça validação nas partes técnicas de elétrica;
- ao fim de cada etapa: rode os testes, mostre o resultado, explique o que foi feito e diga o que ele precisa conferir ou preencher.

## Regras obrigatórias

1. **Nunca inventar valores de tabelas normativas.**
   - Todo número da NBR 5410 fica em `data/nbr5410/*.yaml`, com `A_VALIDAR` até o responsável preencher a partir da cópia licenciada dele.
   - Valores de exemplo só em `data/catalogos/`, com `status: EXEMPLO`; nunca em `data/nbr5410/` (há um teste que garante isso).
   - O código lê esses valores só por meio de `RepositorioDados` / `Tabela.obter()`.
2. **Não copiar texto das normas ABNT.** Implemente as regras em código e escreva os textos com palavras próprias. Cite a norma apenas pelo número do item ou da tabela (campo `referencia` dos arquivos de dados).
3. **Regras de concessionária** ficam em `data/concessionarias/<id>.yaml` (começando por `energisa_ms`). Nova concessionária = copiar `_modelo.yaml`.
4. **Toda função de cálculo tem testes pytest** com casos conferíveis à mão (a conta em comentário) e registra o passo a passo: fórmula, valores, resultado e origem.
5. **Camadas separadas.** `nucleo/` não importa nada de `web/`, `documentos/`, `diagrama/` nem `redacao/`. As dependências só descem.
6. **Todo texto** do sistema, dos documentos, das mensagens de erro, dos comentários e das docstrings fica em português do Brasil.
7. **Dúvida técnica de elétrica** (interpretação de norma, critério de projeto): pergunte ao responsável, não assuma. Quando ele delegar a decisão, registre em `docs/decisoes.md` como PROVISÓRIA e deixe configurável em `data/criterios_projeto.yaml`.
8. **A IA** (futura integração com a API do Claude no módulo `redacao/`) só redige texto a partir de resultados prontos; nunca calcula.

## Convenções de código

- Python 3.11+, layout `src/`, pacote `eletroprojeto`.
- Nomes em português sem acento.
- Unidade no fim do nome, com a grafia do SI: `_A`, `_V`, `_VA`, `_W`, `_kW`, `_mm2`, `_m`, `_m2`, `_pct`, `_C`, `_kA`, `_mA` (decisão D17).
- Nenhum valor numérico normativo em `.py`: só identificadores (`nucleo/vocabulario.py`).
- Tabelas grandes de `data/` usam o formato `colunas` + `linhas`. Faixas são escritas como `"3"`, `"9-11"` ou `"20+"`.
- Marcadores em `data/`: `A_VALIDAR` (pendente, pode ter uma dica depois), `NAO_SE_APLICA`, `SEM_LIMITE`.
- Formatação e lint com ruff (linha de 100 caracteres).

## Comandos

```bash
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest                             # todos os testes
python -m eletroprojeto verificar-dados [--detalhes]
ruff check . && ruff format --check .
```

## Onde está cada coisa

- `docs/PLANO.md`: plano, arquitetura e etapas, com a situação de cada uma.
- `docs/decisoes.md`: decisões técnicas D1, D2... (PROVISÓRIA ou CONFIRMADA).
- `data/LEIA-ME.md`: guia de preenchimento das tabelas.
- `src/eletroprojeto/nucleo/tabelas.py`: leitura e validação de `data/`.
- `src/eletroprojeto/nucleo/vocabulario.py`: tipos de cômodo, circuitos, esquemas e opções de critérios.
- `tests/fixtures/tabelas_ficticias/`: números INVENTADOS, só para testar a lógica.

## Estado das etapas

- [x] **a**: estrutura, arquivos de dados, leitor/validador, `verificar-dados`
- [ ] **b1–b8**: núcleo de cálculo (modelos, previsão, circuitos, demanda, condutores, proteção, eletrodutos/materiais, projeto completo)
- [ ] **c**: quadro de cargas .xlsx
- [ ] **d**: memoriais .docx/PDF
- [ ] **e**: diagrama unifilar
- [ ] **f**: interface web
- [ ] **g**: usuários e projetos salvos

Branch de desenvolvimento: `claude/fervent-keller-gvhk98`.
