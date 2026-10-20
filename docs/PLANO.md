# Plano do projeto eletroprojeto

Sistema web (SaaS) para técnicos e eletricistas gerarem projetos elétricos
residenciais de baixa tensão conforme a ABNT NBR 5410, com documentação
completa e explicação em linguagem clara.

**É uma ferramenta de apoio:** todo documento indica que precisa ser revisado e
assinado por profissional habilitado (TRT/ART).

As decisões técnicas estão em [`decisoes.md`](decisoes.md).

## 1. Visão geral

| Parte | Pasta | O que faz |
|---|---|---|
| Calculadora | `nucleo/` | Recebe os dados da casa e devolve os resultados com o passo a passo |
| Impressora | `documentos/`, `diagrama/`, `redacao/` | Gera Excel, Word, PDF, SVG e DXF a partir dos resultados |
| Balcão | `web/` | Site onde o técnico preenche o formulário |

Os números da norma ficam fora do código, em `data/`.

## 2. Tecnologias

| Parte | Escolha |
|---|---|
| Linguagem | Python 3.11+ |
| Núcleo | Python puro (+ Pydantic a partir da etapa b) |
| Dados normativos | YAML em `data/` |
| Servidor web | FastAPI |
| Telas | HTML + HTMX + Jinja2 + Pico.css |
| Excel / Word / PDF | openpyxl / python-docx / ReportLab |
| Diagrama | SVG gerado por código, ezdxf (DXF), ReportLab (PDF) |
| Banco | SQLite → PostgreSQL (SQLAlchemy + Alembic) |
| Qualidade | pytest, ruff |

## 3. Arquitetura

```
            ┌──────────────────────────────┐
            │ web/  (FastAPI + HTMX)       │  formulário, login, projetos
            └──────────────┬───────────────┘
     ┌─────────────────────┼──────────────────────┐
     ▼                     ▼                      ▼
documentos/           diagrama/              redacao/
(xlsx, docx, pdf)     (svg, dxf, pdf)        (textos explicativos)
     └─────────────────────┼──────────────────────┘
                           ▼  usam só os RESULTADOS
            ┌──────────────────────────────┐
            │ nucleo/  (cálculo puro)      │ ◄── lê data/ (tabelas YAML)
            └──────────────────────────────┘
```

**Princípios**

1. **Nenhum número normativo dentro do código.**
2. **Todo cálculo deixa rastro:** fórmula, valores substituídos, resultado e origem de cada número. Esse rastro vira o memorial de cálculo.
3. **Tabela não validada não passa despercebida.** Um campo `A_VALIDAR` interrompe o cálculo. Um arquivo que não está `VALIDADO` faz os documentos saírem com marca d'água.
4. **O sistema sugere, o técnico decide.** Os ajustes manuais são conferidos e registrados no memorial.
5. **A IA (futura) só redige, nunca calcula.**
6. **Aviso de responsabilidade em todo documento:** capa, rodapé e unifilar.
7. **Texto próprio.** A norma só é citada pelo número do item ou da tabela.
8. **Conteúdo montado uma vez e impresso em vários formatos.** O memorial sai igual em DOCX, PDF e na tela; o unifilar sai igual em SVG, DXF e PDF.

## 4. Modelo de dados

**Entrada**
- **Obra:** nome, endereço, área, tipo de imóvel, concessionária.
- **Cliente** e **responsável técnico** (registro, TRT/ART).
- **Instalação:** sistema de tensão, fases, esquema de aterramento, forma de instalação, isolação, temperatura, eletroduto, distância do medidor ao quadro.
- **Cômodo:** nome, tipo, área, perímetro, distância até o quadro, pontos extras.
- **Equipamento (TUE):** cômodo, potência de placa (W), fator de potência, tensão, quantidade.
- **Trechos de eletroduto** (opcional): comprimento e circuitos.

**Resultado**
- Previsão de pontos por cômodo.
- Circuitos: Ib, fatores, seção por critério, queda de tensão, disjuntor, DR, PE, eletroduto.
- Quadro de cargas, demanda, categoria, alimentador e lista de materiais.
- Memória de cálculo e avisos.
- Registro da versão e situação de cada tabela usada.

**Banco (etapa g)**
- `usuarios`, `projetos`.
- `revisoes`: entrada, resultado, versão do sistema e versão das tabelas.
- `documentos`.

## 5. Sequência do cálculo

```
Entrada → 1 Previsão de cargas → 2 Divisão em circuitos → 3 Balanceamento
        → 4 Carga instalada, demanda e categoria (concessionária)
        → 5 Por circuito: Ib → disjuntor ↔ seção (3 critérios + coordenação)
        → 6 DR, DPS, PE → 7 Alimentador e proteção geral
        → 8 Eletrodutos → 9 Lista de materiais → Resultado + memória de cálculo
```

## 6. Etapas

| Etapa | Entrega | Situação |
|---|---|---|
| **a** | Estrutura, arquivos de dados, leitor/validador, `verificar-dados`, README, CLAUDE.md | ✅ concluída |
| **b1** | Modelos de entrada/saída e memória de cálculo (passos) | pendente |
| **b2** | Previsão de cargas | pendente |
| **b3** | Divisão de circuitos e balanceamento de fases | pendente |
| **b4** | Carga instalada, demanda e categoria (Energisa MS) | pendente |
| **b5** | Condutores: capacidade, queda de tensão, seção mínima, coordenação | pendente |
| **b6** | Proteção: disjuntor, DR, DPS, condutor de proteção | pendente |
| **b7** | Eletrodutos e lista de materiais | pendente |
| **b8** | Projeto completo + casa exemplo + comando `gerar` | pendente |
| **c** | Quadro de cargas em Excel | pendente |
| **d** | Memoriais de cálculo e descritivo (Word/PDF), capa e rodapé | pendente |
| **e** | Diagrama unifilar (SVG/PDF/DXF) | pendente |
| **f** | Interface web responsiva | pendente |
| **g** | Usuários, projetos salvos e revisões | pendente |

Cada etapa termina com: testes rodados, explicação simples e lista do que o
responsável técnico precisa conferir.

## 7. Testes

- **Lógica:** tabelas fictícias com números redondos, em `tests/fixtures/tabelas_ficticias/`, e a conta à mão em comentário.
- **Estrutura dos dados reais:** garante que o preenchimento não quebrou nada.
- **Casos de referência:** com as tabelas reais; ligam sozinhos quando `data/` estiver preenchida.
- **Documentos:** conferência do conteúdo dos arquivos gerados.

## 8. Fora do MVP

Planta baixa, outras concessionárias, redação pela API do Claude, curto-circuito
e impedância de laço (D11), SPDA, edifícios com várias unidades, cobrança,
assinatura digital, hospedagem.
