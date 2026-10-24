'use strict';
/*
 * The Lab Stocks page: glycerol stocks, primers, chemicals and antibodies, a list
 * of each and a page for each record. Addresses: #glycerol, #primers, #chemicals,
 * #antibodies, #glycerol=GL-G-0001, #primer=GL-O-0001, #chemical=GL-C-0001,
 * #antibody=GL-A-0001; and the order list, #orders.
 */

const ST = window.ST;
const url = (path) => `${ST.base}${path}`;
/** One of Trellis Tools' small icons (static/trellis/glyphs/), in place of an emoji. */
const glyph = (name) => el('img', { class: 'tt-glyph', src: url(`/static/trellis/glyphs/${name}.svg`), alt: '' });

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
        } else if (f.type === 'custom') {
          const made = f.build();
          inputs[f.name] = { custom: made.get };
          body.append(el('div', { class: 'field' }, el('span', { class: 'field-label' }, f.label), made.node,
            f.hint ? el('span', { class: 'hint' }, f.hint) : null));
          continue;
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
        for (const [k, input] of Object.entries(inputs)) {
          if (input.custom) Object.assign(values, input.custom());
          else values[k] = input.type === 'checkbox' ? input.checked : input.value.trim();
        }
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
const ICON = { glycerol: 'stocks', primer: 'primer', chemical: 'protocol', antibody: 'antibody', material: 'leaf' };   // glyphs
const NAME = { glycerol: 'glycerol stock', primer: 'primer', chemical: 'chemical', antibody: 'antibody', material: 'plant material' };
const NAMES = { glycerol: 'glycerol stocks', primer: 'primers', chemical: 'chemicals', antibody: 'antibodies', material: 'plant material' };
const PLURAL = { glycerol: 'glycerol', primer: 'primers', chemical: 'chemicals', antibody: 'antibodies', material: 'material' };
const SINGULAR = { glycerol: 'glycerol', primers: 'primer', chemicals: 'chemical', antibodies: 'antibody', material: 'material' };
const TITLE = { glycerol: 'Glycerol stocks', primer: 'Primers', chemical: 'Chemicals', antibody: 'Antibodies', material: 'Plant material' };
const SDS = 'SDS';
const FILE_ICONS = { pdf: 'pdf', word: 'doc', powerpoint: 'slides', excel: 'sheet', archive: 'archive', sequence: 'line', text: 'text', image: 'image', file: 'attach' };
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
    const g = this.meta.glycerol;
    for (const [id, list] of [['permits', g.permits], ['plant-markers', g.plant_markers], ['yeast-markers', g.yeast_markers],
      ['mods-5', this.meta.mods['5']], ['mods-3', this.meta.mods['3']]]) {
      document.body.append(el('datalist', { id }, list.map((v) => el('option', { value: v }))));
    }
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
    const record = hash.match(/^(glycerol|primer|chemical|antibody|material)=(.+)$/);
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
      el('span', { class: 'code-badge' }, `${lab.code}-`), ` (${lab.code}-G glycerol stocks, ${lab.code}-O primers, ${lab.code}-C chemicals, ${lab.code}-A antibodies, ${lab.code}-M plant material)`,
      lab.can_change ? el('button', { class: 'btn btn-secondary btn-sm', style: 'margin-left:.6rem', onclick: () => formModal({
        title: 'Choose the lab code',
        intro: 'Every code your lab makes starts with it. Keep it the same as in the Seed Bank. It can be chosen until the lab\'s first stock; after that it is fixed, as codes on labels never change.',
        fields: [{ name: 'code', label: 'Lab code', value: lab.code }],
        submit: async (v) => { this.meta.lab = await api('PUT', '/lab', { ...v, lab: lab.lab }); this.route(); },
      }) }, 'Change…') : null);
  },

  // The lab's chair group: the labs that see each other's stocks. An administrator chooses it, on the suite's dashboard.
  chairLine() {
    const line = el('p', { class: 'lab-code-line chair-line' });
    const lab = this.meta.lab.lab;
    (async () => {
      let c;
      try { c = await api('GET', `/chair?lab=${encodeURIComponent(lab)}`); } catch (e) { return; }
      this.chair = c.group;
      if (c.group) {
        const others = c.group.labs.filter((l) => l.toLowerCase() !== lab.toLowerCase());
        put(line, 'Chair group ', el('b', {}, c.group.name),
          others.length ? `: sees the stocks of ${others.join(', ')}, and they see this lab's` : ': no other lab in it yet');
      }
      if (this.onChair) this.onChair();
    })();
    return line;
  },

  // The copy in eLabJournal's inventory: how far it is, and for the lab admin, connecting it.
  elabLine() {
    const line = el('p', { class: 'lab-code-line elab-line' });
    const lab = this.meta.lab.lab;
    const draw = async () => {
      let s;
      try { s = await api('GET', `/elab?lab=${encodeURIComponent(lab)}`); } catch (e) { return; }
      const settings = s.can_set && s.source !== 'settings' ? el('button', { class: 'btn btn-secondary btn-sm', style: 'margin-left:.6rem',
        onclick: () => this.connectElab(s, draw) }, s.connected ? 'eLab settings…' : [glyph('link'), ' Connect to eLabJournal…']) : null;
      if (!s.connected) {
        if (settings) put(line, 'Keep the lab\'s glycerol stocks and seed lots in eLabJournal\'s inventory too:', settings);
        else put(line);
        return;
      }
      const failed = s.failed.length;
      put(line,
        'Copied to ', el('a', { href: s.url, target: '_blank', rel: 'noopener' }, 'eLabJournal'), ': ',
        `${s.synced} sent`, s.waiting ? `, ${s.waiting} waiting` : '',
        s.held ? el('span', { title: 'Archived in eLab (by someone there): no longer sent, and not made again' }, `, ${s.held} archived in eLab`) : '',
        failed ? el('a', { href: '#', class: 'elab-failed', onclick: (e) => {
          e.preventDefault();
          modal({ title: 'Not copied to eLabJournal', build: (body, close) => body.append(el('ul', {},
            ...s.failed.map((f) => el('li', {}, f.kind === 'seed' ? el('b', {}, f.code)
              : el('a', { href: `#${f.kind}=${f.code}`, onclick: close }, f.code), ` ${f.error}`)))) });
        } }, `, ${failed} failed`) : '',
        s.last_error ? el('span', { class: 'elab-failed' }, ` — ${s.last_error}`) : '',
        s.can_set ? el('button', { class: 'btn btn-secondary btn-sm', style: 'margin-left:.6rem', onclick: async () => {
          try { await api('POST', '/elab/sync', { lab }); } catch (e) { toast(e.message, 'error', 6000); return; }
          toast('Sending to eLabJournal');
          setTimeout(draw, 8000);
        } }, 'Send now') : null,
        s.can_set ? el('button', { class: 'btn btn-secondary btn-sm', style: 'margin-left:.4rem', title: 'Bring over what eLab already has: glycerol stocks, plant material, and seed samples to the Seed Bank',
          onclick: () => this.importElab(s, draw) }, '⇩ Bring over from eLab…') : null,
        settings);
    };
    draw();
    return line;
  },

  // Connecting the lab to eLabJournal, step by step: make a token there, paste it, choose what is copied.
  connectElab(current, done) {
    const lab = current.lab;
    const address = el('input', { type: 'url', value: current.url || current.default_url });
    const token = el('input', { type: 'password', autocomplete: 'off', spellcheck: 'false',
      placeholder: current.connected ? 'Leave empty to keep the token in use' : 'Paste the token here' });
    let found = { sample_types: [], fields: {} };
    const { body, close } = modal({ title: 'Connect to eLabJournal', wide: true, buttons: [], onClose: done });
    const steps = el('div', { class: 'elab-steps' });
    const step = (n, title, ...content) => put(steps,
      el('p', { class: 'elab-step-count' }, `Step ${n} of 3`), el('h3', {}, title), ...content);
    const nav = (...buttons) => el('div', { class: 'elab-nav' }, ...buttons);
    const button = (label, onclick, kind = 'primary') => el('button', { class: `btn btn-${kind}`, type: 'button', onclick: async (ev) => {
      const b = ev.currentTarget;
      b.disabled = true;
      try { await onclick(); } catch (e) { toast(e.message, 'error', 7000); } finally { b.disabled = false; }
    } }, label);
    const where = lab.startsWith('user:') ? 'your own stocks' : `the stocks of ${lab}`;

    const one = () => step(1, 'Make a token in eLab',
      el('p', {}, `Lab Stocks adds the glycerol stocks and seed lots of ${where.replace(/^the stocks of /, '')} to eLab with a token, which you make there once.`),
      el('label', { class: 'field' }, el('span', {}, 'eLab address'), address),
      el('ol', { class: 'elab-howto' },
        el('li', {}, button('Open eLabJournal ↗', () => window.open(address.value.trim() || current.default_url, '_blank', 'noopener'), 'secondary'),
          ' and sign in, in the eLab ', el('b', {}, 'group whose inventory should hold the stocks'), ' (a token works in the group it was made in).'),
        el('li', {}, 'Open ', el('b', {}, 'Apps & Connections'), ' (in your account menu at the top right).'),
        el('li', {}, 'On the ', el('b', {}, 'eLab Mobile App'), ' card, click ', el('b', {}, 'Manage Authentication'),
          '. (The one on the eLabSync card works as well.)'),
        el('li', {}, 'Make a new token, named for example ', el('code', {}, 'Lab Stocks'), ', and copy it. It may be shown only once.')),
      el('p', { class: 'hint' }, 'The token adds and changes samples in eLab as you. You can take it back there at any time, under Manage Authentication.'),
      nav(current.connected ? button('Stop copying…', disconnect, 'danger') : null, el('span', { style: 'flex:1' }),
        button('Cancel', close, 'secondary'), button('I have the token →', two)));

    const two = () => step(2, 'Paste the token',
      el('label', { class: 'field' }, el('span', {}, 'Token'), token),
      el('p', { class: 'hint' }, 'It is tried at once, and kept only in Lab Stocks (and its backups).'),
      nav(button('← Back', one, 'secondary'), el('span', { style: 'flex:1' }), button('Check the token →', async () => {
        found = await api('POST', '/elab/check', { lab, url: address.value, token: token.value });
        toast('eLab accepted the token', 'success');
        three();
      })));

    const three = () => {
      const types = found.sample_types;
      const has = (name) => types.find((t) => t.toLowerCase() === name.toLowerCase());
      const rows = current.all_kinds.map(([kind, standard, title]) => {
        const chosen = has((current.sample_types && current.sample_types[kind]) || standard) || '';
        const tick = el('input', { type: 'checkbox' });
        tick.checked = current.connected ? current.kinds.includes(kind) : !!chosen;
        const select = el('select', {}, el('option', { value: '' }, '— choose —'), ...types.map((n) => el('option', { value: n }, n)));
        select.value = chosen;
        // The lab's permit and biosafety level for them, from the options of the sample type chosen.
        const own = (current.defaults && current.defaults[kind]) || {};
        const picks = {};
        const extra = el('div', { class: 'elab-lab-fields' });
        const drawExtra = () => {
          const fields = found.fields[select.value] || {};
          put(extra, current.lab_fields.filter((f) => f in fields).map((f) => {
            const options = fields[f];
            const input = options.length
              ? el('select', {}, el('option', { value: '' }, '— not set —'), ...options.map((o) => el('option', { value: o }, o)))
              : el('input', { type: 'text' });
            input.value = picks[f] ? picks[f].value : (own[f] || '');
            picks[f] = input;
            return el('label', {}, `${f} `, input);
          }));
        };
        select.addEventListener('change', () => { tick.checked = !!select.value; drawExtra(); });
        drawExtra();
        return { kind, tick, select, picks, row: el('tr', {}, el('td', {}, el('label', {}, tick, ` ${title}`)), el('td', {}, select, extra)) };
      });
      step(3, 'Choose what to copy',
        el('p', {}, 'eLab accepted the token. Each ticked goes to one of the group\'s sample types, in the fields it has: ',
          'nothing is added to them. Choose the permit and biosafety level the lab\'s samples are kept under.'),
        el('table', { class: 'data elab-kinds' }, el('thead', {}, el('tr', {}, el('th', {}, 'Copy'), el('th', {}, 'To sample type in eLab'))),
          el('tbody', {}, ...rows.map((r) => r.row))),
        el('p', { class: 'hint' }, 'Copying goes one way: change glycerol stocks here and seed lots in the Seed Bank, and eLab follows. ',
          'What is used up, discarded or deleted is archived there; changes made in eLab are overwritten by the next change here.'),
        nav(button('← Back', two, 'secondary'), el('span', { style: 'flex:1' }), button(current.connected ? 'Save' : 'Connect and copy', async () => {
          const ticked = rows.filter((r) => r.tick.checked);
          const missing = ticked.find((r) => !r.select.value);
          if (missing) throw new Error('Choose the sample type for each thing ticked');
          const s = await api('PUT', '/elab', { lab, url: address.value, token: token.value, kinds: ticked.map((r) => r.kind),
            sample_types: Object.fromEntries(ticked.map((r) => [r.kind, r.select.value])),
            defaults: Object.fromEntries(ticked.map((r) => [r.kind, Object.fromEntries(Object.entries(r.picks).map(([f, i]) => [f, i.value]))])) });
          put(steps, el('h3', {}, '✓ Connected to eLabJournal'),
            el('p', {}, `The first copy starts now: ${s.waiting} to send. The line above the list says how far it is; `,
              'anything eLab refuses is listed there with the reason.'),
            nav(el('span', { style: 'flex:1' }), button('Close', close)));
        })));
    };

    async function disconnect() {
      if (!steps.querySelector('.elab-confirm')) {
        steps.append(el('p', { class: 'elab-confirm elab-failed' },
          'Stop copying? What is already in eLab stays there, but no longer follows changes here. ',
          button('Yes, stop copying', async () => { await api('DELETE', '/elab', { lab }); toast('No longer copied to eLabJournal'); close(); }, 'danger')));
      }
    }

    body.append(steps);
    one();
  },

  async showList(kind) {
    const main = document.getElementById('main');
    const query = el('input', { type: 'search', class: 'list-search', value: this[`q_${kind}`] || '',
      placeholder: {
        glycerol: 'Search by code, plasmid, clone, strain, selection or place',
        primer: 'Search by code, name, target, place, or a piece of the sequence (e.g. GGCCAGT)',
        chemical: 'Search by code, name, CAS number, room or size',
        antibody: 'Search by code, short code, description, producer, animal, product number or notes',
        material: 'Search by code, name, tissue, species, plant, experiment, who collected it, or where it is',
      }[kind] });
    const table = el('div', { class: 'list' });
    const labelBtn = el('button', { class: 'btn btn-secondary', onclick: () => this.openLabels([...this.selected]) }, glyph('label'), ' Labels for selected');
    // Primers: the ones ticked go on the order list together.
    const tickedPrimers = () => [...this.selected].filter((c) => /-O-\d+$/.test(c));
    const orderBtn = kind === 'primer' ? el('button', { class: 'btn btn-secondary', title: 'Put the ticked primers on the order list, one order each',
      onclick: () => this.orderPrimers(tickedPrimers(), draw) }, glyph('cart'), ' Add selected to order') : null;
    this.onSelection = () => {
      labelBtn.disabled = !this.selected.size;
      labelBtn.replaceChildren(glyph('label'), ` Labels for selected${this.selected.size ? ` (${this.selected.size})` : ''}`);
      if (orderBtn) {
        const n = tickedPrimers().length;
        orderBtn.disabled = !n;
        orderBtn.replaceChildren(glyph('cart'), ` Add selected to order${n ? ` (${n})` : ''}`);
      }
    };
    // The other labs of the chair group: shown on request, remembered.
    let wide = false;
    try { wide = localStorage.getItem('stocks.chairWide') === '1'; } catch (e) { /* no storage */ }
    const wideBox = el('input', { type: 'checkbox', onchange: () => {
      wide = wideBox.checked;
      try { localStorage.setItem('stocks.chairWide', wide ? '1' : '0'); } catch (e) { /* no storage */ }
      draw();
    } });
    wideBox.checked = wide;
    const wideToggle = el('label', { class: 'chair-toggle', hidden: true }, wideBox, ' ');
    this.onChair = () => {
      if (!this.chair || this.chair.labs.length < 2) return;
      put(wideToggle, wideBox, ` Show the stocks of the other labs of ${this.chair.name}`);
      wideToggle.hidden = false;
    };
    const draw = async () => {
      this[`q_${kind}`] = query.value;
      const data = await api('GET', `/${PLURAL[kind]}?q=${encodeURIComponent(query.value)}`);
      put(table, this.listTable(kind, data[PLURAL[kind]].filter((r) => r.mine || wide)));
    };
    let timer;
    query.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(draw, 250); });
    put(main,
      el('div', { class: 'page-head' }, el('h1', {}, glyph(ICON[kind]), ' ', TITLE[kind]),
        el('span', { class: 'actions' },
          el('button', { class: 'btn btn-primary', onclick: () => ({ glycerol: () => this.newGlycerol(), primer: () => this.editPrimer(),
            chemical: () => this.editChemical(), antibody: () => this.editAntibody(), material: () => this.editMaterial() })[kind]() },
          { glycerol: '＋ Glycerol stock', primer: '＋ Primer', chemical: '＋ Chemical', antibody: '＋ Antibody', material: '＋ Tube' }[kind]),
          kind === 'material' ? el('button', { class: 'btn btn-primary', title: 'Many tubes at once: numbered, or a pasted list, and their places in a box',
            onclick: () => this.boxOfTubes() }, glyph('box'), ' Box of tubes…') : null, orderBtn, labelBtn)),
      this.labCodeLine(),
      this.chairLine(),
      this.elabLine(),
      el('p', { class: 'hint' }, {
        glycerol: 'Frozen cultures of the lab\'s plasmids. Confirming a plasmid by sequencing in the Plasmid Editor makes its glycerol stock here, with the next number.',
        primer: 'The lab\'s oligos, with where each tube is. Primers designed in the Plasmid Editor can be saved here, and the editor shows which of them bind a plasmid.',
        chemical: 'The lab\'s chemicals, with the room each is kept in. Open one to add its safety data sheet (SDS).',
        antibody: 'The lab\'s antibodies: primary and secondary, who makes each, the animal it is raised in, and how to use it.',
        material: 'Plant material kept for later processing: a tube each, often a box of them. Link a tube from the notebook by its code; add a whole box at once with Box of tubes.',
      }[kind], kind === 'chemical' ? this.safetyLinks() : null),
      el('div', { class: 'list-tools' }, query, wideToggle), table);
    await draw();
    this.onSelection();
    query.focus();
  },

  pick(code) {
    return el('input', { type: 'checkbox', checked: this.selected.has(code), title: 'Choose for labels',
      onclick: (e) => e.stopPropagation(),
      onchange: (e) => { if (e.target.checked) this.selected.add(code); else this.selected.delete(code); this.onSelection?.(); } });
  },

  /**
   * The header tick of a table's "Choose for labels" boxes: chooses every row the table shows (what
   * a search has left), or none; ticked when all are chosen, half-ticked when some are. It follows
   * the rows' own boxes as they change.
   */
  pickAll(codes) {
    const box = el('input', { type: 'checkbox', title: 'Choose every row shown for labels', 'aria-label': 'Choose every row shown for labels' });
    box.sync = () => {
      const chosen = codes.filter((c) => this.selected.has(c)).length;
      box.checked = chosen > 0 && chosen === codes.length;
      box.indeterminate = chosen > 0 && chosen < codes.length;
    };
    box.addEventListener('click', (e) => e.stopPropagation());
    box.addEventListener('change', () => {
      for (const c of codes) { if (box.checked) this.selected.add(c); else this.selected.delete(c); }
      for (const row of box.closest('table').querySelectorAll('tbody td.pick input')) row.checked = box.checked;
      this.onSelection?.();
    });
    box.sync();
    return box;
  },

  /** A table whose first column chooses rows for labels, with the select-all tick in that column's header. */
  pickTable(head, codes, body) {
    const all = this.pickAll(codes);
    const table = el('table', { class: 'data' },
      el('thead', {}, el('tr', {}, head.map((h, i) => (i === 0 ? el('th', { class: 'pick' }, all) : el('th', {}, h))))),
      body);
    table.addEventListener('change', (e) => { if (e.target !== all && e.target.closest('td.pick')) all.sync(); });
    return table;
  },

  listTable(kind, rows) {
    if (!rows.length) return el('p', { class: 'empty' }, 'Nothing here yet.');
    const head = {
      glycerol: ['', 'Code', 'Plasmid', 'Clone', 'Strain', 'Selection', 'Kept in', 'Made', 'Status'],
      primer: ['', 'Code', 'Name', 'Sequence (5′→3′)', 'nt', 'Tm', 'Kept in', 'Status'],
      chemical: ['', 'Code', 'Name', 'CAS number', 'Room', 'Size', 'SDS', 'Out'],
      antibody: ['', 'Code', 'Short code', 'Description', 'Type', 'Producer', 'Source animal', 'Product number', 'Notes about the use', 'Status'],
      material: ['', 'Code', 'Name', 'Tissue', 'Species / plant', 'Collected', 'Experiment', 'Kept in', 'Status'],
    }[kind];
    const cells = {
      glycerol: (r) => [r.plasmid_name, r.clone, r.host, r.selection, r.location, r.made_on || (r.created_at || '').slice(0, 10),
        r.source === 'sequencing' ? `${r.status} ✓` : r.status],
      primer: (r) => [r.name, el('span', { class: 'mono' }, r.mod5 ? el('span', { class: 'mod-tag' }, r.mod5) : null, r.sequence,
        r.mod3 ? el('span', { class: 'mod-tag' }, r.mod3) : null), r.length, r.tm !== null ? `${r.tm} °C` : '', r.location, [r.status, this.onOrderMark(r)]],
      chemical: (r) => [r.name, el('span', { class: 'mono' }, r.cas), r.room, r.size,
        r.has_sds ? el('span', { title: 'Has its safety data sheet' }, glyph('pdf')) : el('span', { class: 'hint', title: 'No safety data sheet yet' }, '—'),
        [r.status === 'discarded' || !r.mine ? r.status : this.outToggle(r), this.onOrderMark(r)]],
      antibody: (r) => [el('b', {}, r.short_code), r.description, r.type, r.producer, r.host, el('span', { class: 'mono' }, r.product_number),
        el('span', { class: 'clip', title: r.notes }, r.notes), [r.status, this.onOrderMark(r)]],
      material: (r) => [el('b', {}, r.name), r.tissue, [r.species, r.from_plant].filter(Boolean).join(' · '),
        [r.collected_on, r.collected_by].filter(Boolean).join(' · '), r.experiment,
        r.elab_layer_path ? `${r.elab_layer_path.split(' / ').slice(-2).join(' / ')}${r.elab_position ? ` · ${r.elab_position}` : ''}` : r.location, r.status],
    }[kind];
    return this.pickTable(head, rows.map((r) => r.code),
      el('tbody', {}, rows.map((r) => el('tr', { class: `clickable ${r.status !== 'in stock' ? 'faded' : ''}`, onclick: () => { location.hash = `${kind}=${r.code}`; } },
        el('td', { class: 'pick' }, this.pick(r.code)),
        el('td', { class: 'code' }, r.code, r.mine ? null : el('span', { class: 'lab-tag', title: `${r.lab}'s: you see it, ${r.lab} changes it` }, r.lab)),
        cells(r).map((c) => el('td', {}, c))))));
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
      antibody: () => this.antibodyView(rec), material: () => this.materialView(rec) }[kind](), this.elabFact(rec),
      this.files(rec), this.mentions(rec), this.history(rec));
  },

  reload() { this.showRecord(this.rec.kind, this.rec.code); },

  /** Where the record is in eLab: a link to its sample there, and how it stands. */
  elabFact(rec) {
    const e = rec.elab;
    if (!e) return null;
    const link = e.url ? el('a', { href: e.url, target: '_blank', rel: 'noopener', title: 'Open its sample in eLab' }, `sample ${e.sample_id} ↗`) : null;
    const again = e.state === 'archived in eLab' ? el('button', { class: 'btn btn-secondary btn-sm', style: 'margin-left:.5rem',
      title: 'If it was restored in eLab, it goes on following changes there; if not, a new sample is made',
      onclick: async () => {
        try {
          const res = await api('POST', `/${PLURAL[rec.kind]}/${rec.code}/elab-again`);
          toast(res.restored ? 'Restored in eLab: changes go to it again' : 'A new sample is being made in eLab', 'success', 5000);
          setTimeout(() => this.reload(), 4000);
        } catch (err) { toast(err.message, 'error', 6000); }
      } }, 'Send to eLab again') : null;
    const said = {
      sent: ['✓ sent', ''], waiting: ['waiting to be sent', ''], 'not sent': ['not in eLab yet', ''],
      failed: ['not sent', ` (${e.error || 'eLab refused it'})`], archived: ['archived there', ' (used up, discarded or deleted here)'],
      'archived in eLab': ['archived in eLab', ' (by someone there): no longer sent. Restore it there (open it, then Restore), or send it again'],
    }[e.state] || [e.state, ''];
    return el('p', { class: `elab-fact ${e.state === 'failed' ? 'elab-failed' : ''}` }, glyph('link'), ' In eLabJournal: ', link, link ? ' · ' : '', el('b', {}, said[0]), said[1], again);
  },

  head(rec, title, subtitle, actions) {
    return el('div', { class: 'record-head' },
      el('div', {}, el('div', { class: 'crumbs' }, el('a', { href: `#${PLURAL[rec.kind]}` }, glyph(ICON[rec.kind]), ` All ${NAMES[rec.kind]}`)),
        el('h1', {}, el('span', { class: 'code-badge' }, rec.code), ' ', title),
        subtitle ? el('div', { class: 'hint' }, subtitle) : null, this.onOrder(rec)),
      rec.mine ? null : el('p', { class: 'not-mine' }, `${rec.lab}'s, in your chair group: you see it, only ${rec.lab} changes it.`),
      !rec.mine ? el('span', { class: 'actions' }, el('button', { class: 'btn btn-secondary', onclick: () => this.openLabels([rec.code]) }, glyph('label'), ' Label')) :
      el('span', { class: 'actions' }, actions,
        ['glycerol', 'material'].includes(rec.kind) ? null : el('button', { class: 'btn btn-secondary', title: 'Put it on the lab\'s order list, with its details',
          onclick: () => this.orderStock(rec) }, glyph('cart'), ' Add to order'),
        el('button', { class: 'btn btn-secondary', onclick: () => this.openLabels([rec.code]) }, glyph('label'), ' Label'),
        el('button', { class: 'btn btn-secondary', title: 'Delete', onclick: () => modal({
          title: `Delete ${rec.code}?`,
          build: (b) => b.append(el('p', {}, 'Better: set its status to used up or discarded, so its history stays. Deleting removes it from the lists; the code is not given out again.')),
          buttons: [{ label: 'Cancel', kind: 'secondary' }, { label: 'Delete', kind: 'danger', onClick: async () => {
            await api('DELETE', `/${PLURAL[rec.kind]}/${rec.code}`);
            location.hash = PLURAL[rec.kind];
          } }],
        }) }, glyph('trash'))));
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
      { name: 'elab_storage', label: 'Storage location (eLab)', type: 'custom', build: () => this.storagePicker(rec) },
      { name: 'made_on', label: 'Made on', type: 'date', value: rec?.made_on || today() },
      { name: 'status', label: 'Status', type: 'select', options: this.meta.status, value: rec?.status || 'in stock' },
      { name: 'notes', label: 'Notes', type: 'textarea', value: rec?.notes },
      // Biosafety, for the GMO register (and eLab's Glycerol Stock): empty is the lab's, or from the strain.
      { name: 'permit', label: 'Permit', value: rec?.permit, list: 'permits', placeholder: 'empty: the lab\'s (chosen with eLab)' },
      { name: 'biosafety', label: 'Biosafety level', type: 'select', value: rec?.biosafety,
        options: this.meta.glycerol.biosafety.map((v) => [v, v || '— the lab\'s —']) },
      { name: 'host_system', label: 'Host system', type: 'select', value: rec?.host_system,
        options: this.meta.glycerol.host_systems.map((v) => [v, v || '— from the strain —']) },
      { name: 'plant_markers', label: 'Plant markers', value: rec?.plant_markers, list: 'plant-markers', placeholder: 'e.g. BASTA, Hygromycin' },
      { name: 'yeast_markers', label: 'Yeast markers', value: rec?.yeast_markers, list: 'yeast-markers', placeholder: 'e.g. Ura-, Leu-' },
      { name: 'inserts', label: 'Insert(s)?', type: 'select', value: rec?.inserts, options: this.meta.glycerol.yes_no },
      { name: 'gene_ids', label: 'Gene ID(s)', value: rec?.gene_ids, placeholder: 'e.g. AT1G01060' },
      { name: 'donor', label: 'Donor organism(s)', value: rec?.donor, placeholder: 'e.g. Arabidopsis thaliana' },
      { name: 'harmful', label: 'Harmful gene product?', type: 'select', value: rec?.harmful, options: this.meta.glycerol.harmful },
      { name: 'harmful_notes', label: 'Remarks on harmful effects', type: 'textarea', value: rec?.harmful_notes,
        placeholder: 'e.g. toxic, transposase activity' },
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
      wide: true,
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
      ? el('a', { href: editorOpen(rec.plasmid_id), target: '_blank', rel: 'noopener', title: 'Open in the Plasmid Editor' }, glyph('plasmid'), ` ${linked.name || rec.plasmid_name}`)
      : el('span', {}, rec.plasmid_name || '—', ' ', el('span', { class: 'hint warn-text' }, {
        unlinked: '(not linked to a plasmid in the editor)',
        missing: '(no longer in the Plasmid Editor\'s library)',
        other_lab: `(${linked.owner || 'someone'}'s, in another lab, and not public)`,
      }[linked.state] || ''));
    return el('div', {},
      this.head(rec, (linked.name || rec.plasmid_name) + (rec.clone ? ` clone ${rec.clone}` : ''),
        [rec.status, rec.host, rec.location && `kept in ${rec.location}`].filter(Boolean).join(' · '), [
          open ? el('a', { class: 'btn btn-primary', href: editorOpen(rec.plasmid_id), target: '_blank', rel: 'noopener',
            title: 'Open the plasmid in this stock in the Plasmid Editor' }, glyph('plasmid'), ' Open in the Plasmid Editor') : null,
          rec.plasmid_id ? el('a', { class: 'btn btn-secondary', href: `${ST.seeds}/#tree=plasmid:${encodeURIComponent(rec.plasmid_id)}`,
            target: '_blank', rel: 'noopener', title: 'In the Seed Bank: the lines made with this plasmid, their seeds and plants, and the notebook pages about each' },
          glyph('link'), ' Family tree ↗') : null,
          el('button', { class: `btn ${open ? 'btn-secondary' : 'btn-primary'}`, onclick: () => this.linkPlasmid(rec),
            title: open ? 'Link this stock to another plasmid of the editor\'s library' : 'Link this stock to its plasmid in the editor\'s library' },
          glyph('plasmid'), open ? ' Change plasmid…' : ' Link a plasmid…'),
          el('button', { class: 'btn btn-secondary', onclick: () => formModal({
            title: `Edit ${rec.code}`, fields: this.glycerolFields(rec), wide: true,
            submit: async (v) => { await api('PUT', `/glycerol/${rec.code}`, v); this.reload(); },
          }) }, '✎ Edit')]),
      this.facts([
        ['Plasmid', plasmidFact],
        ['Sequencing', open ? el('a', { href: `${ST.editor}/sequencing?sequence=${encodeURIComponent(rec.plasmid_id)}`, target: '_blank', rel: 'noopener' },
          rec.source === 'sequencing' ? '✓ confirmed by sequencing: see the reads' : 'see the reads') : null],
        ['Clone', rec.clone], ['Strain', rec.host], ['Selection', rec.selection], ['Kept in', rec.location],
        ['In eLab\'s storage', rec.elab_layer_path ? `${rec.elab_layer_path}${rec.elab_position ? `, place ${rec.elab_position}` : ''}` : null],
        ['Made on', rec.made_on], ['Status', rec.status], ['Made by', `${rec.created_by || '—'} · ${localTime(rec.created_at)}`]]),
      rec.notes ? el('p', { class: 'description' }, rec.notes) : null,
      this.section('Biosafety', this.facts([
        ['Permit', rec.permit || el('span', { class: 'hint' }, 'the lab\'s')],
        ['Biosafety level', rec.biosafety || el('span', { class: 'hint' }, 'the lab\'s')],
        ['Host system', rec.host_system || el('span', { class: 'hint' }, 'from the strain')],
        ['Plant markers', rec.plant_markers], ['Yeast markers', rec.yeast_markers],
        ['Insert(s)?', rec.inserts], ['Gene ID(s)', rec.gene_ids], ['Donor organism(s)', rec.donor],
        ['Harmful gene product?', rec.harmful], ['Remarks on harmful effects', rec.harmful_notes]])),
      rec.same_plasmid?.length ? this.section('Other stocks of this plasmid', el('div', { class: 'chips' },
        rec.same_plasmid.map((s) => el('a', { class: 'chip', href: `#glycerol=${s.code}` }, glyph('stocks'), ` ${s.code}${s.clone ? ` clone ${s.clone}` : ''} · ${s.status}`)))) : null);
  },

  /**
   * Where a glycerol stock is kept in eLab's storage: one of the group's locations (a freezer's tower, a
   * box, a place in a box), or a new one added there. Gives {node, get}; get() the stock's fields.
   */
  storagePicker(rec) {
    const lab = rec?.lab || this.meta.lab.lab;
    const chosen = { id: rec?.elab_layer_id || '', path: rec?.elab_layer_path || '', position: rec?.elab_position || '' };
    let places = [];
    let kinds = {};
    const node = el('div', { class: 'storage-picker' }, el('span', { class: 'hint' }, 'Asking eLab for its storage…'));
    const filter = el('input', { type: 'search', placeholder: 'Find a location: freezer, tower, box…' });
    const select = el('select', { size: 6 });
    const place = el('input', { type: 'text', placeholder: 'e.g. B3 or 12' });
    const placeRow = el('label', { class: 'storage-place' }, 'Place in the box ', place);
    const label = (p) => p.path.slice(p.unit.length + 3) || '(the whole unit)';
    const at = (id) => places.find((p) => String(p.id) === String(id));
    const draw = () => {
      const q = filter.value.trim().toLowerCase();
      const units = [...new Set(places.map((p) => p.unit))];
      put(select, el('option', { value: '' }, '— none —'), units.map((u) => {
        const shown = places.filter((p) => p.unit === u && (!q || p.path.toLowerCase().includes(q) || String(p.id) === String(chosen.id)));
        return shown.length ? el('optgroup', { label: u }, shown.map((p) => el('option', { value: p.id }, `${p.grid ? '▦ ' : ''}${label(p)}`))) : null;
      }));
      select.value = chosen.id;
      const p = at(chosen.id);
      placeRow.hidden = !(p && p.grid);
      if (p && p.grid) place.placeholder = `1–${p.rows * p.columns}` + (p.lettered ? `, or A1–${String.fromCharCode(64 + p.rows)}${p.columns}` : '');
    };
    filter.addEventListener('input', draw);
    select.addEventListener('change', () => {
      const p = at(select.value);
      chosen.id = select.value;
      chosen.path = p ? p.path : '';
      if (!p || !p.grid) place.value = '';
      draw();
    });
    place.value = chosen.position;

    // A new location in eLab, under the one chosen.
    const name = el('input', { type: 'text', placeholder: 'e.g. Box 12 glycerol stocks' });
    const kind = el('select', {});
    const under = el('span', { class: 'hint' });
    const adder = el('div', { class: 'storage-new', hidden: true }, el('div', {}, 'New location in eLab, under ', under),
      el('label', {}, 'Name ', name), el('label', {}, 'Kind ', kind),
      el('button', { class: 'btn btn-secondary btn-sm', type: 'button', onclick: async (ev) => {
        const b = ev.currentTarget;
        b.disabled = true;
        try {
          const { location: made } = await api('POST', '/elab/locations', { lab, parent: chosen.id, name: name.value, kind: kind.value });
          ({ locations: places, kinds } = await api('GET', `/elab/locations?lab=${encodeURIComponent(lab)}`));
          chosen.id = String(made.id);
          chosen.path = made.path;
          adder.hidden = true;
          name.value = '';
          filter.value = '';
          draw();
          toast(`Added ${made.path} in eLab`, 'success', 4000);
        } catch (e) { toast(e.message, 'error', 7000); } finally { b.disabled = false; }
      } }, 'Add it in eLab'));
    const openAdder = () => {
      const p = at(chosen.id);
      if (!p) { toast('First choose where in eLab the new location goes: a freezer, a tower, a shelf…', 'error', 5000); return; }
      if (p.grid) { toast(`${p.path} is a box with places: choose the tower or shelf it is in`, 'error', 5000); return; }
      const fits = (kinds[p.storage_id] || []).filter((k) => k.level === p.level + 1);
      if (!fits.length) { toast(`${p.unit} has no kind of location under ${label(p)}`, 'error', 5000); return; }
      put(under, p.path);
      put(kind, fits.map((k) => el('option', { value: k.id }, `${k.name}${k.grid ? ` (box, ${k.rows} × ${k.columns})` : ''}`)));
      adder.hidden = false;
      name.focus();
    };

    (async () => {
      let found;
      try { found = await api('GET', `/elab/locations?lab=${encodeURIComponent(lab)}`); } catch (e) {
        put(node, el('span', { class: 'hint' }, `eLab's storage could not be read: ${e.message}`));
        return;
      }
      if (!found.connected) {
        put(node, el('span', { class: 'hint' }, 'Connect the lab to eLabJournal to choose where it is kept there.'));
        return;
      }
      ({ locations: places, kinds } = found);
      if (chosen.id && !at(chosen.id)) places.unshift({ id: chosen.id, path: chosen.path || `eLab location ${chosen.id}`, unit: '(no longer in eLab)', level: 0 });
      draw();
      put(node, filter, select, placeRow,
        el('div', { class: 'storage-actions' },
          el('button', { class: 'btn btn-secondary btn-sm', type: 'button', onclick: openAdder }, '＋ New location under the one chosen…'),
          el('button', { class: 'btn btn-secondary btn-sm', type: 'button', title: 'Read eLab\'s storage again', onclick: async () => {
            ({ locations: places, kinds } = await api('GET', `/elab/locations?lab=${encodeURIComponent(lab)}&refresh=1`));
            draw();
          } }, '↻')),
        adder);
    })();

    return {
      node,
      current: () => at(chosen.id),
      get: () => {
        const p = at(chosen.id);
        let n = '';
        if (p && p.grid && place.value.trim()) {
          const v = place.value.trim().toUpperCase();
          // A place is its number in eLab, counted along the rows; a box with lettered rows also takes B3.
          const m = p.lettered && v.match(/^([A-Z])\s*(\d+)$/);
          n = m ? (m[1].charCodeAt(0) - 65) * p.columns + Number(m[2]) : /^\d+$/.test(v) ? Number(v) : 0;
          if (!(n >= 1 && n <= p.rows * p.columns) || (m && Number(m[2]) > p.columns)) {
            throw new Error(`A place in ${label(p)} is 1 to ${p.rows * p.columns}` + (p.lettered ? `, or A1 to ${String.fromCharCode(64 + p.rows)}${p.columns}` : ''));
          }
        }
        // Not read from eLab (not connected, or eLab away): left as it was.
        if (!places.length) return {};
        return { elab_layer_id: chosen.id, elab_layer_path: chosen.id ? chosen.path : '', elab_position: n ? String(n) : '' };
      },
    };
  },

  /* plant material ------------------------------------------------------------------ */

  materialFields(rec, many = false) {
    if (!document.getElementById('tissues')) {
      document.body.append(el('datalist', { id: 'tissues' }, this.meta.tissues.map((t) => el('option', { value: t }))));
    }
    return [
      ...(many ? [] : [{ name: 'name', label: 'Name (on the tube)', value: rec?.name, placeholder: 'e.g. P130-34 F3' }]),
      { name: 'tissue', label: 'Tissue', value: rec?.tissue, list: 'tissues', placeholder: 'e.g. leaf, flower' },
      { name: 'species', label: 'Species', value: rec?.species, placeholder: 'e.g. Petunia W138' },
      { name: 'from_plant', label: 'From plant', value: rec?.from_plant, placeholder: 'e.g. a Seed Bank plant code, GARD-P-0012' },
      { name: 'description', label: 'Description', value: rec?.description, placeholder: 'e.g. Petunia W138 flower tissue' },
      { name: 'collected_on', label: 'Collected on', type: 'date', value: rec ? rec.collected_on : today() },
      { name: 'collected_by', label: 'Collected by', value: rec ? rec.collected_by : ST.person.username },
      { name: 'experiment', label: 'Experiment', value: rec?.experiment, placeholder: 'e.g. scent time course, day 3' },
      { name: 'location', label: 'Kept in', value: rec?.location, placeholder: 'e.g. −80 °C freezer 1 / box 3' },
      ...(many ? [] : [{ name: 'elab_storage', label: 'Storage location (eLab)', type: 'custom', build: () => this.storagePicker(rec) },
        { name: 'status', label: 'Status', type: 'select', options: this.meta.status, value: rec?.status || 'in stock' }]),
      { name: 'notes', label: 'Notes', type: 'textarea', value: rec?.notes },
    ];
  },

  editMaterial(rec) {
    formModal({
      title: rec ? `Edit ${rec.code}` : 'New tube of plant material', wide: true,
      intro: rec ? null : 'One tube. For a box of them at once, use Box of tubes.',
      fields: this.materialFields(rec),
      submit: async (v) => {
        const res = rec ? await api('PUT', `/material/${rec.code}`, v) : await api('POST', '/material', { ...v, lab: this.chosenLab });
        if (rec) this.reload(); else location.hash = `material=${res.record.code}`;
        toast(rec ? 'Saved' : `Made ${res.record.code}`, 'success');
      },
    });
  },

  materialView(rec) {
    return el('div', {},
      this.head(rec, rec.name, [rec.tissue, rec.species, rec.status].filter(Boolean).join(' · '), [
        el('button', { class: 'btn btn-secondary', onclick: () => this.editMaterial(rec) }, '✎ Edit')]),
      this.facts([['Name on the tube', rec.name], ['Tissue', rec.tissue], ['Species', rec.species], ['From plant', rec.from_plant],
        ['Description', rec.description], ['Collected', [rec.collected_on, rec.collected_by && `by ${rec.collected_by}`].filter(Boolean).join(' ')],
        ['Experiment', rec.experiment], ['Kept in', rec.location],
        ['In eLab\'s storage', rec.elab_layer_path ? `${rec.elab_layer_path}${rec.elab_position ? `, place ${rec.elab_position}` : ''}` : null],
        ['Status', rec.status], ['Added by', `${rec.created_by || '—'} · ${localTime(rec.created_at)}`]]),
      rec.notes ? el('p', { class: 'description' }, rec.notes) : null);
  },

  /** A box of tubes at once: named in a row (L2201-1 … L2201-81) or pasted as a list, filling a box's places in order. */
  boxOfTubes() {
    let picker;
    const tubes = () => {
      const prefix = el('input', { type: 'text', placeholder: 'e.g. L2201-' });
      const from = el('input', { type: 'number', value: 1, min: 0, style: 'width:6rem' });
      const to = el('input', { type: 'number', value: 81, min: 0, style: 'width:6rem' });
      const suffix = el('input', { type: 'text', placeholder: 'e.g. L1', style: 'width:8rem' });
      const pad = el('input', { type: 'number', value: 0, min: 0, max: 6, style: 'width:4rem', title: 'Digits, padded with zeros (0: as they are)' });
      const list = el('textarea', { rows: 6, placeholder: 'One tube a line, e.g. pasted from a spreadsheet:\nP130-34 F3\nP130-34 F4\n… (a second column, after a tab, is its description)' });
      const preview = el('p', { class: 'hint' });
      const mode = { value: 'row' };
      const rowBox = el('div', { class: 'tube-row' }, 'Named ', prefix, el('span', {}, 'number from '), from, el('span', {}, 'to '), to,
        el('span', {}, 'then '), suffix, el('span', {}, 'digits '), pad);
      const listBox = el('div', { hidden: true }, list);
      const names = () => {
        if (mode.value === 'list') {
          return list.value.split('\n').map((l) => l.split('\t')).filter((c) => c[0].trim())
            .map((c) => ({ name: c[0].trim(), ...(c[1] && c[1].trim() ? { description: c[1].trim() } : {}) }));
        }
        const a = Number(from.value), b = Number(to.value), d = Number(pad.value) || 0;
        if (!Number.isFinite(a) || !Number.isFinite(b) || b < a || b - a >= 500) return [];
        return Array.from({ length: b - a + 1 }, (_, i) => ({ name: `${prefix.value}${String(a + i).padStart(d, '0')}${suffix.value}` }));
      };
      const show = () => {
        const n = names();
        put(preview, n.length ? `${n.length} tube${n.length === 1 ? '' : 's'}: ${n.slice(0, 3).map((t) => t.name).join(', ')}${n.length > 3 ? ` … ${n[n.length - 1].name}` : ''}` : 'No tubes yet');
      };
      for (const i of [prefix, from, to, suffix, pad, list]) i.addEventListener('input', show);
      const pick = (m) => { mode.value = m; rowBox.hidden = m !== 'row'; listBox.hidden = m !== 'list'; show(); };
      show();
      return {
        node: el('div', { class: 'tubes' },
          el('div', { class: 'tube-modes' },
            el('label', {}, el('input', { type: 'radio', name: 'tube-mode', checked: true, onchange: () => pick('row') }), ' Numbered'),
            el('label', {}, el('input', { type: 'radio', name: 'tube-mode', onchange: () => pick('list') }), ' Paste a list')),
          rowBox, listBox, preview),
        get: () => ({ _tubes: names() }),
      };
    };
    formModal({
      title: 'A box of tubes', wide: true,
      intro: 'Many tubes of plant material at once. What is filled in below goes on every tube; in a box with places in eLab, they fill its places in order from the one given (or 1).',
      fields: [{ name: 'tubes', label: 'Tubes', type: 'custom', build: tubes }, ...this.materialFields(null, true),
        { name: 'elab_storage', label: 'Storage location (eLab): the box', type: 'custom', build: () => { picker = this.storagePicker(null); return picker; } }],
      label: 'Make the tubes',
      submit: async (v) => {
        const { _tubes: list, elab_layer_id: layer, elab_layer_path: path, elab_position: start, ...shared } = v;
        if (!list.length) throw new Error('Name the tubes: numbered, or a pasted list');
        const box = picker.current();
        const first = Number(start) || 1;
        if (box && box.grid && first + list.length - 1 > box.rows * box.columns) {
          throw new Error(`${list.length} tubes from place ${first} do not fit in ${box.path} (${box.rows * box.columns} places)`);
        }
        const items = list.map((t, i) => ({ ...t, ...(layer ? { elab_layer_id: layer, elab_layer_path: path,
          elab_position: box && box.grid ? String(first + i) : '' } : {}) }));
        const res = await api('POST', '/material/many', { items, shared, lab: this.chosenLab });
        toast(`Made ${res.material.length} tubes: ${res.material[0].code} to ${res.material[res.material.length - 1].code}`, 'success', 5000);
        location.hash = 'material';
        this.route();
      },
    });
  },

  /* bringing over from eLab ----------------------------------------------------------- */

  /** What eLab already has, brought over and linked: its plant material here, its seed samples to the Seed Bank. */
  importElab(status, done) {
    const lab = status.lab;
    const seedsApi = async (method, path, body) => {
      const res = await fetch(`${ST.seeds}/api${path}`, { method, credentials: 'same-origin',
        headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(`Seed Bank: ${data.error || res.status}`);
      return data;
    };
    let kind = 'glycerol';
    let samples = [];
    const owners = el('div', { class: 'import-owners' });
    const where = el('input', { type: 'search', placeholder: 'Only those kept in… e.g. Tower N, Gardiner Lab' });
    const summary = el('p', {});
    const table = el('div', { class: 'import-preview' });
    const progress = el('p', { class: 'hint' });
    const ticked = new Set();
    const chosen = () => samples.filter((s) => ticked.has(s.owner) && (!where.value.trim() || s.path.toLowerCase().includes(where.value.trim().toLowerCase())));
    const groups = (list) => {
      const by = new Map();
      for (const s of list) {
        const key = (s.note || s.name).slice(0, 200);
        if (!by.has(key)) by.set(key, []);
        by.get(key).push(s);
      }
      return by;
    };
    const draw = () => {
      const list = chosen();
      put(summary, {
        seed: `${list.length} seed samples → ${groups(list).size} lines in the Seed Bank (one per cross or note), each sample a seed lot`,
        material: `${list.length} samples → ${list.length} tubes of plant material here, in their places in eLab's storage`,
        glycerol: `${list.length} samples → ${list.length} glycerol stocks here, in their places in eLab's storage, each linked to the plasmid of its name in the Plasmid Editor when there is one`,
      }[kind]);
      const cols = { seed: ['Note (the line)', 'Species', (s) => s.note, (s) => s.species],
        material: ['Description', 'Note', (s) => s.description, (s) => s.note],
        glycerol: ['Strain', 'Selection', (s) => s.strain, (s) => s.selection] }[kind];
      put(table, list.length ? el('table', { class: 'data' },
        el('thead', {}, el('tr', {}, ['eLab name', 'Owner', cols[0], cols[1], 'Kept in'].map((h) => el('th', {}, h)))),
        el('tbody', {}, list.slice(0, 12).map((s) => el('tr', {}, el('td', { class: 'code' }, s.name), el('td', {}, s.owner),
          el('td', {}, cols[2](s)), el('td', {}, cols[3](s)),
          el('td', {}, `${s.path.split(' / ').slice(-2).join(' / ')}${s.position ? ` · ${s.position}` : ''}`)))),
        list.length > 12 ? el('tfoot', {}, el('tr', {}, el('td', { colspan: 5, class: 'hint' }, `… and ${list.length - 12} more`))) : null) : null);
    };
    where.addEventListener('input', draw);
    let asked = 0;
    const load = async (refresh = false) => {
      const mine = ++asked;          // only the latest answer counts, should the choice change meanwhile
      put(summary, 'Asking eLab… (with thousands of samples in the group, this can take a minute)');
      put(owners);
      put(table);
      const found = await api('GET', `/elab/import?lab=${encodeURIComponent(lab)}&kind=${kind}${refresh ? '&refresh=1' : ''}`);
      if (mine !== asked) return;
      samples = found.samples;
      ticked.clear();
      // Everyone owning any there, also those whose samples are all here already (nothing to tick).
      put(owners, el('span', { class: 'hint' }, 'Owned in eLab by: '), found.owners.map(([o, n, here]) => el('label', {
        class: `chip ${n ? '' : 'chip-done'}`, title: n ? `${n} not here yet${here ? `, ${here} brought over already` : ''}` : `All ${here} brought over already: nothing to bring` },
        el('input', { type: 'checkbox', disabled: !n, checked: ticked.has(o), onchange: (e) => { if (e.target.checked) ticked.add(o); else ticked.delete(o); draw(); } }),
        ` ${o || '(nobody)'} (${n ? n : `all ${here} here`}${n && here ? `, ${here} here` : ''})`)));
      draw();
    };
    const run = async () => {
      const list = chosen();
      if (!list.length) throw new Error('Choose whose samples to bring over');
      if (kind === 'glycerol') {
        put(progress, `Bringing over ${list.length} glycerol stocks…`);
        const res = await api('POST', '/elab/import/glycerol', { lab, ids: list.map((s) => s.id) });
        toast(`Brought over ${res.made} glycerol stocks, linked to eLab${res.plasmids ? `; ${res.plasmids} linked to their plasmid` : ''}`, 'success', 6000);
      } else if (kind === 'material') {
        put(progress, `Bringing over ${list.length} tubes…`);
        const res = await api('POST', '/elab/import/material', { lab, ids: list.map((s) => s.id) });
        toast(`Brought over ${res.made} tubes of plant material, linked to eLab`, 'success', 6000);
      } else {
        const existing = new Map((await seedsApi('GET', '/lines')).lines.filter((l) => l.lab === lab).map((l) => [l.name, l]));
        let lots = 0;
        let n = 0;
        for (const [name, members] of groups(list)) {
          n += 1;
          put(progress, `Line ${n} of ${groups(list).size}: ${name}`);
          let line = existing.get(name);
          if (!line) {
            line = (await seedsApi('POST', '/lines', { name, lab, species: members[0].species || '',
              kind: /\bx\b/i.test(name) ? 'cross' : 'other', description: `Brought over from eLab (${members.length} seed samples).` })).record;
            existing.set(name, line);
          }
          const pairs = [];
          for (const s of members) {
            const lot = (await seedsApi('POST', '/lots', { line: line.code, source: `eLab ${s.name}`, location: s.path,
              notes: [s.description, s.note !== name ? s.note : ''].filter(Boolean).join('\n') })).record;
            pairs.push({ code: lot.code, sample_id: s.id, name: s.name });
          }
          lots += (await api('POST', '/elab/adopt', { lab, pairs })).linked;
        }
        toast(`Brought over ${lots} seed lots in ${n} lines to the Seed Bank, linked to eLab`, 'success', 6000);
      }
      put(progress);
      await load(true);
    };
    const kindPick = el('select', { onchange: (e) => { kind = e.target.value; load().catch((err) => put(summary, err.message)); } },
      el('option', { value: 'glycerol' }, 'Glycerol stocks → Lab Stocks'), el('option', { value: 'material' }, 'Plant material → Lab Stocks'),
      el('option', { value: 'seed' }, 'Seed samples → the Seed Bank'));
    const go = el('button', { class: 'btn btn-primary', type: 'button', onclick: async () => {
      go.disabled = true;
      try { await run(); } catch (e) { toast(e.message, 'error', 8000); put(progress); } finally { go.disabled = false; }
    } }, 'Bring them over');
    modal({ title: 'Bring over from eLabJournal', wide: true, onClose: done, buttons: [{ label: 'Close', kind: 'secondary' }],
      build: (body) => body.append(
        el('p', { class: 'hint' }, 'eLab\'s samples not yet linked to a record here. Each one brought over is linked to its sample in eLab, ',
          'which keeps its name; after that it follows changes made here, as other stocks do.'),
        el('label', { class: 'field' }, el('span', { class: 'field-label' }, 'What'), kindPick),
        owners, el('label', { class: 'field' }, where), summary, table, progress, el('div', { class: 'elab-nav' }, el('span', { style: 'flex:1' }), go)) });
    load().catch((err) => put(summary, err.message));
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
        { name: 'mod5', label: '5′ modification', value: rec?.mod5, list: 'mods-5', placeholder: 'none; e.g. Phosphate, 6-FAM, Biotin' },
        { name: 'mod3', label: '3′ modification', value: rec?.mod3, list: 'mods-3', placeholder: 'none; e.g. BHQ-1, Phosphate, Inverted dT' },
        { name: 'modifications', label: 'Other modifications', value: rec?.modifications, placeholder: 'e.g. internal dT-FAM at 12, phosphorothioate bonds' },
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
        el('div', {}, el('span', { class: 'hint' }, "5′ "), rec.mod5 ? el('span', { class: 'mod-tag', title: '5′ modification' }, rec.mod5) : null,
          el('span', { class: 'mono big' }, rec.sequence), rec.mod3 ? el('span', { class: 'mod-tag', title: '3′ modification' }, rec.mod3) : null,
          el('span', { class: 'hint' }, " 3′"),
          el('button', { class: 'btn btn-secondary btn-sm', onclick: async () => {
            if (await copyText(rec.sequence)) toast('Copied', 'success', 1500);
            else toast('Copying is blocked here: select the sequence and copy it', 'error', 4000);
          } }, 'Copy')),
        el('div', { class: 'hint' }, 'Reverse complement: ', el('span', { class: 'mono' }, revcomp(rec.sequence)))),
      this.facts([['Length', `${rec.length} nt`], ['GC', `${rec.gc}%`], ['Tm', rec.tm !== null ? `${rec.tm} °C (nearest neighbour, 50 mM Na⁺, 250 nM primer)` : null],
        ['Direction', rec.direction], ['Target', rec.target], ['Purpose', rec.purpose],
        ['5′ modification', rec.mod5], ['3′ modification', rec.mod3], ['Other modifications', rec.modifications],
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
        title: 'Utrecht University\'s register of hazardous substances (SOFOS)' }, glyph('shield'), ' SOFOS ↗'),
      el('a', { class: 'btn btn-secondary btn-sm', href: ST.chemwatch, target: '_blank', rel: 'noopener',
        title: cas ? `Chemwatch: search it for CAS ${cas}` : 'Chemwatch' }, glyph('hazard'), ' Chemwatch ↗'));
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
          sds ? el('span', {}, el('a', { class: 'btn btn-primary', href: fileUrl(sds.id), target: '_blank', rel: 'noopener' }, glyph('pdf'), ' Open the SDS'),
            el('span', { class: 'hint' }, ` ${sds.filename} · ${sizeLabel(sds.size)} · added by ${sds.created_by || '—'} ${localTime(sds.created_at)}`))
            : el('span', { class: 'hint' }, 'No safety data sheet yet. '),
          !rec.mine ? null : el('label', { class: `btn ${sds ? 'btn-secondary' : 'btn-primary'} btn-sm` }, sds ? 'Replace the SDS…' : [glyph('pdf'), ' Add the SDS (PDF)…'], sdsInput)),
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
    return el('div', { class: 'on-order' }, el('a', { href: '#orders' }, glyph('cart'), ' On the order list'), ': ',
      o.status === 'ordered' ? `ordered ${localTime(o.ordered_at).slice(0, 10)}, waiting for it to arrive`
        : `asked for by ${o.requested_by || '—'} ${localTime(o.requested_at).slice(0, 10)}${o.auto ? ' (marked out)' : ''}, not ordered yet`);
  },

  onOrderMark(r) {
    return r.on_order ? el('span', { class: 'on-order-mark', title: 'On the order list' }, ' ', glyph('cart')) : null;
  },

  /** The primers ticked in the list, on the order list at once: one order each, with the same amount and note. */
  orderPrimers(codes, redraw) {
    if (!codes.length) { toast('Tick the primers to order', 'error'); return; }
    formModal({
      title: `Order ${codes.length} primer${codes.length === 1 ? '' : 's'}`,
      intro: `${codes.join(', ')} go on the lab's order list, each with its sequence; the lab admin orders them. Primers on the list already are not added again.`,
      fields: [
        { name: 'quantity', label: 'How much of each', placeholder: 'e.g. 25 nmol, desalted' },
        { name: 'notes', label: 'Note for the lab admin', type: 'textarea', placeholder: 'e.g. for the Golden Gate assembly' },
        { name: 'urgent', label: 'Urgent', type: 'checkbox' },
      ],
      label: [glyph('cart'), ' Add to order'],
      submit: async (v) => {
        const res = await api('POST', '/orders/many', { ...v, records: codes });
        const n = res.made.length;
        toast(`${n} primer${n === 1 ? '' : 's'} on the order list${res.already.length ? `; ${res.already.length} already ${res.already.length === 1 ? 'was' : 'were'}` : ''}`, 'success', 4000);
        for (const c of codes) this.selected.delete(c);
        this.refreshWaiting();
        await redraw();
        this.onSelection?.();
      },
    });
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
      label: [glyph('cart'), ' Add to order'],
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
      intro: `Ask for anything the lab needs: enzymes, kits, consumables, chemicals.${labs.length > 1 ? ` It goes to ${this.meta.lab.lab}'s lab admin (choose another lab at the top).` : ' The lab admin orders it.'} For a chemical, primer or antibody the lab already has, use Add to order on its page instead: its details come along.`,
      fields: this.orderFields(null),
      label: [glyph('cart'), ' Send the request'],
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
    if (o.can_handle && o.status === 'ordered') out.push(el('button', { class: 'btn btn-primary btn-sm', onclick: stop(() => this.setOrder(o, { status: 'received' }, `${o.item}: received${o.record_code ? `; ${o.record_code} is in stock` : ''}`)) }, glyph('box'), ' Received'));
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
      put(table, this.ordersTable(data.orders));
    };
    let timer;
    query.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(draw, 250); });
    filter.addEventListener('change', draw);
    put(main,
      el('div', { class: 'page-head' }, el('h1', {}, glyph('cart'), ' Orders'),
        el('span', { class: 'actions' }, el('button', { class: 'btn btn-primary', onclick: () => this.orderRequest() }, '＋ Order request'),
          handles.length ? sheet : null)),
      el('p', { class: 'hint' }, handles.length
        ? `You order for ${handles.join(', ')}: these are the lab's requests, from the request form, Add to order on a chemical, primer or antibody, and chemicals switched to Out. Mark each ✓ Ordered when you have ordered it, and Received when it arrives; a stock that had run out is then back in stock. Orders of the other labs of your chair group are shown too, marked with their lab; their own lab admins order them.`
        : 'Ask for what the lab needs with ＋ Order request, or Add to order on a chemical, primer or antibody; a chemical switched to Out is added by itself. Your lab admin orders it. These are the orders of your lab, and of the other labs of its chair group (marked with their lab), and how far each has got.'),
      el('div', { class: 'list-tools' }, filter, query), table);
    await draw();
  },

  ordersTable(rows) {
    if (!rows.length) return el('p', { class: 'empty' }, 'No orders here.');
    const STATUS_LABEL = { requested: 'to order', ordered: 'ordered', received: 'received', cancelled: 'cancelled' };
    return el('table', { class: 'data orders' },
      el('thead', {}, el('tr', {}, ['#', 'What', 'Kind', 'How much', 'Supplier', 'Product number', 'Asked by', 'Status', ''].map((h) => el('th', {}, h)))),
      el('tbody', {}, rows.map((o) => el('tr', { class: `clickable ${['received', 'cancelled'].includes(o.status) ? 'faded' : ''}`, onclick: () => this.openOrder(o) },
        el('td', { class: 'code' }, o.id),
        el('td', {}, o.urgent ? el('span', { class: 'urgent', title: 'Urgent' }, glyph('alert'), ' ') : null, el('b', {}, o.item),
          o.own_lab ? null : el('span', { class: 'lab-tag', title: `${o.lab}'s order, in your chair group: ${o.lab}'s lab admin orders it` }, o.lab),
          o.record_code ? [' ', el('a', { class: 'code-badge', href: `#${o.record_kind}=${o.record_code}`, onclick: (e) => e.stopPropagation() }, o.record_code)] : null,
          o.details ? el('div', { class: 'hint clip' }, o.details) : null,
          o.notes ? el('div', { class: 'hint clip', title: o.notes }, `“${o.notes}”`) : null),
        el('td', {}, o.category), el('td', {}, o.quantity),
        el('td', {}, o.link ? el('a', { href: o.link, target: '_blank', rel: 'noopener noreferrer', onclick: (e) => e.stopPropagation() }, `${o.supplier || 'link'} ↗`) : o.supplier),
        el('td', {}, el('span', { class: 'mono' }, o.product_number)),
        el('td', {}, `${o.requested_by || '—'} · `, localTime(o.requested_at).slice(0, 10), o.auto ? el('span', { class: 'hint', title: 'Added on marking the chemical out' }, ' (out)') : null,
          this.meta.orders.handles.length > 1 && o.own_lab ? el('div', { class: 'hint' }, o.lab) : null),
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
        el('span', { class: 'file-icon' }, glyph(FILE_ICONS[a.kind] || 'attach')), el('a', { href: fileUrl(a.id), target: '_blank', rel: 'noopener' }, a.filename),
        el('span', { class: 'hint' }, ` ${sizeLabel(a.size)} · ${a.created_by || ''}`)))) : null,
      rec.mine ? el('label', { class: 'btn btn-secondary btn-sm' }, glyph('attach'), ' Add photos or files…',
        el('input', { type: 'file', multiple: true, hidden: true, onchange: (e) => this.upload(rec, [...e.target.files]) })) : null);
    zone.addEventListener('dragover', (e) => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); zone.classList.add('drop'); } });
    zone.addEventListener('dragleave', () => zone.classList.remove('drop'));
    zone.addEventListener('drop', (e) => { e.preventDefault(); zone.classList.remove('drop'); if (rec.mine) this.upload(rec, [...e.dataTransfer.files]); });
    return this.section(`Photos and files (${list.length})`, zone);
  },

  mentions(rec) {
    if (!rec.mentions?.length) return null;
    return this.section('In the lab notebook', el('ul', { class: 'plain' }, rec.mentions.map((m) => el('li', {},
      el('a', { href: `${ST.notebook}/#note=${m.id}`, target: '_blank', rel: 'noopener' }, glyph('notebook'), ` ${m.title}`),
      el('span', { class: 'hint' }, m.owner ? ` · ${m.owner}` : ' · protocol library')))));
  },

  history(rec) {
    return el('details', { class: 'history' }, el('summary', {}, `History (${rec.changes.length})`),
      el('ul', { class: 'plain' }, rec.changes.map((c) => el('li', {}, el('span', { class: 'hint' }, `${localTime(c.changed_at)} · ${c.changed_by || '—'}: `), c.what))));
  },
};

document.addEventListener('DOMContentLoaded', () => App.init());
