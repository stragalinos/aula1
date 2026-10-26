#!/bin/bash
# Painel do Investidor: dois cliques para abrir no Mac.
cd "$(dirname "$0")"
if ! command -v node >/dev/null 2>&1; then
  echo ""
  echo "Para abrir o painel no computador, instale antes o Node.js (gratuito)."
  echo "Vou abrir a página de download: escolha a versão LTS, instale e abra este arquivo de novo."
  open "https://nodejs.org/pt-br/download"
  read -r -p "Pressione Enter para fechar."
  exit 1
fi
node local/servidor.js
