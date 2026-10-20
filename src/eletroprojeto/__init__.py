"""eletroprojeto: ferramenta de apoio para projetos elétricos residenciais de baixa tensão.

Todo projeto gerado precisa ser revisado e assinado por profissional habilitado (TRT/ART).

Camadas (as dependências só "descem"):
    web/          interface (formulário, login, projetos salvos)
    documentos/   planilha, memoriais (Word/PDF)
    diagrama/     diagrama unifilar (SVG/DXF/PDF)
    redacao/      textos explicativos dos memoriais
    nucleo/       cálculo puro: não conhece nenhuma das camadas acima
"""

__version__ = "0.1.0"
