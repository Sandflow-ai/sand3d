// Drawer on a phone, and the current section lit in the menus.
const body = document.body, burger = document.getElementById('burger'), scrim = document.getElementById('scrim');
function menu(open) { body.classList.toggle('menu', open); if (burger) burger.setAttribute('aria-expanded', open); }
if (burger) burger.addEventListener('click', () => menu(!body.classList.contains('menu')));
if (scrim) scrim.addEventListener('click', () => menu(false));
document.addEventListener('keydown', e => { if (e.key === 'Escape') menu(false); });
document.querySelectorAll('.side a[href^="#"], .toc-m a').forEach(a => a.addEventListener('click', () => {
  menu(false); const d = a.closest('details'); if (d) d.open = false; }));
const heads = [...document.querySelectorAll('main.doc h2[id]')];
const links = [...document.querySelectorAll('.side .subs a, .toc a')];
function light() {
  let cur = heads[0];
  for (const h of heads) if (h.getBoundingClientRect().top < 140) cur = h;
  if (cur) links.forEach(a => a.classList.toggle('act', a.getAttribute('href') === '#' + cur.id));
}
if (heads.length) { addEventListener('scroll', light, {passive: true}); light(); }
