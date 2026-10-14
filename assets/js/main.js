// =========================================================
// CONFIGURAÇÃO — edite aqui
// =========================================================
const CONFIG = {
  // Número do WhatsApp só com dígitos: 55 (Brasil) + DDD + número.
  // Exemplo: (11) 98765-4321 vira '5511987654321'
  whatsapp: '5500000000000',
  // Mensagem que já aparece escrita quando a pessoa clica nos botões do WhatsApp
  mensagemPadrao: 'Olá! Encontrei seu site e gostaria de mais informações.'
};

function linkWhatsApp(mensagem) {
  return `https://wa.me/${CONFIG.whatsapp}?text=${encodeURIComponent(mensagem)}`;
}

// Todos os links com o atributo data-whatsapp passam a abrir o WhatsApp
document.querySelectorAll('[data-whatsapp]').forEach((link) => {
  link.href = linkWhatsApp(link.dataset.whatsapp || CONFIG.mensagemPadrao);
  link.target = '_blank';
  link.rel = 'noopener';
});

// =========================================================
// MENU DO CELULAR
// =========================================================
const menuBotao = document.getElementById('menu-botao');
const menu = document.getElementById('menu');

function definirMenu(aberto) {
  menu.classList.toggle('menu--aberto', aberto);
  menuBotao.setAttribute('aria-expanded', String(aberto));
  menuBotao.setAttribute('aria-label', aberto ? 'Fechar menu' : 'Abrir menu');
}

menuBotao.addEventListener('click', () => {
  definirMenu(menuBotao.getAttribute('aria-expanded') !== 'true');
});

menu.querySelectorAll('a').forEach((link) => {
  link.addEventListener('click', () => definirMenu(false));
});

document.addEventListener('keydown', (evento) => {
  if (evento.key === 'Escape') definirMenu(false);
});

// =========================================================
// CABEÇALHO: sombra ao rolar e destaque da seção atual no menu
// =========================================================
const cabecalho = document.getElementById('cabecalho');

function atualizarCabecalho() {
  cabecalho.classList.toggle('cabecalho--rolado', window.scrollY > 8);
}

window.addEventListener('scroll', atualizarCabecalho, { passive: true });
atualizarCabecalho();

const linksMenu = menu.querySelectorAll('a[href^="#"]');
const observador = new IntersectionObserver((entradas) => {
  entradas.forEach((entrada) => {
    if (!entrada.isIntersecting) return;
    linksMenu.forEach((link) => {
      link.classList.toggle('ativo', link.getAttribute('href') === `#${entrada.target.id}`);
    });
  });
}, { rootMargin: '-45% 0px -50% 0px' });

document.querySelectorAll('main section[id]').forEach((secao) => observador.observe(secao));

// =========================================================
// FORMULÁRIO DE CONTATO → abre o WhatsApp com a mensagem pronta
// =========================================================
const formulario = document.getElementById('formulario-contato');

formulario.addEventListener('submit', (evento) => {
  evento.preventDefault();
  const dados = new FormData(formulario);
  const mensagem =
    `Olá! Meu nome é ${dados.get('nome').trim()}.\n` +
    `Assunto: ${dados.get('assunto')}\n\n` +
    dados.get('mensagem').trim();
  window.open(linkWhatsApp(mensagem), '_blank', 'noopener');
});

// =========================================================
// ANO ATUAL NO RODAPÉ
// =========================================================
document.getElementById('ano-atual').textContent = new Date().getFullYear();
