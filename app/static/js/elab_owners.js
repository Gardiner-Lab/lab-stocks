/*
 * Which lab each of eLab's owners belongs to.
 *
 * A shared eLab group holds several labs' samples, and whoever made a sample there decides whose stock
 * it becomes here. This screen is the list: every owner the stocks already name, how many are theirs,
 * and the lab to file their next ones under. It is a tab of the suite's dashboard (suite-manifest.json)
 * and also stands on its own at /elab-owners.
 */
const base = window.location.pathname.replace(/\/elab-owners\/?$/, '');
const $ = (id) => document.getElementById(id);

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'text') node.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c === undefined || c === null || c === false) continue;
    node.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

async function api(method, path, body) {
  const res = await fetch(`${base}/api${path}`, {
    method,
    credentials: 'same-origin',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Lab Stocks: ${res.status}`);
  return data;
}

// A lab as the lab writes it: a stock kept by someone in no lab is their own, not "user:someone".
const labName = (lab) => (lab.startsWith('user:') ? `${lab.slice(5)}'s own stocks` : lab);

// The same corner toast the rest of Lab Stocks uses, so a message looks the same wherever it appears.
function say(message, kind) {
  let shelf = document.querySelector('.toasts');
  if (!shelf) document.body.append(shelf = el('div', { class: 'toasts' }));
  const note = el('div', { class: `toast toast-${kind}` }, message);
  shelf.append(note);
  setTimeout(() => note.remove(), kind === 'error' ? 7000 : 5000);
}

async function draw() {
  const box = $('ownerLabs');
  let state;
  try {
    state = await api('GET', '/elab/owner-labs');
  } catch (err) {
    box.replaceChildren(el('p', { class: 'hint' }, err.message));
    return;
  }
  const { owner_labs: placed, owners, labs } = state;
  if (!owners.length) {
    box.replaceChildren(el('p', { class: 'hint' },
      'No stock here names an owner in eLab yet. Bring some over and they will be listed.'));
    return;
  }
  const chosen = {};
  const rows = owners.map((o) => {
    const pick = el('select', {}, el('option', { value: '' }, '— stays with the lab bringing it over —'),
      ...labs.map((l) => el('option', { value: l }, l)));
    pick.value = placed[o.owner] || '';
    chosen[o.owner] = pick;
    return el('tr', {},
      el('td', {}, el('b', {}, o.owner)),
      el('td', { class: 'num' }, String(o.stocks)),
      el('td', { class: 'hint' }, o.labs.map(labName).join(', ')),
      el('td', {}, pick));
  });
  const save = el('button', { class: 'btn btn-primary btn-sm', type: 'button', onclick: async () => {
    save.disabled = true;
    try {
      const wanted = Object.fromEntries(Object.entries(chosen).map(([o, s]) => [o, s.value]));
      const res = await api('PUT', '/elab/owner-labs', { owner_labs: wanted });
      const n = Object.keys(res.owner_labs).length;
      say(`Saved. ${n} ${n === 1 ? 'person is' : 'people are'} placed in a lab.`, 'success');
    } catch (err) {
      say(err.message, 'error');
    } finally {
      save.disabled = false;
    }
  } }, 'Save');

  box.replaceChildren(
    el('table', { class: 'data' },
      el('thead', {}, el('tr', {},
        el('th', {}, 'Owner in eLab'),
        el('th', { class: 'num' }, 'Stocks here'),
        el('th', {}, 'Filed under now'),
        el('th', {}, 'Their lab'))),
      el('tbody', {}, rows)),
    el('div', { class: 'elab-nav', style: 'margin-top:.8rem' }, el('span', { style: 'flex:1' }), save));
}

draw();
