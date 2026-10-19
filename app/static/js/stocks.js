'use strict';
/*
 * The Lab Stocks page: glycerol stocks, primers, chemicals and antibodies, a list
 * of each and a page for each record. Addresses: #glycerol, #primers, #chemicals,
 * #antibodies, #glycerol=GL-G-0001, #primer=GL-O-0001, #chemical=GL-C-0001,
 * #antibody=GL-A-0001; and the order list, #orders.
 */

const ST = window.ST;
const url = (path) => `${ST.base}${path}`;

/* --- helpers (as in the Seed Bank) ----------------------------------------------- */

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'style') node.setAttribute('style', value);
    else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2), value);
    else if (key in node && typeof value !== 'string') node[key] = value;
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function put(node, ...children) {
  node.replaceChildren(...children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false)
    .map((c) => (c instanceof Node ? c : document.createTextNode(String(c)))));
  return node;
}

async function api(method, path, body, form) {
  const res = await fetch(url(`/api${path}`), {
    method, credentials: 'same-origin',
    headers: form || body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: form || (body === undefined ? undefined : JSON.stringify(body)),
  });
  let data = {};
  try { data = await res.json(); } catch (e) { /* not JSON */ }
  if (!res.ok) {
    const err = new Error(data.error || (res.status === 413 ? 'Too large to send at once' : `${res.status} ${res.statusText}`));
    err.status = res.status;
    throw err;
  }
  return data;
}

/**
 * Copy text to the clipboard; resolves true when it was copied. Browsers give
 * pages the clipboard API only over https (or on localhost), so elsewhere, a
 * suite reached over plain http say, it copies a selected text field with the
 * copy command instead, which still works while handling a click.
 */
async function copyText(text) {
  if (window.isSecureContext && navigator.clipboard) {
    try { await navigator.clipboard.writeText(text); return true; } catch (e) { /* refused: try the other way */ }
  }
  const field = document.createElement('textarea');
  field.value = text;
  field.setAttribute('readonly', '');
  field.style.position = 'fixed';
  field.style.opacity = '0';
  document.body.append(field);
  field.select();
  let copied = false;
  try { copied = document.execCommand('copy'); } catch (e) { copied = false; }
  field.remove();
  return copied;
}

function toast(message, kind = 'info', ms = 3500) {
  const box = el('div', { class: `toast toast-${kind}` }, message);
  document.getElementById('toasts').append(box);
  setTimeout(() => box.remove(), ms);
}

function modal({ title, build, buttons = [{ label: 'Close', kind: 'secondary' }], wide = false, onClose }) {
  const body = el('div', { class: 'modal-body' });
  const backdrop = el('div', { class: 'modal-backdrop' });
  let closed = false;
  const close = () => { if (closed) return; closed = true; backdrop.remove(); onClose?.(); };
  const foot = el('div', { class: 'modal-foot' }, buttons.map((b) => el('button', {
    class: `btn ${b.kind === 'secondary' ? 'btn-secondary' : b.kind === 'danger' ? 'btn-danger' : 'btn-primary'}`,
    type: 'button',
    onclick: async (ev) => {
      const btn = ev.currentTarget;
      btn.disabled = true;
      try {
        const keep = await b.onClick?.({ close, body });
        if (keep !== false) close();
      } catch (err) {
        toast(err.message, 'error', 6000);
      } finally {
        btn.disabled = false;
      }
    },
  }, b.label)));
  backdrop.append(el('div', { class: `modal ${wide ? 'modal-wide' : ''}`, role: 'dialog' },
    el('div', { class: 'modal-head' }, el('span', { class: 'modal-title', text: title }),
      el('button', { class: 'icon-btn', title: 'Close', onclick: close }, '✕')),
    body, foot));
  backdrop.addEventListener('mousedown', (e) => { if (e.target === backdrop) close(); });
  document.body.append(backdrop);
  build?.(body, close);
  return { close, body };
}

/**
 * A dialog with a form. fields: [{name, label, type, value, options, placeholder, hint}].
 * submit(values) runs on the main button; returning false keeps the dialog open.
 */
function formModal({ title, intro, fields, submit, label = 'Save', wide = false }) {
  const inputs = {};
  modal({
    title, wide,
    build: (body) => {
      if (intro) body.append(el('p', { class: 'hint' }, intro));
      for (const f of fields) {
        let input;
        if (f.type === 'select') {
          input = el('select', {}, f.options.map((o) => {
            const [value, text] = Array.isArray(o) ? o : [o, o || '—'];
            return el('option', { value, selected: String(f.value ?? '') === String(value) }, text);
          }));
        } else if (f.type === 'textarea') {
          input = el('textarea', { rows: 3, placeholder: f.placeholder || '' });
          input.value = f.value ?? '';
        } else if (f.type === 'checkbox') {
          input = el('input', { type: 'checkbox', checked: !!f.value });
        } else {
          input = el('input', { type: f.type || 'text', placeholder: f.placeholder || '', list: f.list || null });
          input.value = f.value ?? '';
          if (f.min !== undefined) input.min = f.min;
          if (f.max !== undefined) input.max = f.max;
          if (f.step !== undefined) input.step = f.step;
        }
        inputs[f.name] = input;
        body.append(el('label', { class: `field ${f.type === 'checkbox' ? 'field-check' : ''}` },
          el('span', { class: 'field-label' }, f.label), input, f.hint ? el('span', { class: 'hint' }, f.hint) : null));
      }
      setTimeout(() => body.querySelector('input, select, textarea')?.focus(), 0);
    },
    buttons: [{ label: 'Cancel', kind: 'secondary' }, {
      label,
      onClick: async () => {
        const values = {};
        for (const [k, input] of Object.entries(inputs)) values[k] = input.type === 'checkbox' ? input.checked : input.value.trim();
        return submit(values);
      },
    }],
  });
}

/** Search-as-you-type list in a dialog; resolves with the item chosen, or null. */
function picker({ title, placeholder, search, describe }) {
  return new Promise((resolve) => {
    let chosen = null;
    modal({
      title,
      onClose: () => resolve(chosen),
      build: (body, close) => {
        const input = el('input', { type: 'search', class: 'picker-input', placeholder });
        const list = el('ul', { class: 'picker-list' });
        let ticket = 0;
        const run = async () => {
          const mine = ++ticket;
          let items = [];
          try { items = await search(input.value.trim()); } catch (err) { toast(err.message, 'error'); }
          if (mine !== ticket) return;
          put(list, items.length ? items.map((item) => el('li', {
            class: 'picker-item', tabindex: '0',
            onclick: () => { chosen = item; close(); },
            onkeydown: (e) => { if (e.key === 'Enter') { chosen = item; close(); } },
          }, describe(item))) : el('li', { class: 'hint' }, 'Nothing found'));
        };
        input.addEventListener('input', run);
        body.append(input, list);
        setTimeout(() => input.focus(), 0);
        run();
      },
      buttons: [{ label: 'Cancel', kind: 'secondary' }],
    });
  });
}

function localTime(stamp) {
  if (!stamp) return '';
  const d = new Date(String(stamp).replace(' ', 'T') + (/[zZ]|[+-]\d\d:?\d\d$/.test(stamp) ? '' : 'Z'));
  if (Number.isNaN(d.getTime())) return String(stamp).slice(0, 16);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}


const today = () => new Date().toISOString().slice(0, 10);
const ICON = { glycerol: '🧫', primer: '🧬', chemical: '⚗️', antibody: '🔬' };
const NAME = { glycerol: 'glycerol stock', primer: 'primer', chemical: 'chemical', antibody: 'antibody' };
const NAMES = { glycerol: 'glycerol stocks', primer: 'primers', chemical: 'chemicals', antibody: 'antibodies' };
const PLURAL = { glycerol: 'glycerol', primer: 'primers', chemical: 'chemicals', antibody: 'antibodies' };
const SINGULAR = { glycerol: 'glycerol', primers: 'primer', chemicals: 'chemical', antibodies: 'antibody' };
const TITLE = { glycerol: '🧫 Glycerol stocks', primer: '🧬 Primers', chemical: '⚗️ Chemicals', antibody: '🔬 Antibodies' };
const SDS = 'SDS';
const FILE_ICONS = { pdf: '📕', word: '📝', powerpoint: '📽️', excel: '📊', archive: '🗜️', sequence: '🧬', text: '📄', image: '🖼️', file: '📎' };
const fileUrl = (id, download = false) => url(`/api/attachments/${encodeURIComponent(id)}${download ? '?download' : ''}`);
const sizeLabel = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} kB`);
const editorOpen = (id) => `${ST.editor}/editor?open=${encodeURIComponent(id)}`;
const COMPLEMENT = { A: 'T', T: 'A', G: 'C', C: 'G', R: 'Y', Y: 'R', S: 'S', W: 'W', K: 'M', M: 'K', B: 'V', V: 'B', D: 'H', H: 'D', N: 'N' };
const revcomp = (s) => [...s].reverse().map((c) => COMPLEMENT[c] || c).join('');
const HOSTS = ['DH5α', 'DH10B', 'TOP10', 'DB3.1', 'ccdB Survival 2', 'BL21(DE3)', 'Agrobacterium GV3101', 'Agrobacterium AGL1', 'Agrobacterium C58C1'];

const App = {
  selected: new Set(),

  async init() {
    try {
      this.meta = await api('GET', '/me');
      this.labPicker(this.meta.lab.labs);
      await this.loadLab();
      this.showWaiting(this.meta.orders.waiting);
    } catch (err) {
      put(document.getElementById('main'), el('p', { class: 'empty' }, err.message));
      return;
    }
    document.body.append(el('datalist', { id: 'hosts' }, HOSTS.map((h) => el('option', { value: h }))));
    window.addEventListener('hashchange', () => this.route());
    this.route();
  },

  /**
   * Someone in several labs chooses which one new records go to (their first,
   * until they choose; remembered on this computer). They see all their labs' records.
   */
  chosenLab: null,
  labPicker(labs) {
    if (!labs || labs.length < 2) return;
    let kept = null;
    try { kept = localStorage.getItem('labChoice'); } catch (e) { /* private window */ }
    this.chosenLab = labs.includes(kept) ? kept : labs[0];
    const picker = el('select', { class: 'lab-picker', title: 'New records go to this lab; you see the records of all your labs',
      'aria-label': 'Lab for new records', onchange: async (e) => {
        this.chosenLab = e.target.value;
        try { localStorage.setItem('labChoice', this.chosenLab); } catch (e) { /* private window */ }
        await this.loadLab();
        this.route();
      } }, labs.map((l) => el('option', { value: l, selected: l === this.chosenLab }, l)));
    document.querySelector('.topbar-user')?.before(el('label', { class: 'lab-pick' }, 'New in ', picker));
  },

  /** The chosen lab's code, for the line above the lists. */
  async loadLab() {
    if (this.chosenLab) this.meta.lab = await api('GET', `/lab?lab=${encodeURIComponent(this.chosenLab)}`);
  },

  route() {
    const hash = location.hash.slice(1) || 'glycerol';
    const record = hash.match(/^(glycerol|primer|chemical|antibody)=(.+)$/);
    for (const tab of document.querySelectorAll('.view-tab')) {
      tab.classList.toggle('active', tab.dataset.view === (record ? PLURAL[record[1]] : hash));
    }
    if (record) this.showRecord(record[1], decodeURIComponent(record[2]));
    else if (hash === 'orders') this.showOrders();
    else this.showList(SINGULAR[hash] || 'glycerol');
  },

  /* lists -------------------------------------------------------------------------- */

  labCodeLine() {
    const lab = this.meta.lab;
    return el('p', { class: 'lab-code-line' },
      'Codes in ', el('b', {}, lab.lab.startsWith('user:') ? 'your own stocks' : lab.lab), ' start with ',
      el('span', { class: 'code-badge' }, `${lab.code}-`), ` (${lab.code}-G glycerol stocks, ${lab.code}-O primers, ${lab.code}-C chemicals, ${lab.code}-A antibodies)`,
      lab.can_change ? el('button', { class: 'btn btn-secondary btn-sm', style: 'margin-left:.6rem', onclick: () => formModal({
        title: 'Choose the lab code',
        intro: 'Every code your lab makes starts with it. Keep it the same as in the Seed Bank. It can be chosen until the lab\'s first stock; after that it is fixed, as codes on labels never change.',
        fields: [{ name: 'code', label: 'Lab code', value: lab.code }],
        submit: async (v) => { this.meta.lab = await api('PUT', '/lab', { ...v, lab: lab.lab }); this.route(); },
      }) }, 'Change…') : null);
  },

  async showList(kind) {
    const main = document.getElementById('main');
    const query = el('input', { type: 'search', class: 'list-search', value: this[`q_${kind}`] || '',
      placeholder: {
        glycerol: 'Search by code, plasmid, clone, strain, selection or place',
        primer: 'Search by code, name, target, place, or a piece of the sequence (e.g. GGCCAGT)',
        chemical: 'Search by code, name, CAS number, room or size',
        antibody: 'Search by code, short code, description, producer, animal, product number or notes',
      }[kind] });
    const table = el('div', { class: 'list' });
    const labelBtn = el('button', { class: 'btn btn-secondary', onclick: () => this.openLabels([...this.selected]) }, '🏷 Labels for selected');
    this.onSelection = () => { labelBtn.disabled = !this.selected.size; labelBtn.textContent = `🏷 Labels for selected${this.selected.size ? ` (${this.selected.size})` : ''}`; };
    const draw = async () => {
      this[`q_${kind}`] = query.value;
      const data = await api('GET', `/${PLURAL[kind]}?q=${encodeURIComponent(query.value)}`);
      put(table, this.listTable(kind, data[PLURAL[kind]]));
    };
    let timer;
    query.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(draw, 250); });
    put(main,
      el('div', { class: 'page-head' }, el('h1', {}, TITLE[kind]),
        el('span', { class: 'actions' },
          el('button', { class: 'btn btn-primary', onclick: () => ({ glycerol: () => this.newGlycerol(), primer: () => this.editPrimer(),
            chemical: () => this.editChemical(), antibody: () => this.editAntibody() })[kind]() },
          { glycerol: '＋ Glycerol stock', primer: '＋ Primer', chemical: '＋ Chemical', antibody: '＋ Antibody' }[kind]), labelBtn)),
      this.labCodeLine(),
      el('p', { class: 'hint' }, {
        glycerol: 'Frozen cultures of the lab\'s plasmids. Confirming a plasmid by sequencing in the Plasmid Editor makes its glycerol stock here, with the next number.',
        primer: 'The lab\'s oligos, with where each tube is. Primers designed in the Plasmid Editor can be saved here, and the editor shows which of them bind a plasmid.',
        chemical: 'The lab\'s chemicals, with the room each is kept in. Open one to add its safety data sheet (SDS).',
        antibody: 'The lab\'s antibodies: primary and secondary, who makes each, the animal it is raised in, and how to use it.',
      }[kind], kind === 'chemical' ? this.safetyLinks() : null),
      query, table);
    await draw();
    this.onSelection();
    query.focus();
  },

  pick(code) {
    return el('input', { type: 'checkbox', checked: this.selected.has(code), title: 'Choose for labels',
      onclick: (e) => e.stopPropagation(),
      onchange: (e) => { if (e.target.checked) this.selected.add(code); else this.selected.delete(code); this.onSelection?.(); } });
  },

  listTable(kind, rows) {
    if (!rows.length) return el('p', { class: 'empty' }, 'Nothing here yet.');
    const head = {
      glycerol: ['', 'Code', 'Plasmid', 'Clone', 'Strain', 'Selection', 'Kept in', 'Made', 'Status'],
      primer: ['', 'Code', 'Name', 'Sequence (5′→3′)', 'nt', 'Tm', 'Kept in', 'Status'],
      chemical: ['', 'Code', 'Name', 'CAS number', 'Room', 'Size', 'SDS', 'Out'],
      antibody: ['', 'Code', 'Short code', 'Description', 'Type', 'Producer', 'Source animal', 'Product number', 'Notes about the use', 'Status'],
    }[kind];
    const cells = {
      glycerol: (r) => [r.plasmid_name, r.clone, r.host, r.selection, r.location, r.made_on || (r.created_at || '').slice(0, 10),
        r.source === 'sequencing' ? `${r.status} ✓` : r.status],
      primer: (r) => [r.name, el('span', { class: 'mono' }, r.sequence), r.length, r.tm !== null ? `${r.tm} °C` : '', r.location, r.status],
      chemical: (r) => [r.name, el('span', { class: 'mono' }, r.cas), r.room, r.size,
        r.has_sds ? el('span', { title: 'Has its safety data sheet' }, '📕') : el('span', { class: 'hint', title: 'No safety data sheet yet' }, '—'),
        r.status === 'discarded' ? 'discarded' : this.outToggle(r)],
      antibody: (r) => [el('b', {}, r.short_code), r.description, r.type, r.producer, r.host, el('span', { class: 'mono' }, r.product_number),
        el('span', { class: 'clip', title: r.notes }, r.notes), r.status],
    }[kind];
    return el('table', { class: 'data' },
      el('thead', {}, el('tr', {}, head.map((h) => el('th', {}, h)))),
      el('tbody', {}, rows.map((r) => el('tr', { class: `clickable ${r.status !== 'in stock' ? 'faded' : ''}`, onclick: () => { location.hash = `${kind}=${r.code}`; } },
        el('td', { class: 'pick' }, this.pick(r.code)), el('td', { class: 'code' }, r.code), cells(r).map((c) => el('td', {}, c))))));
  },

  openLabels(codes) {
    if (!codes.length) { toast('Tick the stocks to print labels for', 'error'); return; }
    window.open(url(`/labels?codes=${encodeURIComponent(codes.join(','))}`), '_blank', 'noopener');
  },

  /* records ------------------------------------------------------------------------ */

  async showRecord(kind, code) {
    const main = document.getElementById('main');
    let rec;
    try {
      rec = (await api('GET', `/${PLURAL[kind]}/${encodeURIComponent(code)}`)).record;
    } catch (err) {
      put(main, el('p', { class: 'empty' }, err.message), el('a', { href: `#${PLURAL[kind]}` }, `All ${NAME[kind]}s`));
      return;
    }
    this.rec = rec;
    put(main, { glycerol: () => this.glycerolView(rec), primer: () => this.primerView(rec), chemical: () => this.chemicalView(rec),
      antibody: () => this.antibodyView(rec) }[kind](),
      this.files(rec), this.mentions(rec), this.history(rec));
  },

  reload() { this.showRecord(this.rec.kind, this.rec.code); },

  head(rec, title, subtitle, actions) {
    return el('div', { class: 'record-head' },
      el('div', {}, el('div', { class: 'crumbs' }, el('a', { href: `#${PLURAL[rec.kind]}` }, `${ICON[rec.kind]} All ${NAMES[rec.kind]}`)),
        el('h1', {}, el('span', { class: 'code-badge' }, rec.code), ' ', title),
        subtitle ? el('div', { class: 'hint' }, subtitle) : null, this.onOrder(rec)),
      el('span', { class: 'actions' }, actions,
        rec.kind === 'glycerol' ? null : el('button', { class: 'btn btn-secondary', title: 'Put it on the lab\'s order list, with its details',
          onclick: () => this.orderStock(rec) }, '🛒 Add to order'),
        el('button', { class: 'btn btn-secondary', onclick: () => this.openLabels([rec.code]) }, '🏷 Label'),
        el('button', { class: 'btn btn-secondary', title: 'Delete', onclick: () => modal({
          title: `Delete ${rec.code}?`,
          build: (b) => b.append(el('p', {}, 'Better: set its status to used up or discarded, so its history stays. Deleting removes it from the lists; the code is not given out again.')),
          buttons: [{ label: 'Cancel', kind: 'secondary' }, { label: 'Delete', kind: 'danger', onClick: async () => {
            await api('DELETE', `/${PLURAL[rec.kind]}/${rec.code}`);
            location.hash = PLURAL[rec.kind];
          } }],
        }) }, '🗑')));
  },

  facts(pairs) {
    return el('dl', { class: 'facts' }, pairs.filter(([, v]) => v !== null && v !== undefined && v !== '')
      .map(([k, v]) => [el('dt', {}, k), el('dd', {}, v)]));
  },

  section(title, ...content) { return el('section', { class: 'section' }, el('h2', {}, title), content); },

  glycerolFields(rec) {
    return [
      { name: 'clone', label: 'Clone', value: rec?.clone, placeholder: 'e.g. 4, B2' },
      { name: 'host', label: 'Strain', value: rec?.host, list: 'hosts', placeholder: 'e.g. DH5α, GV3101' },
      { name: 'selection', label: 'Selection', value: rec?.selection, placeholder: 'e.g. kanamycin 50 µg/mL' },
      { name: 'location', label: 'Kept in', value: rec?.location, placeholder: 'e.g. −80 °C freezer 1 / box 3 / B4' },
      { name: 'made_on', label: 'Made on', type: 'date', value: rec?.made_on || today() },
      { name: 'status', label: 'Status', type: 'select', options: this.meta.status, value: rec?.status || 'in stock' },
      { name: 'notes', label: 'Notes', type: 'textarea', value: rec?.notes },
    ];
  },

  /** Choose a plasmid from the Plasmid Editor's library (the ones this person may open). */
  pickPlasmid(title = 'Which plasmid is in it?') {
    return picker({ title, placeholder: 'Search the Plasmid Editor\'s library',
      search: async (q) => (await api('GET', `/plasmids?q=${encodeURIComponent(q)}`)).plasmids,
      describe: (p) => [el('b', { text: p.name }), el('span', { class: 'hint' }, ` · ${p.length.toLocaleString()} bp${p.owner ? ` · ${p.owner}` : ''}${p.confirmed ? ' · ✓ sequenced' : ''}`)] });
  },

  /** Link a glycerol stock to the plasmid it holds, or to another one. */
  async linkPlasmid(rec) {
    const plasmid = await this.pickPlasmid(rec.plasmid_id ? `Which plasmid is in ${rec.code}?` : `Link ${rec.code} to its plasmid`);
    if (!plasmid) return;
    try {
      await api('PUT', `/glycerol/${rec.code}`, { plasmid_id: plasmid.id });
      toast(`${rec.code} is linked to ${plasmid.name}`, 'success');
      this.reload();
    } catch (err) { toast(err.message, 'error', 6000); }
  },

  async newGlycerol() {
    const plasmid = await this.pickPlasmid();
    if (!plasmid) return;
    formModal({
      title: `Glycerol stock of ${plasmid.name}`,
      intro: 'Usually made for you on confirming a plasmid by sequencing in the Plasmid Editor; add one here for stocks made otherwise.',
      fields: this.glycerolFields(null),
      submit: async (v) => {
        const { record } = await api('POST', '/glycerol', { ...v, plasmid_id: plasmid.id, plasmid_name: plasmid.name, lab: this.chosenLab });
        location.hash = `glycerol=${record.code}`;
        toast(`Made ${record.code}`, 'success');
      },
    });
  },

  glycerolView(rec) {
    const linked = rec.plasmid || { state: rec.plasmid_id ? 'open' : 'unlinked' };
    const open = linked.state === 'open';
    // The plasmid it holds: a link to it in the editor, or why there is none.
    const plasmidFact = open
      ? el('a', { href: editorOpen(rec.plasmid_id), target: '_blank', rel: 'noopener', title: 'Open in the Plasmid Editor' }, `🧬 ${linked.name || rec.plasmid_name}`)
      : el('span', {}, rec.plasmid_name || '—', ' ', el('span', { class: 'hint warn-text' }, {
        unlinked: '(not linked to a plasmid in the editor)',
        missing: '(no longer in the Plasmid Editor\'s library)',
        other_lab: `(${linked.owner || 'someone'}'s, in another lab, and not public)`,
      }[linked.state] || ''));
    return el('div', {},
      this.head(rec, (linked.name || rec.plasmid_name) + (rec.clone ? ` clone ${rec.clone}` : ''),
        [rec.status, rec.host, rec.location && `kept in ${rec.location}`].filter(Boolean).join(' · '), [
          open ? el('a', { class: 'btn btn-primary', href: editorOpen(rec.plasmid_id), target: '_blank', rel: 'noopener',
            title: 'Open the plasmid in this stock in the Plasmid Editor' }, '🧬 Open in the Plasmid Editor') : null,
          el('button', { class: `btn ${open ? 'btn-secondary' : 'btn-primary'}`, onclick: () => this.linkPlasmid(rec),
            title: open ? 'Link this stock to another plasmid of the editor\'s library' : 'Link this stock to its plasmid in the editor\'s library' },
          open ? '🔗 Change plasmid…' : '🔗 Link a plasmid…'),
          el('button', { class: 'btn btn-secondary', onclick: () => formModal({
            title: `Edit ${rec.code}`, fields: this.glycerolFields(rec),
            submit: async (v) => { await api('PUT', `/glycerol/${rec.code}`, v); this.reload(); },
          }) }, '✎ Edit')]),
      this.facts([
        ['Plasmid', plasmidFact],
        ['Sequencing', open ? el('a', { href: `${ST.editor}/sequencing?sequence=${encodeURIComponent(rec.plasmid_id)}`, target: '_blank', rel: 'noopener' },
          rec.source === 'sequencing' ? '✓ confirmed by sequencing: see the reads' : 'see the reads') : null],
        ['Clone', rec.clone], ['Strain', rec.host], ['Selection', rec.selection], ['Kept in', rec.location],
        ['Made on', rec.made_on], ['Status', rec.status], ['Made by', `${rec.created_by || '—'} · ${localTime(rec.created_at)}`]]),
      rec.notes ? el('p', { class: 'description' }, rec.notes) : null,
      rec.same_plasmid?.length ? this.section('Other stocks of this plasmid', el('div', { class: 'chips' },
        rec.same_plasmid.map((s) => el('a', { class: 'chip', href: `#glycerol=${s.code}` }, `🧫 ${s.code}${s.clone ? ` clone ${s.clone}` : ''} · ${s.status}`)))) : null);
  },

  editPrimer(rec) {
    let preview;
    formModal({
      title: rec ? `Edit ${rec.code}` : 'New primer',
      fields: [
        { name: 'name', label: 'Name', value: rec?.name, placeholder: 'e.g. GFP-F, M13 fwd' },
        { name: 'sequence', label: 'Sequence (5′→3′)', value: rec?.sequence, placeholder: 'ACGT…; IUPAC codes allowed' },
        { name: 'direction', label: 'Direction', type: 'select', options: [['', '—'], ['forward', 'forward'], ['reverse', 'reverse']], value: rec?.direction || '' },
        { name: 'target', label: 'Target', value: rec?.target, placeholder: 'the gene or plasmid it is for' },
        { name: 'purpose', label: 'Purpose', value: rec?.purpose, placeholder: 'e.g. sequencing, colony PCR, cloning' },
        { name: 'modifications', label: 'Modifications', value: rec?.modifications, placeholder: "e.g. 5' phosphate, FAM" },
        { name: 'supplier', label: 'Supplier', value: rec?.supplier },
        { name: 'ordered_on', label: 'Ordered on', type: 'date', value: rec?.ordered_on },
        { name: 'concentration', label: 'Concentration', value: rec?.concentration, placeholder: 'e.g. 100 µM stock' },
        { name: 'location', label: 'Kept in', value: rec?.location, placeholder: 'e.g. Primer box 2 / C5' },
        { name: 'status', label: 'Status', type: 'select', options: this.meta.status, value: rec?.status || 'in stock' },
        { name: 'notes', label: 'Notes', type: 'textarea', value: rec?.notes },
      ],
      submit: async (v) => {
        const res = rec ? await api('PUT', `/primers/${rec.code}`, v) : await api('POST', '/primers', { ...v, lab: this.chosenLab });
        if (rec) this.reload(); else location.hash = `primer=${res.record.code}`;
      },
    });
    // Length, GC and Tm as the sequence is typed.
    setTimeout(() => {
      const field = [...document.querySelectorAll('.modal-body .field')].find((f) => f.textContent.startsWith('Sequence'));
      if (!field) return;
      preview = el('span', { class: 'hint' });
      field.append(preview);
      const input = field.querySelector('input');
      let ticket = 0;
      const calc = async () => {
        const mine = ++ticket;
        if (!input.value.trim()) { put(preview, ''); return; }
        try {
          const d = await api('GET', `/oligo?sequence=${encodeURIComponent(input.value)}`);
          if (mine === ticket) put(preview, `${d.length} nt · GC ${d.gc}%${d.tm !== null ? ` · Tm ${d.tm} °C` : ''}`);
        } catch (err) { if (mine === ticket) put(preview, err.message); }
      };
      input.addEventListener('input', calc);
      calc();
    }, 0);
  },

  primerView(rec) {
    return el('div', {},
      this.head(rec, rec.name, [rec.direction, rec.target, rec.status, rec.location && `kept in ${rec.location}`].filter(Boolean).join(' · '), [
        el('button', { class: 'btn btn-secondary', onclick: () => this.editPrimer(rec) }, '✎ Edit')]),
      el('div', { class: 'primer-seq' },
        el('div', {}, el('span', { class: 'hint' }, "5′ "), el('span', { class: 'mono big' }, rec.sequence), el('span', { class: 'hint' }, " 3′"),
          el('button', { class: 'btn btn-secondary btn-sm', onclick: async () => {
            if (await copyText(rec.sequence)) toast('Copied', 'success', 1500);
            else toast('Copying is blocked here: select the sequence and copy it', 'error', 4000);
          } }, 'Copy')),
        el('div', { class: 'hint' }, 'Reverse complement: ', el('span', { class: 'mono' }, revcomp(rec.sequence)))),
      this.facts([['Length', `${rec.length} nt`], ['GC', `${rec.gc}%`], ['Tm', rec.tm !== null ? `${rec.tm} °C (nearest neighbour, 50 mM Na⁺, 250 nM primer)` : null],
        ['Direction', rec.direction], ['Target', rec.target], ['Purpose', rec.purpose], ['Modifications', rec.modifications],
        ['Supplier', rec.supplier], ['Ordered on', rec.ordered_on], ['Concentration', rec.concentration], ['Kept in', rec.location],
        ['Status', rec.status], ['Made by', `${rec.created_by || '—'} · ${localTime(rec.created_at)}`]]),
      rec.notes ? el('p', { class: 'description' }, rec.notes) : null);
  },

  /* chemicals ---------------------------------------------------------------------- */

  editChemical(rec) {
    formModal({
      title: rec ? `Edit ${rec.code}` : 'New chemical',
      fields: [
        { name: 'name', label: 'Name', value: rec?.name, placeholder: 'e.g. Ethanol absolute, Kanamycin sulfate' },
        { name: 'cas', label: 'CAS number', value: rec?.cas, placeholder: 'e.g. 64-17-5', hint: 'The check digit is checked, to catch typing errors.' },
        { name: 'room', label: 'Room', value: rec?.room, placeholder: 'e.g. Kruyt O.703, flammables cabinet' },
        { name: 'size', label: 'Size', value: rec?.size, placeholder: 'e.g. 500 mL, 25 g' },
        { name: 'status', label: 'Status', type: 'select', options: this.meta.chemical_status, value: rec?.status || 'in stock' },
        { name: 'notes', label: 'Notes', type: 'textarea', value: rec?.notes },
      ],
      submit: async (v) => {
        const res = rec ? await api('PUT', `/chemicals/${rec.code}`, v) : await api('POST', '/chemicals', { ...v, lab: this.chosenLab });
        if (res.ordered) { toast(`${res.record.name}: ${res.ordered}`, 'success', 3500); this.refreshWaiting(); }
        if (rec) this.reload(); else location.hash = `chemical=${res.record.code}`;
      },
    });
  },

  /** A switch: the chemical has run out (on), or is in stock (off). In the list it does not open the chemical. */
  outToggle(rec) {
    const box = el('input', { type: 'checkbox', checked: rec.status === 'out', onchange: async () => {
      const status = box.checked ? 'out' : 'in stock';
      let res;
      try {
        res = await api('PUT', `/chemicals/${rec.code}`, { status });
      } catch (err) { box.checked = !box.checked; toast(`Not changed: ${err.message}`, 'error', 6000); return; }
      rec.status = status;
      toast(`${rec.name}: ${status === 'out' ? 'marked as out' : 'back in stock'}${res.ordered ? `, and ${res.ordered}` : ''}`, 'success', 3500);
      this.refreshWaiting();
      // In the list: grey its row; on its page: show it again.
      const row = box.closest('tr');
      if (row) row.classList.toggle('faded', status !== 'in stock');
      else this.reload();
    } });
    return el('label', { class: 'switch', title: 'Out: it has run out and needs ordering (it goes on the order list)', onclick: (e) => e.stopPropagation() },
      box, el('span', { class: 'slider' }), el('span', { class: 'switch-label' }, 'Out'));
  },

  /** Where to look a chemical up: the university's hazardous substances register (SOFOS), and Chemwatch. */
  safetyLinks(cas) {
    return el('span', { class: 'safety-links' },
      el('a', { class: 'btn btn-secondary btn-sm', href: ST.sofos, target: '_blank', rel: 'noopener',
        title: 'Utrecht University\'s register of hazardous substances (SOFOS)' }, '🛡 SOFOS ↗'),
      el('a', { class: 'btn btn-secondary btn-sm', href: ST.chemwatch, target: '_blank', rel: 'noopener',
        title: cas ? `Chemwatch: search it for CAS ${cas}` : 'Chemwatch' }, '☣ Chemwatch ↗'));
  },

  chemicalView(rec) {
    const sds = rec.sds;
    const copyCas = el('button', { class: 'btn btn-secondary btn-sm', onclick: async () => {
      if (await copyText(rec.cas)) toast('CAS number copied: paste it into the search', 'success', 2500);
      else toast('Copying is blocked here: select the CAS number and copy it', 'error', 4000);
    } }, 'Copy');
    const sdsInput = el('input', { type: 'file', hidden: true, accept: 'application/pdf,.pdf',
      onchange: (e) => { if (e.target.files.length) this.upload(rec, [e.target.files[0]], SDS); } });
    return el('div', {},
      this.head(rec, rec.name, [rec.cas && `CAS ${rec.cas}`, rec.size, rec.room && `in ${rec.room}`, rec.status].filter(Boolean).join(' · '), [
        rec.status === 'discarded' ? null : this.outToggle(rec),
        el('button', { class: 'btn btn-secondary', onclick: () => this.editChemical(rec) }, '✎ Edit')]),
      this.facts([['Name', rec.name], ['CAS number', rec.cas ? el('span', {}, el('span', { class: 'mono' }, rec.cas), ' ', copyCas) : null],
        ['Room', rec.room], ['Size', rec.size], ['Status', rec.status], ['Added by', `${rec.created_by || '—'} · ${localTime(rec.created_at)}`]]),
      rec.notes ? el('p', { class: 'description' }, rec.notes) : null,
      this.section('Safety data sheet',
        el('div', { class: 'sds' },
          sds ? el('span', {}, el('a', { class: 'btn btn-primary', href: fileUrl(sds.id), target: '_blank', rel: 'noopener' }, `📕 Open the SDS`),
            el('span', { class: 'hint' }, ` ${sds.filename} · ${sizeLabel(sds.size)} · added by ${sds.created_by || '—'} ${localTime(sds.created_at)}`))
            : el('span', { class: 'hint' }, 'No safety data sheet yet. '),
          el('label', { class: `btn ${sds ? 'btn-secondary' : 'btn-primary'} btn-sm` }, sds ? 'Replace the SDS…' : '📕 Add the SDS (PDF)…', sdsInput)),
        el('p', { class: 'hint' }, rec.cas ? `Look it up by its CAS number, ${rec.cas}:` : 'Look it up:', ' ', this.safetyLinks(rec.cas))));
  },

  /* antibodies --------------------------------------------------------------------- */

  editAntibody(rec) {
    formModal({
      title: rec ? `Edit ${rec.code}` : 'New antibody',
      fields: [
        { name: 'short_code', label: 'Short code in lab', value: rec?.short_code, placeholder: 'e.g. αGFP-m, αRb-HRP' },
        { name: 'description', label: 'Description', value: rec?.description, placeholder: 'e.g. Anti-GFP, monoclonal (clone B-2)' },
        { name: 'type', label: 'Primary / secondary / other', type: 'select', value: rec?.type || 'primary',
          options: this.meta.antibody_types.map((t) => [t, t[0].toUpperCase() + t.slice(1)]) },
        { name: 'producer', label: 'Producer', value: rec?.producer, placeholder: 'e.g. Santa Cruz, Abcam, Agrisera' },
        { name: 'host', label: 'Source animal', value: rec?.host, placeholder: 'e.g. mouse, rabbit, goat' },
        { name: 'product_number', label: 'Product number', value: rec?.product_number, placeholder: 'e.g. sc-9996' },
        { name: 'notes', label: 'Notes about the use', type: 'textarea', value: rec?.notes,
          placeholder: 'e.g. 1:5000 in 5% milk TBS-T for western blots; 1:200 for immunostaining' },
        { name: 'status', label: 'Status', type: 'select', options: this.meta.status, value: rec?.status || 'in stock' },
      ],
      submit: async (v) => {
        const res = rec ? await api('PUT', `/antibodies/${rec.code}`, v) : await api('POST', '/antibodies', { ...v, lab: this.chosenLab });
        if (rec) this.reload(); else location.hash = `antibody=${res.record.code}`;
      },
    });
  },

  antibodyView(rec) {
    const kindLabel = rec.type ? rec.type[0].toUpperCase() + rec.type.slice(1) : '';
    return el('div', {},
      this.head(rec, rec.short_code || rec.description,
        [kindLabel && `${kindLabel} antibody`, rec.host && `raised in ${rec.host}`, rec.producer, rec.status].filter(Boolean).join(' · '), [
          el('button', { class: 'btn btn-secondary', onclick: () => this.editAntibody(rec) }, '✎ Edit')]),
      this.facts([['Short code in lab', rec.short_code], ['Description', rec.description], ['Primary / secondary / other', kindLabel],
        ['Producer', rec.producer], ['Source animal', rec.host], ['Product number', rec.product_number ? el('span', { class: 'mono' }, rec.product_number) : null],
        ['Status', rec.status], ['Added by', `${rec.created_by || '—'} · ${localTime(rec.created_at)}`]]),
      rec.notes ? this.section('Notes about the use', el('p', { class: 'description' }, rec.notes)) : null);
  },

  /* orders ------------------------------------------------------------------------- */

  /** The number on the Orders tab: requests waiting to be ordered, for a lab admin. */
  showWaiting(n) {
    const badge = document.getElementById('orders-waiting');
    if (!badge) return;
    badge.hidden = !n;
    badge.textContent = n || '';
    badge.title = n ? `${n} request${n === 1 ? '' : 's'} waiting to be ordered` : '';
  },

  async refreshWaiting() {
    if (!this.meta.orders.handles.length) return;
    try { this.showWaiting((await api('GET', '/orders/waiting')).waiting); } catch (e) { /* shown next time */ }
  },

  /** On a stock's page: the line saying it is on the order list. */
  onOrder(rec) {
    const o = rec.order;
    if (!o) return null;
    return el('div', { class: 'on-order' }, el('a', { href: '#orders' }, '🛒 On the order list'), ': ',
      o.status === 'ordered' ? `ordered ${localTime(o.ordered_at).slice(0, 10)}, waiting for it to arrive`
        : `asked for by ${o.requested_by || '—'} ${localTime(o.requested_at).slice(0, 10)}${o.auto ? ' (marked out)' : ''}, not ordered yet`);
  },

  /** Put a chemical, primer or antibody on the order list: its details go along. */
  orderStock(rec) {
    if (rec.order) { toast('It is on the order list already', 'info', 3000); return; }
    formModal({
      title: `Order ${rec.name || rec.short_code || rec.description || rec.code}`,
      intro: `${rec.code} goes on the lab's order list with its details${rec.kind === 'antibody' ? ' (producer and product number)' : rec.kind === 'primer' ? ' (its sequence)' : ''}; the lab admin orders it.`,
      fields: [
        { name: 'quantity', label: 'How much', value: rec.kind === 'chemical' ? rec.size : '', placeholder: rec.kind === 'primer' ? 'e.g. 25 nmol, desalted' : 'e.g. 2 × 500 mL' },
        { name: 'notes', label: 'Note for the lab admin', type: 'textarea', placeholder: 'e.g. needed for Friday\'s westerns' },
        { name: 'urgent', label: 'Urgent', type: 'checkbox' },
      ],
      label: '🛒 Add to order',
      submit: async (v) => {
        const res = await api('POST', '/orders', { ...v, record: rec.code });
        toast(res.already ? 'It was on the order list already' : 'On the order list', 'success', 3000);
        this.refreshWaiting();
        this.reload();
      },
    });
  },

  orderFields(o) {
    const cats = this.meta.orders.categories;
    return [
      { name: 'item', label: 'What', value: o?.item, placeholder: 'e.g. Phusion polymerase, 1000 µL tips, agarose' },
      { name: 'category', label: 'Kind', type: 'select', value: o?.category || 'other', options: cats.map((c) => [c, c[0].toUpperCase() + c.slice(1)]) },
      { name: 'quantity', label: 'How much', value: o?.quantity, placeholder: 'e.g. 2 × 100 U, 10 racks' },
      { name: 'supplier', label: 'Supplier', value: o?.supplier, placeholder: 'e.g. NEB, Merck, Thermo Fisher' },
      { name: 'product_number', label: 'Product number', value: o?.product_number, placeholder: 'e.g. M0530S' },
      { name: 'link', label: 'Link', type: 'url', value: o?.link, placeholder: 'https://… the product page' },
      { name: 'notes', label: 'Notes', type: 'textarea', value: o?.notes },
      { name: 'urgent', label: 'Urgent', type: 'checkbox', value: o?.urgent },
    ];
  },

  orderRequest() {
    const labs = this.meta.lab.labs;
    formModal({
      title: 'Order request',
      intro: `Ask for anything the lab needs: enzymes, kits, consumables, chemicals.${labs.length > 1 ? ` It goes to ${this.meta.lab.lab}'s lab admin (choose another lab at the top).` : ' The lab admin orders it.'} For a chemical, primer or antibody the lab already has, use 🛒 Add to order on its page instead: its details come along.`,
      fields: this.orderFields(null),
      label: '🛒 Send the request',
      submit: async (v) => {
        await api('POST', '/orders', { ...v, lab: this.chosenLab });
        toast('Request sent to the lab admin', 'success', 3000);
        this.refreshWaiting();
        this.showOrders();
      },
    });
  },

  async setOrder(o, change, done) {
    try {
      await api('PUT', `/orders/${o.id}`, change);
      if (done) toast(done, 'success', 2500);
    } catch (err) { toast(err.message, 'error', 6000); }
    // From an order's dialog: close it; the list shows the change.
    document.querySelectorAll('.modal-backdrop').forEach((b) => b.remove());
    this.refreshWaiting();
    this.showOrders();
  },

  /** What a lab admin (or the one who asked) can do with an order, as buttons. */
  orderActions(o) {
    const stop = (fn) => (e) => { e.stopPropagation(); fn(); };
    const cancel = () => modal({
      title: `Cancel the order of ${o.item}?`,
      build: (b) => b.append(el('p', {}, 'It stays in the list of done orders, marked cancelled.')),
      buttons: [{ label: 'Keep it', kind: 'secondary' }, { label: 'Cancel the order', kind: 'danger', onClick: () => this.setOrder(o, { status: 'cancelled' }, 'Cancelled') }],
    });
    const out = [];
    if (o.can_handle && o.status === 'requested') out.push(el('button', { class: 'btn btn-primary btn-sm', onclick: stop(() => this.setOrder(o, { status: 'ordered' }, `${o.item}: ordered`)) }, '✓ Ordered'));
    if (o.can_handle && o.status === 'ordered') out.push(el('button', { class: 'btn btn-primary btn-sm', onclick: stop(() => this.setOrder(o, { status: 'received' }, `${o.item}: received${o.record_code ? `; ${o.record_code} is in stock` : ''}`)) }, '📦 Received'));
    if ((o.can_handle && ['requested', 'ordered'].includes(o.status)) || (o.can_change && o.status === 'requested')) {
      out.push(el('button', { class: 'btn btn-secondary btn-sm', title: 'Cancel', onclick: stop(cancel) }, '✕'));
    }
    if (o.can_handle && ['received', 'cancelled'].includes(o.status)) out.push(el('button', { class: 'btn btn-secondary btn-sm', title: 'Put it back on the list, to be ordered', onclick: stop(() => this.setOrder(o, { status: 'requested' }, 'Back on the list')) }, '↺'));
    return el('span', { class: 'row-actions' }, out);
  },

  async showOrders() {
    const main = document.getElementById('main');
    const handles = this.meta.orders.handles;
    const filter = el('select', { class: 'order-filter', 'aria-label': 'Which orders' },
      [['open', 'Open: to order and on their way'], ['requested', 'To order'], ['ordered', 'Ordered, on their way'],
        ['closed', 'Done: received or cancelled'], ['', 'All']].map(([v, t]) => el('option', { value: v, selected: (this.orderFilter ?? 'open') === v }, t)));
    const query = el('input', { type: 'search', class: 'list-search', value: this.q_orders || '',
      placeholder: 'Search by item, supplier, product number, who asked, or a stock\'s code' });
    const sheet = el('a', { class: 'btn btn-secondary', title: 'The orders shown, as a spreadsheet: for filling in a supplier\'s order form' }, '⬇ Spreadsheet');
    const table = el('div', { class: 'list' });
    const draw = async () => {
      this.orderFilter = filter.value;
      this.q_orders = query.value;
      const qs = `?status=${encodeURIComponent(filter.value)}&q=${encodeURIComponent(query.value)}`;
      sheet.href = url(`/api/orders.csv${qs}`);
      let data;
      try { data = await api('GET', `/orders${qs}`); } catch (err) { put(table, el('p', { class: 'empty' }, err.message)); return; }
      this.showWaiting(data.waiting);
      put(table, this.ordersTable(data.orders, !!handles.length));
    };
    let timer;
    query.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(draw, 250); });
    filter.addEventListener('change', draw);
    put(main,
      el('div', { class: 'page-head' }, el('h1', {}, '🛒 Orders'),
        el('span', { class: 'actions' }, el('button', { class: 'btn btn-primary', onclick: () => this.orderRequest() }, '＋ Order request'),
          handles.length ? sheet : null)),
      el('p', { class: 'hint' }, handles.length
        ? `You order for ${handles.join(', ')}: these are the lab's requests, from the request form, 🛒 Add to order on a chemical, primer or antibody, and chemicals switched to Out. Mark each ✓ Ordered when you have ordered it, and 📦 Received when it arrives; a stock that had run out is then back in stock.`
        : 'Ask for what the lab needs with ＋ Order request, or 🛒 Add to order on a chemical, primer or antibody; a chemical switched to Out is added by itself. Your lab admin orders it. These are your requests, and how far each has got.'),
      el('div', { class: 'list-tools' }, filter, query), table);
    await draw();
  },

  ordersTable(rows, handler) {
    if (!rows.length) return el('p', { class: 'empty' }, 'No orders here.');
    const STATUS_LABEL = { requested: 'to order', ordered: 'ordered', received: 'received', cancelled: 'cancelled' };
    return el('table', { class: 'data orders' },
      el('thead', {}, el('tr', {}, ['#', 'What', 'Kind', 'How much', 'Supplier', 'Product number', handler ? 'Asked by' : 'Asked', 'Status', ''].map((h) => el('th', {}, h)))),
      el('tbody', {}, rows.map((o) => el('tr', { class: `clickable ${['received', 'cancelled'].includes(o.status) ? 'faded' : ''}`, onclick: () => this.openOrder(o) },
        el('td', { class: 'code' }, o.id),
        el('td', {}, o.urgent ? el('span', { class: 'urgent', title: 'Urgent' }, '❗ ') : null, el('b', {}, o.item),
          o.record_code ? [' ', el('a', { class: 'code-badge', href: `#${o.record_kind}=${o.record_code}`, onclick: (e) => e.stopPropagation() }, o.record_code)] : null,
          o.details ? el('div', { class: 'hint clip' }, o.details) : null,
          o.notes ? el('div', { class: 'hint clip', title: o.notes }, `“${o.notes}”`) : null),
        el('td', {}, o.category), el('td', {}, o.quantity),
        el('td', {}, o.link ? el('a', { href: o.link, target: '_blank', rel: 'noopener noreferrer', onclick: (e) => e.stopPropagation() }, `${o.supplier || 'link'} ↗`) : o.supplier),
        el('td', {}, el('span', { class: 'mono' }, o.product_number)),
        el('td', {}, handler ? `${o.requested_by || '—'} · ` : '', localTime(o.requested_at).slice(0, 10), o.auto ? el('span', { class: 'hint', title: 'Added on marking the chemical out' }, ' (out)') : null,
          handler && this.meta.orders.handles.length > 1 ? el('div', { class: 'hint' }, o.lab) : null),
        el('td', {}, el('span', { class: `status-pill status-${o.status}` }, STATUS_LABEL[o.status] || o.status),
          o.status === 'ordered' && o.ordered_at ? el('div', { class: 'hint' }, localTime(o.ordered_at).slice(0, 10)) : null),
        el('td', {}, this.orderActions(o))))));
  },

  /** An order: everything about it, its history, and changing it (the lab admin, or the one who asked until it is ordered). */
  async openOrder(o) {
    let full;
    try { full = (await api('GET', `/orders/${o.id}`)).order; } catch (err) { toast(err.message, 'error'); return; }
    const when = (at, by) => (at ? `${localTime(at)}${by ? ` · ${by}` : ''}` : null);
    modal({
      title: `Order ${full.id}: ${full.item}`, wide: true,
      build: (body) => body.append(
        this.facts([['What', full.item], ['Stock', full.record_code ? el('a', { href: `#${full.record_kind}=${full.record_code}`, onclick: () => document.querySelector('.modal-backdrop')?.remove() }, full.record_code) : null],
          ['Kind', full.category], ['How much', full.quantity], ['Supplier', full.supplier], ['Product number', full.product_number],
          ['Details', full.details], ['Link', full.link ? el('a', { href: full.link, target: '_blank', rel: 'noopener noreferrer' }, full.link) : null],
          ['Notes', full.notes], ['Urgent', full.urgent ? 'yes' : null], ['Lab', full.lab],
          ['Asked', when(full.requested_at, full.requested_by) + (full.auto ? ' (on marking the chemical out)' : '')],
          ['Ordered', when(full.ordered_at, full.ordered_by)], ['Received', when(full.received_at, full.received_by)],
          ['Cancelled', full.status === 'cancelled' ? when(full.closed_at, full.closed_by) : null], ['Status', full.status]]),
        el('div', { class: 'actions' }, this.orderActions(full)),
        el('details', { class: 'history' }, el('summary', {}, `History (${full.changes.length})`),
          el('ul', { class: 'plain' }, full.changes.map((c) => el('li', {}, el('span', { class: 'hint' }, `${localTime(c.changed_at)} · ${c.changed_by || '—'}: `), c.what))))),
      buttons: full.can_change ? [{ label: 'Close', kind: 'secondary' }, { label: '✎ Edit', onClick: () => formModal({
        title: `Edit order ${full.id}`, fields: this.orderFields(full),
        submit: async (v) => { await api('PUT', `/orders/${full.id}`, v); this.showOrders(); },
      }) }] : [{ label: 'Close', kind: 'secondary' }],
    });
  },

  async upload(rec, files, caption) {
    const form = new FormData();
    for (const f of files) form.append('file', f, f.name || 'photo.png');
    if (caption) form.append('caption', caption);
    try {
      await api('POST', `/${PLURAL[rec.kind]}/${rec.code}/attachments`, undefined, form);
      if (caption === SDS) toast('Safety data sheet added', 'success', 2500);
      this.reload();
    } catch (err) { toast(`Not attached: ${err.message}`, 'error', 7000); }
  },

  files(rec) {
    // A chemical's safety data sheets are shown in their own section.
    const list = (rec.attachments || []).filter((a) => a.caption !== SDS);
    const zone = el('div', { class: 'files' },
      list.filter((a) => a.image).length ? el('div', { class: 'gallery' }, list.filter((a) => a.image).map((a) => el('figure', {},
        el('img', { src: fileUrl(a.id), loading: 'lazy', alt: a.filename, onclick: () => window.open(fileUrl(a.id), '_blank', 'noopener') }),
        el('figcaption', {}, a.filename)))) : null,
      list.filter((a) => !a.image).length ? el('ul', { class: 'file-list' }, list.filter((a) => !a.image).map((a) => el('li', {},
        el('span', { class: 'file-icon' }, FILE_ICONS[a.kind] || '📎'), el('a', { href: fileUrl(a.id), target: '_blank', rel: 'noopener' }, a.filename),
        el('span', { class: 'hint' }, ` ${sizeLabel(a.size)} · ${a.created_by || ''}`)))) : null,
      el('label', { class: 'btn btn-secondary btn-sm' }, '📎 Add photos or files…',
        el('input', { type: 'file', multiple: true, hidden: true, onchange: (e) => this.upload(rec, [...e.target.files]) })));
    zone.addEventListener('dragover', (e) => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); zone.classList.add('drop'); } });
    zone.addEventListener('dragleave', () => zone.classList.remove('drop'));
    zone.addEventListener('drop', (e) => { e.preventDefault(); zone.classList.remove('drop'); this.upload(rec, [...e.dataTransfer.files]); });
    return this.section(`Photos and files (${list.length})`, zone);
  },

  mentions(rec) {
    if (!rec.mentions?.length) return null;
    return this.section('In the lab notebook', el('ul', { class: 'plain' }, rec.mentions.map((m) => el('li', {},
      el('a', { href: `${ST.notebook}/#note=${m.id}`, target: '_blank', rel: 'noopener' }, `📓 ${m.title}`),
      el('span', { class: 'hint' }, m.owner ? ` · ${m.owner}` : ' · protocol library')))));
  },

  history(rec) {
    return el('details', { class: 'history' }, el('summary', {}, `History (${rec.changes.length})`),
      el('ul', { class: 'plain' }, rec.changes.map((c) => el('li', {}, el('span', { class: 'hint' }, `${localTime(c.changed_at)} · ${c.changed_by || '—'}: `), c.what))));
  },
};

document.addEventListener('DOMContentLoaded', () => App.init());
