'use strict';
/*
 * Labels for glycerol stocks and primers, each with a QR code that opens the
 * record. /labels?codes=S-0001,P-0003 ; print from the browser.
 */

const SB = window.ST;
const KIND = { G: 'glycerol', O: 'primer', C: 'chemical', A: 'antibody', M: 'material' };
const PATH = { glycerol: 'glycerol', primer: 'primers', chemical: 'chemicals', antibody: 'antibodies', material: 'material' };
// GL-G-0001, GL-O-0001: the letter before the number says what it is.
const kindOf = (code) => KIND[code.split('-').slice(-2, -1)[0]];

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') node.className = v; else node.setAttribute(k, v);
  }
  for (const c of children.flat()) if (c !== null && c !== undefined && c !== false && c !== '') node.append(c);
  return node;
}

/** Where a phone reaches the suite: the address set for it, or the one this page is open at. */
function publicBase() {
  return `${ST.public || location.origin}${ST.base}`;
}

function qr(text) {
  const code = qrcode(0, 'M');
  code.addData(text);
  code.make();
  const holder = el('div', { class: 'qr' });
  holder.innerHTML = code.createSvgTag({ cellSize: 2, margin: 0, scalable: true });   // made here, from our own URL
  return holder;
}

function label(rec) {
  const target = `${publicBase()}/#${rec.kind}=${rec.code}`;
  const lines = {
    glycerol: () => [`${rec.plasmid_name}${rec.clone ? ` clone ${rec.clone}` : ''}`, [rec.host, rec.selection].filter(Boolean).join(' · '),
      [rec.made_on, rec.location].filter(Boolean).join(' · ')],
    primer: () => [rec.name, `${rec.mod5 ? `[${rec.mod5}]` : ''}${rec.sequence}${rec.mod3 ? `[${rec.mod3}]` : ''}`,
      [`${rec.length} nt`, rec.tm !== null ? `Tm ${rec.tm} °C` : '', rec.location].filter(Boolean).join(' · ')],
    chemical: () => [rec.name, rec.cas ? `CAS ${rec.cas}` : '', [rec.size, rec.room].filter(Boolean).join(' · ')],
    antibody: () => [[rec.short_code, rec.type].filter(Boolean).join(' · '), rec.description,
      [rec.host && `raised in ${rec.host}`, rec.producer, rec.product_number].filter(Boolean).join(' · ')],
    material: () => [rec.name, [rec.tissue, rec.species || rec.from_plant].filter(Boolean).join(' · '),
      [rec.collected_on, rec.experiment].filter(Boolean).join(' · ')],
  }[rec.kind]();
  return el('div', { class: `label label-${rec.kind}` }, qr(target),
    el('div', { class: 'label-text' }, el('div', { class: 'label-code' }, rec.code),
      lines.filter(Boolean).map((t) => el('div', { class: 'label-line' }, t))));
}

async function main() {
  const codes = (new URLSearchParams(location.search).get('codes') || '').split(',').map((c) => c.trim().toUpperCase()).filter(Boolean);
  const sheet = document.getElementById('sheet');
  const help = document.getElementById('labelsHelp');
  const host = new URL(publicBase()).hostname;
  help.textContent = `${codes.length} label${codes.length === 1 ? '' : 's'}. The codes open ${publicBase()}/ on a phone.`
    + (['localhost', '127.0.0.1', '::1'].includes(host)
      ? ' This is this computer\'s own address, which phones cannot reach: open this page through the server\'s name (e.g. http://UU115629:8080), or set SUITE_PUBLIC_URL for the suite.' : '');
  for (const code of codes) {
    const kind = kindOf(code);
    if (!kind) continue;
    try {
      const res = await fetch(`${ST.base}/api/${PATH[kind]}/${encodeURIComponent(code)}`, { credentials: 'same-origin' });
      const data = await res.json();
      sheet.append(res.ok ? label(data.record) : el('div', { class: 'label label-missing' }, `${code}: ${data.error || 'not found'}`));
    } catch (err) {
      sheet.append(el('div', { class: 'label label-missing' }, `${code}: ${err.message}`));
    }
  }
  const size = document.getElementById('labelSize');
  const apply = () => { sheet.className = `label-sheet size-${size.value}`; };
  size.addEventListener('change', apply);
  apply();
}

document.addEventListener('DOMContentLoaded', main);
