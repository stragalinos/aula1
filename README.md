# eletroprojeto

Ferramenta de apoio para técnicos e eletricistas elaborarem projetos elétricos
residenciais de baixa tensão conforme a ABNT NBR 5410.

> **Aviso:** este sistema é uma ferramenta de apoio. Todo projeto gerado precisa
> ser revisado e assinado por profissional habilitado, com TRT (CFT) ou ART (CREA).

## Situação atual

**Etapa (a) concluída:** estrutura do projeto, arquivos das tabelas em `data/`
(a preencher) e o comando que confere esses arquivos. O sistema **ainda não
calcula projetos**; o núcleo de cálculo é a próxima etapa.

O plano completo está em [`docs/PLANO.md`](docs/PLANO.md) e as decisões técnicas
em [`docs/decisoes.md`](docs/decisoes.md).

## Instalação

É preciso ter o **Python 3.11 ou mais novo**.

### Windows (PowerShell)

1. Instale o Python pelo site python.org e marque a opção **"Add python.exe to PATH"**.
2. Abra o PowerShell na pasta do projeto e rode:
   ```powershell
   py -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -e ".[dev]"
   ```
   Se o PowerShell bloquear a ativação, rode uma vez
   `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` e tente de novo.

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Depois de instalar, sempre que abrir um terminal novo **ative o ambiente**
(`.venv\Scripts\Activate.ps1` no Windows ou `source .venv/bin/activate` no Linux/macOS).

## Comandos

| O que fazer | Comando |
|---|---|
| Rodar todos os testes | `pytest` |
| Conferir os arquivos de `data/` | `python -m eletroprojeto verificar-dados` |
| Ver cada valor que falta preencher | `python -m eletroprojeto verificar-dados --detalhes` |
| Conferir o padrão do código | `ruff check .` e `ruff format --check .` |

## Preenchendo as tabelas

Os valores da NBR 5410, dos catálogos e da concessionária **não estão no código**.
Ficam em arquivos YAML na pasta `data/`, hoje marcados como `A_VALIDAR`. O guia
de preenchimento está em [`data/LEIA-ME.md`](data/LEIA-ME.md).

## Estrutura de pastas

```
data/                  tabelas a preencher e validar (NBR 5410, catálogos, concessionárias)
docs/                  plano e registro de decisões técnicas
src/eletroprojeto/
  nucleo/              cálculo puro (não depende de interface nem de documentos)
  redacao/             textos explicativos dos memoriais          (etapa d)
  documentos/          planilha e memoriais Word/PDF              (etapas c e d)
  diagrama/            diagrama unifilar SVG/DXF/PDF              (etapa e)
  web/                 site, login e projetos salvos              (etapas f e g)
  cli.py               comandos de terminal
tests/                 testes automáticos (pytest)
  fixtures/            tabelas FICTÍCIAS, só para testar a lógica
```

## Regras do projeto

Estão resumidas em [`CLAUDE.md`](CLAUDE.md). As principais:
- nenhum valor normativo no código;
- nenhum texto copiado das normas;
- todo cálculo testado e com o passo a passo registrado;
- todo texto em português do Brasil.
