'use strict';
/*
 * The Lab Stocks page: glycerol stocks and primers, a list of each and a page
 * for each record. Addresses: #glycerol, #primers, #glycerol=GL-G-0001, #primer=GL-O-0001.
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
const ICON = { glycerol: '🧫', primer: '🧬' };
const NAME = { glycerol: 'glycerol stock', primer: 'primer' };
const PLURAL = { glycerol: 'glycerol', primer: 'primers' };
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
    } catch (err) {
      put(document.getElementById('main'), el('p', { class: 'empty' }, err.message));
      return;
    }
    document.body.append(el('datalist', { id: 'hosts' }, HOSTS.map((h) => el('option', { value: h }))));
    window.addEventListener('hashchange', () => this.route());
    this.route();
  },

  route() {
    const hash = location.hash.slice(1) || 'glycerol';
    const record = hash.match(/^(glycerol|primer)=(.+)$/);
    for (const tab of document.querySelectorAll('.view-tab')) {
      tab.classList.toggle('active', tab.dataset.view === (record ? PLURAL[record[1]] : hash));
    }
    if (record) this.showRecord(record[1], decodeURIComponent(record[2]));
    else this.showList(hash === 'primers' ? 'primer' : 'glycerol');
  },

  /* lists -------------------------------------------------------------------------- */

  labCodeLine() {
    const lab = this.meta.lab;
    return el('p', { class: 'lab-code-line' },
      'Codes in ', el('b', {}, lab.lab.startsWith('user:') ? 'your own stocks' : lab.lab), ' start with ',
      el('span', { class: 'code-badge' }, `${lab.code}-`), ` (${lab.code}-G glycerol stocks, ${lab.code}-O primers)`,
      lab.can_change ? el('button', { class: 'btn btn-secondary btn-sm', style: 'margin-left:.6rem', onclick: () => formModal({
        title: 'Choose the lab code',
        intro: 'Every code your lab makes starts with it. Keep it the same as in the Seed Bank. It can be chosen until the lab\'s first stock; after that it is fixed, as codes on labels never change.',
        fields: [{ name: 'code', label: 'Lab code', value: lab.code }],
        submit: async (v) => { this.meta.lab = await api('PUT', '/lab', v); this.route(); },
      }) }, 'Change…') : null);
  },

  async showList(kind) {
    const main = document.getElementById('main');
    const query = el('input', { type: 'search', class: 'list-search', value: this[`q_${kind}`] || '',
      placeholder: kind === 'glycerol' ? 'Search by code, plasmid, clone, strain, selection or place'
        : 'Search by code, name, target, place, or a piece of the sequence (e.g. GGCCAGT)' });
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
      el('div', { class: 'page-head' }, el('h1', {}, kind === 'glycerol' ? '🧫 Glycerol stocks' : '🧬 Primers'),
        el('span', { class: 'actions' },
          el('button', { class: 'btn btn-primary', onclick: () => (kind === 'glycerol' ? this.newGlycerol() : this.editPrimer()) },
            kind === 'glycerol' ? '＋ Glycerol stock' : '＋ Primer'), labelBtn)),
      this.labCodeLine(),
      el('p', { class: 'hint' }, kind === 'glycerol'
        ? 'Frozen cultures of the lab\'s plasmids. Confirming a plasmid by sequencing in the Plasmid Editor makes its glycerol stock here, with the next number.'
        : 'The lab\'s oligos, with where each tube is. Primers designed in the Plasmid Editor can be saved here, and the editor shows which of them bind a plasmid.'),
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
    const head = kind === 'glycerol'
      ? ['', 'Code', 'Plasmid', 'Clone', 'Strain', 'Selection', 'Kept in', 'Made', 'Status']
      : ['', 'Code', 'Name', 'Sequence (5′→3′)', 'nt', 'Tm', 'Kept in', 'Status'];
    const cells = kind === 'glycerol'
      ? (r) => [r.plasmid_name, r.clone, r.host, r.selection, r.location, r.made_on || (r.created_at || '').slice(0, 10),
        r.source === 'sequencing' ? `${r.status} ✓` : r.status]
      : (r) => [r.name, el('span', { class: 'mono' }, r.sequence), r.length, r.tm !== null ? `${r.tm} °C` : '', r.location, r.status];
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
    put(main, kind === 'glycerol' ? this.glycerolView(rec) : this.primerView(rec),
      this.files(rec), this.mentions(rec), this.history(rec));
  },

  reload() { this.showRecord(this.rec.kind, this.rec.code); },

  head(rec, title, subtitle, actions) {
    return el('div', { class: 'record-head' },
      el('div', {}, el('div', { class: 'crumbs' }, el('a', { href: `#${PLURAL[rec.kind]}` }, `${ICON[rec.kind]} All ${NAME[rec.kind]}s`)),
        el('h1', {}, el('span', { class: 'code-badge' }, rec.code), ' ', title),
        subtitle ? el('div', { class: 'hint' }, subtitle) : null),
      el('span', { class: 'actions' }, actions,
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

  async newGlycerol() {
    const plasmid = await picker({ title: 'Which plasmid is in it?', placeholder: 'Search the Plasmid Editor\'s library',
      search: async (q) => (await api('GET', `/plasmids?q=${encodeURIComponent(q)}`)).plasmids,
      describe: (p) => [el('b', { text: p.name }), el('span', { class: 'hint' }, ` · ${p.length.toLocaleString()} bp${p.owner ? ` · ${p.owner}` : ''}${p.confirmed ? ' · ✓ sequenced' : ''}`)] });
    if (!plasmid) return;
    formModal({
      title: `Glycerol stock of ${plasmid.name}`,
      intro: 'Usually made for you on confirming a plasmid by sequencing in the Plasmid Editor; add one here for stocks made otherwise.',
      fields: this.glycerolFields(null),
      submit: async (v) => {
        const { record } = await api('POST', '/glycerol', { ...v, plasmid_id: plasmid.id, plasmid_name: plasmid.name });
        location.hash = `glycerol=${record.code}`;
        toast(`Made ${record.code}`, 'success');
      },
    });
  },

  glycerolView(rec) {
    return el('div', {},
      this.head(rec, rec.plasmid_name + (rec.clone ? ` clone ${rec.clone}` : ''),
        [rec.status, rec.host, rec.location && `kept in ${rec.location}`].filter(Boolean).join(' · '), [
          el('button', { class: 'btn btn-secondary', onclick: () => formModal({
            title: `Edit ${rec.code}`, fields: this.glycerolFields(rec),
            submit: async (v) => { await api('PUT', `/glycerol/${rec.code}`, v); this.reload(); },
          }) }, '✎ Edit')]),
      this.facts([
        ['Plasmid', rec.plasmid_id ? el('a', { href: editorOpen(rec.plasmid_id), target: '_blank', rel: 'noopener', title: 'Open in the Plasmid Editor' }, `🧬 ${rec.plasmid_name}`) : rec.plasmid_name],
        ['Sequencing', rec.plasmid_id ? el('a', { href: `${ST.editor}/sequencing?sequence=${encodeURIComponent(rec.plasmid_id)}`, target: '_blank', rel: 'noopener' },
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
        const res = rec ? await api('PUT', `/primers/${rec.code}`, v) : await api('POST', '/primers', v);
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
          el('button', { class: 'btn btn-secondary btn-sm', onclick: () => navigator.clipboard.writeText(rec.sequence).then(() => toast('Copied', 'success', 1500)) }, 'Copy')),
        el('div', { class: 'hint' }, 'Reverse complement: ', el('span', { class: 'mono' }, revcomp(rec.sequence)))),
      this.facts([['Length', `${rec.length} nt`], ['GC', `${rec.gc}%`], ['Tm', rec.tm !== null ? `${rec.tm} °C (nearest neighbour, 50 mM Na⁺, 250 nM primer)` : null],
        ['Direction', rec.direction], ['Target', rec.target], ['Purpose', rec.purpose], ['Modifications', rec.modifications],
        ['Supplier', rec.supplier], ['Ordered on', rec.ordered_on], ['Concentration', rec.concentration], ['Kept in', rec.location],
        ['Status', rec.status], ['Made by', `${rec.created_by || '—'} · ${localTime(rec.created_at)}`]]),
      rec.notes ? el('p', { class: 'description' }, rec.notes) : null);
  },

  async upload(rec, files) {
    const form = new FormData();
    for (const f of files) form.append('file', f, f.name || 'photo.png');
    try {
      await api('POST', `/${PLURAL[rec.kind]}/${rec.code}/attachments`, undefined, form);
      this.reload();
    } catch (err) { toast(`Not attached: ${err.message}`, 'error', 7000); }
  },

  files(rec) {
    const list = rec.attachments || [];
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
