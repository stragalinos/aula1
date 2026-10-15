# Site de advocacia

Site institucional de uma página para a advogada: apresentação, áreas de atuação, como
funciona o atendimento, perguntas frequentes e contato pelo WhatsApp.

Feito só com HTML, CSS e JavaScript, sem nada para instalar. Pode ser hospedado em qualquer
lugar (GitHub Pages, Netlify, Cloudflare Pages, hospedagem comum) e ligado ao domínio
comprado no Registro.br.

## Estrutura

```
index.html            → todo o conteúdo do site (textos, seções, menu)
assets/
  css/style.css       → visual: cores, fontes, espaçamentos
  js/main.js          → número do WhatsApp, menu do celular, formulário
  img/                → favicon, logo e foto dela
robots.txt            → orienta o Google (trocar o domínio)
sitemap.xml           → lista de páginas para o Google (trocar o domínio)
```

A pasta `Aula1/` é da aula anterior e não faz parte do site.

## Como ver o site no computador

Abra o arquivo `index.html` com dois cliques no navegador. Ou, num terminal, na pasta do
projeto:

```
npx serve .
```

e acesse o endereço que aparecer (normalmente http://localhost:3000).

## O que trocar antes de publicar

Nome, OAB/SP, cidade e WhatsApp já estão preenchidos. No `index.html`, o que ainda falta
está marcado com o comentário `EDITAR`:

| Procure por                  | Troque por                                   |
| ---------------------------- | -------------------------------------------- |
| `www.seudominio.com.br`      | domínio comprado (também em `robots.txt` e `sitemap.xml`) |
| `Universidade Exemplo`       | formação dela (graduação, pós, cursos)       |
| `Aqui vai um pouco da sua trajetória` | texto de apresentação dela          |
| `Segunda a sexta`            | horário de atendimento real                  |
| `contato@seudominio.com.br`, `seuperfil` | e-mail e redes sociais (estão comentados; preencha e descomente) |

E também:

- **WhatsApp dos botões:** em `assets/js/main.js`, no campo `whatsapp`
  (55 + DDD + número, só dígitos). Todos os botões e o formulário usam esse número.
- **Foto:** fica em `assets/img/foto.jpg` e aparece redonda na seção "Sobre". Para trocar,
  substitua o arquivo por outra imagem quadrada com o mesmo nome.
- **Áreas de atuação:** cada área é um bloco `<article class="area">`. Copie um bloco
  para adicionar, apague para remover. Lembre de ajustar também as opções do campo
  "Assunto" no formulário de contato.
- **Cores:** ficam no topo de `assets/css/style.css`, nas variáveis `--cor-...`.

## Regras da OAB para sites (Provimento 205/2021)

A publicidade na advocacia deve ser informativa, discreta e sóbria. Ao escrever os textos,
evitar:

- mencionar valores de honorários, formas de pagamento, gratuidade ou descontos;
- chamar-se de **especialista** em uma área sem ter título de especialização
  (pós-graduação) nela — sem título, use "atuação em";
- expressões de autoengrandecimento ou comparação ("a melhor", "a mais experiente");
- promessas de resultado ("ganhe sua causa");
- citar nomes de clientes ou publicar depoimentos de clientes.

O nome e o número da OAB devem aparecer no site (já estão no cabeçalho, no "Sobre" e no
rodapé). Vale conferir o texto oficial do provimento e as orientações da seccional dela.

## Publicar e ligar o domínio do Registro.br

Uma opção gratuita é o **GitHub Pages**:

1. No GitHub, abra o repositório → **Settings → Pages**.
2. Em **Source**, escolha **Deploy from a branch**, a branch principal e a pasta `/ (root)`.
3. Em **Custom domain**, digite o domínio (ex.: `www.seudominio.com.br`) e salve.
4. No painel do Registro.br, na zona de DNS do domínio, crie:
   - um registro **CNAME**: `www` → `stragalinos.github.io`
   - quatro registros **A** para o domínio sem `www`:
     `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
5. Depois que o DNS propagar (pode levar algumas horas), marque **Enforce HTTPS** no GitHub.

Dica: além do `.com.br`, o Registro.br oferece a categoria `.adv.br`, voltada a advogados.
Confira as regras dessa categoria no próprio site do Registro.br.

## Próximas ideias

- Imagem de capa para compartilhamento (`og:image`)
- Mapa do escritório (Google Maps incorporado)
- Página de artigos/blog com conteúdo jurídico informativo
- Cadastro no Perfil da Empresa no Google (Google Meu Negócio)
- Política de privacidade, se no futuro o site passar a coletar dados
