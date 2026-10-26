"""
Copies the lab's glycerol stocks, and its seed lots from the Seed Bank, to
eLabJournal's inventory, one way: Lab Stocks and the Seed Bank are where they
are changed, and eLab follows.

The eLab group is usually shared (a chair group's), with sample types of its
own, so nothing is added to them: a glycerol stock becomes a sample of the
group's Glycerol Stock type, a seed lot one of its Plant Seed type, their values
in the fields those types have (strain in 'Name of host strain', a seed lot's
mother plant in 'Mother plant', ...), and only values eLab offers for a field
with options. Each sample is named by its code and name, with its code as
eLab's alternative id; the Permit and Biosafety level are the lab's, chosen when
connecting. A stock used up, discarded or deleted, or a seed lot used up or
deleted, is archived in eLab. Anything changed in eLab is overwritten by the
next change here; a sample archived in eLab is left so (sent no more, never made
again), and one this account may not change (someone else's) is listed as failed.

A lab is connected by its lab admin, on the stocks page (Connect to
eLabJournal): the eLab address, an API token made in eLab (Apps & Connections >
Manage Authentication) by someone in the eLab group, what is copied, to which
sample types, and the permit and biosafety level. That is kept in
elab_settings. Without it, a lab follows the settings below, when set:

    ELAB_URL            e.g. https://uu.elabjournal.com
    ELAB_TOKEN          the API token
    ELAB_LABS           the suite labs copied, comma-separated (default: every lab)
    ELAB_KINDS          default glycerol,seed
    ELAB_SAMPLE_TYPES   other sample type names, e.g. seed=Seeds
    ELAB_INTERVAL       seconds between rounds (default 120)
    ELAB_HOSTS          the hosts a lab may connect to (default elabjournal.com,elabnext.com and their subdomains)

A glycerol stock can be kept in one of the group's storage locations in eLab
(a compartment of a storage unit: a freezer's tower, a box, a place in a box),
chosen in its form from what eLab has, or added there from the form; its sample
is placed there.

A thread in the app compares every glycerol stock and seed lot with what was
last sent, every ELAB_INTERVAL seconds and straight after a change here (seed
lots, changed in the Seed Bank, at the next round), and sends what differs.
"""

import contextlib
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.db import connect

# What is copied: its kind here, the eLab sample type it goes to, and what it is called.
SAMPLE_TYPES = {'glycerol': 'Glycerol Stock', 'material': 'Plant Material', 'seed': 'Plant Seed'}
TITLES = {'glycerol': 'Glycerol stocks', 'material': 'Plant material', 'seed': 'Seed lots (from the Seed Bank)'}
# The lab's own values, chosen when connecting, for fields of these names.
LAB_FIELDS = ('Permit', 'Biosafety level')
RETRY_AFTER = 600            # seconds before a record that failed is tried again unchanged
DEFAULT_URL = 'https://uu.elabjournal.com'

_state: Dict[str, Any] = {'last_run': None, 'errors': {}, 'running': False}
_wake = threading.Event()
_lock = threading.Lock()
_thread: Optional[threading.Thread] = None


class ElabError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f'eLab answered {status}: {message}' if status else message)
        self.status = status


# --- where each lab's stocks go ----------------------------------------------------

@dataclass
class Connection:
    url: str
    token: str
    kinds: List[str]
    sample_types: Dict[str, str] = field(default_factory=dict)
    defaults: Dict[str, Dict[str, str]] = field(default_factory=dict)   # kind -> {Permit: ..., Biosafety level: ...}
    source: str = 'lab'                 # 'lab': chosen on the stocks page; 'settings': the installation's ELAB_ settings
    set_by: Optional[str] = None
    set_at: Optional[str] = None

    def type_name(self, kind: str) -> str:
        return (self.sample_types.get(kind) or '').strip() or SAMPLE_TYPES[kind]


def _env_connection(lab: str) -> Optional[Connection]:
    url, token = os.environ.get('ELAB_URL', '').strip(), os.environ.get('ELAB_TOKEN', '').strip()
    chosen = {c.strip().casefold() for c in os.environ.get('ELAB_LABS', '').split(',') if c.strip()}
    if not (url and token) or (chosen and lab.casefold() not in chosen):
        return None
    kinds = [k.strip() for k in os.environ.get('ELAB_KINDS', '').split(',') if k.strip() in SAMPLE_TYPES]
    types = {}
    for pair in os.environ.get('ELAB_SAMPLE_TYPES', '').split(','):
        k, _, name = pair.partition('=')
        if k.strip() in SAMPLE_TYPES and name.strip():
            types[k.strip()] = name.strip()
    return Connection(url.rstrip('/'), token, kinds or list(SAMPLE_TYPES), types, source='settings')


def connection(lab: str) -> Optional[Connection]:
    """Where this lab's stocks are copied: chosen by its lab admin, else the installation's settings; or nowhere."""
    with connect() as conn:
        row = conn.execute('SELECT * FROM elab_settings WHERE lab = ? COLLATE NOCASE', (lab,)).fetchone()
    if row:
        return Connection(row['url'], row['token'], [k for k in json.loads(row['kinds']) if k in SAMPLE_TYPES],
                          json.loads(row['sample_types'] or '{}'), json.loads(row['defaults'] or '{}'),
                          set_by=row['set_by'], set_at=row['set_at'])
    return _env_connection(lab)


def clean_url(url: str) -> str:
    """An eLab address a lab may connect to: https, on an eLab host (not anything the server can reach)."""
    raw = (url or '').strip()
    parsed = urllib.parse.urlparse(raw if '://' in raw else 'https://' + raw)
    host = (parsed.hostname or '').lower()
    hosts = [h.strip().lower().lstrip('.') for h in os.environ.get('ELAB_HOSTS', 'elabjournal.com,elabnext.com').split(',')
             if h.strip()]
    if parsed.scheme != 'https' or not any(host == h or host.endswith('.' + h) for h in hosts):
        raise ValueError(f"That is not an eLab address: it is written like {DEFAULT_URL}")
    return f'https://{host}' + (f':{parsed.port}' if parsed.port else '')


def check(url: str, token: str, opener=None) -> dict:
    """
    Tries a token: gives the sample types eLab has for it, and for each the options of its Permit and
    Biosafety level fields; or says what is wrong.
    """
    token = (token or '').strip()
    if not token:
        raise ValueError('Paste the token made in eLab')
    client = Client(clean_url(url), token, opener)
    try:
        types = [t for t in _items(client.call('GET', '/sampleTypes', query={'$records': 1000}))
                 if t.get('name') and not t.get('deleted')]
        fields = {}
        for t in types:
            metas = _items(client.call('GET', f"/sampleTypes/{t['sampleTypeID']}/meta", query={'$records': 1000}))
            fields[t['name'].strip()] = {m['key'].strip(): m.get('optionValues') or [] for m in metas
                                         if str(m.get('key', '')).strip() in LAB_FIELDS}
    except ElabError as exc:
        if exc.status in (401, 403):
            raise ValueError('eLab did not accept that token: copy it again, the whole of it') from exc
        raise ValueError(str(exc)) from exc
    return {'sample_types': sorted(fields, key=str.casefold), 'fields': fields}


def save(lab: str, by: str, data: dict, opener=None) -> Connection:
    """Connects the lab, after trying the token (kept as it was when none is given and the address is the same)."""
    url = clean_url(data.get('url') or '')
    token = str(data.get('token') or '').strip()
    old = connection(lab)
    if not token and old and old.source == 'lab' and old.url == url:
        token = old.token
    found = check(url, token, opener)
    kinds = [k for k in SAMPLE_TYPES if k in (data.get('kinds') or [])]
    if not kinds:
        raise ValueError('Choose at least one thing to copy')
    names = data.get('sample_types') or {}
    types = {}
    for k in kinds:
        name = str(names.get(k) or SAMPLE_TYPES[k]).strip()
        match = next((t for t in found['sample_types'] if t.casefold() == name.casefold()), None)
        if match is None:
            raise ValueError(f'eLab has no sample type called {name}: choose one it has')
        types[k] = match
    given = data.get('defaults') or {}
    defaults = {k: {f: str((given.get(k) or {}).get(f) or '').strip()[:100] for f in LAB_FIELDS} for k in kinds}
    with connect() as conn:
        conn.execute('INSERT OR REPLACE INTO elab_settings (lab, url, token, kinds, sample_types, defaults, set_by, set_at) '
                     'VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)',
                     (lab, url, token, json.dumps(kinds), json.dumps(types), json.dumps(defaults), by))
    _state['errors'].pop(lab, None)
    nudge()
    return connection(lab)


def remove(lab: str) -> None:
    """Stops copying the lab's stocks: what is in eLab stays there."""
    with connect() as conn:
        conn.execute('DELETE FROM elab_settings WHERE lab = ? COLLATE NOCASE', (lab,))
    _state['errors'].pop(lab, None)


# --- eLab's API ------------------------------------------------------------------

class Client:
    """eLabJournal's REST API (/api/v1), with an API token."""

    def __init__(self, url: str, token: str, opener=None):
        self.base = url.rstrip('/') + '/api/v1'
        self.token = token
        self.opener = opener or urllib.request.urlopen

    def call(self, method: str, path: str, body: Any = None, query: Optional[dict] = None) -> Any:
        url = self.base + path + ('?' + urllib.parse.urlencode(query) if query else '')
        data = None if body is None else json.dumps(body).encode()
        for attempt in range(4):
            req = urllib.request.Request(url, data=data, method=method, headers={
                'Authorization': self.token, 'Accept': 'application/json',
                **({'Content-Type': 'application/json; charset=utf-8'} if data is not None else {})})
            try:
                with self.opener(req, timeout=30) as response:
                    text = response.read().decode('utf-8', 'replace')
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < 3:         # 50 calls a second at most
                    time.sleep(1 + attempt)
                    continue
                detail = exc.read().decode('utf-8', 'replace')[:300]
                try:
                    detail = json.loads(detail).get('message') or detail
                except (ValueError, AttributeError):
                    pass
                raise ElabError(exc.code, detail or exc.reason)
            except (urllib.error.URLError, OSError) as exc:
                raise ElabError(0, f'eLab could not be reached: {exc}')
        if not text.strip():
            return None
        try:
            return json.loads(text)
        except ValueError:
            return text


def _items(found: Any) -> List[dict]:
    """A list from eLab: as it is, or the data of one page of it."""
    if isinstance(found, dict):
        found = found.get('data') or []
    return [f for f in found or [] if isinstance(f, dict)]


@dataclass
class SampleType:
    id: int
    fields: Dict[str, Tuple[int, str, str, List[str]]]   # name folded -> (sampleTypeMetaID, its name, sampleDataType, options)


def sample_type(client: Client, name: str) -> SampleType:
    """The group's sample type of this name, and its fields. It is not made, nor are fields added to it."""
    found = [t for t in _items(client.call('GET', '/sampleTypes', query={'name': name, '$records': 1000}))
             if str(t.get('name', '')).strip().casefold() == name.casefold() and not t.get('deleted')]
    if not found:
        raise ElabError(0, f'eLab has no sample type called {name}: choose another in eLab settings')
    type_id = int(found[0]['sampleTypeID'])
    metas = _items(client.call('GET', f'/sampleTypes/{type_id}/meta', query={'$records': 1000}))
    return SampleType(type_id, {_fold(m.get('key')):
                                (int(m['sampleTypeMetaID']), m.get('key'), m.get('sampleDataType') or 'TEXT',
                                 m.get('optionValues') or []) for m in metas if m.get('sampleTypeMetaID')})


def _fold(name: Any) -> str:
    """A field's name to compare: 'Construction  method' and 'Selection marker ' as written here."""
    return ' '.join(str(name or '').split()).casefold()


def _field(st: 'SampleType', label: str):
    """The sample type's field of this name, or the one whose name starts with it ('Remarks on harmful effects (for ...')."""
    folded = _fold(label)
    if folded in st.fields:
        return st.fields[folded]
    starting = [f for name, f in st.fields.items() if name.startswith(folded)]
    return starting[0] if len(starting) == 1 else None


# --- what is copied ----------------------------------------------------------------

@dataclass
class Item:
    """A glycerol stock or seed lot, as eLab gets it."""
    kind: str
    id: str
    code: str
    lab: str
    name: str
    values: Dict[str, str]      # eLab field name -> value
    gone: Optional[str]         # why it is archived in eLab, or None
    storage: Optional[Dict[str, Optional[int]]] = None     # {'storageLayerID', 'position'}: where it is kept in eLab
    props: Dict[str, str] = field(default_factory=dict)    # the sample's own description and note
    from_elab: Optional[str] = None     # brought over from eLab: the sample's name there (it is never made there)
    called: str = ''                    # its own name here (the plasmid, the tube), to know its sample in eLab by


# --- the group's storage in eLab ---------------------------------------------------

PLACES_FOR = 600                # seconds the group's storage is remembered between lookups
_places: Dict[str, Tuple[float, dict]] = {}


def _all(client: Client, path: str, query: dict) -> List[dict]:
    """Every page of a list from eLab: until it has them all (eLab says hasNextPage false even when there are more)."""
    out, page = [], 0
    while True:
        found = client.call('GET', path, query={**query, '$records': 1000, '$page': page})
        items = _items(found)
        out += items
        total = found.get('totalRecords') if isinstance(found, dict) else None
        if not items or total is None or len(out) >= total or page > 200:
            return out
        page += 1


def locations(lab: str, refresh: bool = False, opener=None) -> dict:
    """
    The storage locations of the lab's eLab group: every compartment of its storage units (not its
    equipment), with its path ('Freezer 1 / Tower 2 / Box 5'), whether it is a box with places
    (a grid, rows x columns), and the kinds of compartment each unit has, by level, for adding one.
    """
    c = connection(lab)
    if c is None:
        return {'connected': False, 'locations': [], 'kinds': {}}
    key = f'{lab.casefold()}|{c.url}'
    cached = _places.get(key)
    if cached and not refresh and time.time() - cached[0] < PLACES_FOR:
        return cached[1]
    client = Client(c.url, c.token, opener)
    units = [u for u in _items(client.call('GET', '/storage', query={'$records': 1000}))
             if (u.get('deviceType') or 'STORAGE') == 'STORAGE']
    places, kinds = [], {}
    for u in units:
        sid = u['storageID']
        definitions = [d for d in _items(client.call('GET', f'/storage/{sid}/storageLayerDefinitions')) if not d.get('deleted')]
        level = {d['storageLayerDefinitionID']: d.get('level') or 0 for d in definitions}
        kinds[str(sid)] = [{'id': d['storageLayerDefinitionID'], 'name': d.get('name') or '', 'level': d.get('level') or 0,
                            'grid': bool(d.get('isGrid')), 'rows': _count(d, 'rows'), 'columns': _count(d, 'columns')}
                           for d in definitions]
        layers = {la['storageLayerID']: la for la in _all(client, '/storageLayers', {'storageID': sid})}
        for la in layers.values():
            names, node, seen = [], la, set()
            while node and node['storageLayerID'] not in seen:
                seen.add(node['storageLayerID'])
                names.append((node.get('name') or '').strip())
                node = layers.get(node.get('parentStorageLayerID') or 0)
            places.append({'id': la['storageLayerID'], 'path': ' / '.join(reversed(names)), 'unit': (u.get('name') or '').strip(),
                           'storage_id': sid, 'level': level.get(la.get('storageLayerDefinitionID'), 0),
                           'grid': bool(la.get('isGrid')), 'rows': _count(la, 'rows'), 'columns': _count(la, 'columns'),
                           # how eLab names a box's rows: A, B, C (ALPHA) or 1, 2, 3 (NUMERIC)
                           'lettered': ((la.get('dimension') or {}).get('rows') or {}).get('numbering') == 'ALPHA'})
    places.sort(key=lambda p: p['path'].casefold())
    found = {'connected': True, 'url': c.url, 'locations': places, 'kinds': kinds}
    _places[key] = (time.time(), found)
    return found


def _count(layer: dict, side: str) -> int:
    return int(((layer.get('dimension') or {}).get(side) or {}).get('count') or 1)


def add_location(lab: str, parent_id: Any, name: str, kind_id: Any, opener=None) -> dict:
    """Adds a compartment to the group's storage in eLab, under one there is, of a kind its unit has at that level."""
    name = str(name or '').strip()[:120]
    if not name:
        raise ValueError('Give the new location a name')
    known = locations(lab, refresh=True, opener=opener)
    if not known['connected']:
        raise ValueError('Connect the lab to eLab first')
    parent = next((p for p in known['locations'] if str(p['id']) == str(parent_id)), None)
    if parent is None:
        raise ValueError('Choose where in eLab the new location goes')
    if parent['grid']:
        raise ValueError(f"{parent['path']} is a box with places: put the new location somewhere else")
    kind = next((k for k in known['kinds'].get(str(parent['storage_id']), [])
                 if str(k['id']) == str(kind_id) and k['level'] == parent['level'] + 1), None)
    if kind is None:
        raise ValueError(f"Choose what kind of location it is: one {parent['unit']} has under {parent['path']}")
    c = connection(lab)
    made = Client(c.url, c.token, opener).call('POST', f"/storageLayers/{parent['id']}/childLayers",
                                               {'name': name, 'storageLayerDefinitionID': kind['id']})
    new_id = made if isinstance(made, int) else (made or {}).get('storageLayerID') if isinstance(made, dict) else None
    found = locations(lab, refresh=True, opener=opener)['locations']
    return next((p for p in found if new_id and p['id'] == new_id), None) or next(
        p for p in found if p['path'] == f"{parent['path']} / {name}")


HOSTS = [(re.compile(r'agro|gv3101|gv2260|agl[0-9]|eha10|lba4404|c58|rhizob', re.I), 'Agrobacterium / Rhizobium'),
         (re.compile(r'coli|dh5|dh10|top10|db3|ccdb|xl[0-9]|bl21|stbl|jm10|mach1|neb|omnimax|pir', re.I), 'E. coli'),
         (re.compile(r'yeast|cerevisiae|pichia|ah109|y2h|y187', re.I), 'Yeast'),
         (re.compile(r'pseudomonas', re.I), 'Pseudomonas')]


def host_system(strain: str) -> str:
    """eLab's host system for a strain: E. coli for DH5α, Agrobacterium for GV3101, ..."""
    if not strain.strip():
        return ''
    return next((system for pattern, system in HOSTS if pattern.search(strain)), '~ Other ~')


def _lines(*parts) -> str:
    return '\n'.join(p for p in parts if p)


def _plasmids(ids: List[str]) -> Dict[str, str]:
    """The sequences of these plasmids in the Plasmid Editor's library (read only): id -> sequence."""
    from app.sources import _read
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    rows = _read(os.environ.get('EDITOR_DATABASE_PATH', '/editor/plasmid_editor.db'),
                 f'SELECT id, sequence FROM sequences WHERE id IN ({", ".join("?" * len(ids))})', ids)
    return {r['id']: r['sequence'] or '' for r in rows}


def _glycerol(lab: str, defaults: Dict[str, str]) -> List[Item]:
    with connect() as conn:
        rows = conn.execute('SELECT * FROM glycerol WHERE lab = ? ORDER BY created_at, rowid', (lab,)).fetchall()
    plasmids = _plasmids([r['plasmid_id'] for r in rows])
    out = []
    for r in rows:
        gone = 'Deleted in Lab Stocks' if r['deleted_at'] else (
            f"{r['status'].capitalize()} in Lab Stocks" if r['status'] != 'in stock' else None)
        sequence = plasmids.get(r['plasmid_id'], '')
        system = {'other': '~ Other ~'}.get(r['host_system'], r['host_system']) or host_system(r['host'])
        storage = _storage(r)
        out.append(Item('glycerol', r['id'], r['code'], lab,
                        ' '.join(filter(None, [r['code'], r['plasmid_name'], f"clone {r['clone']}" if r['clone'] else ''])),
                        {'Permit': r['permit'] or defaults.get('Permit', ''),
                         'Biosafety level': r['biosafety'] or defaults.get('Biosafety level', ''),
                         'Name of host strain': r['host'], 'Host system': system,
                         'Bacterial Markers': r['selection'], 'Plant Markers': r['plant_markers'],
                         'Yeast Markers': r['yeast_markers'], 'Insert(s)?': r['inserts'], 'geneID(s)': r['gene_ids'],
                         'Donororganism(s)': r['donor'], 'Harmful gene product?': r['harmful'],
                         'Remarks on harmful effects': r['harmful_notes'],
                         # From the plasmid in the editor's library it holds.
                         'Plasmid sequence': sequence,
                         'Molecular weight (in kb)': f'{len(sequence) / 1000:.1f}' if sequence else '',
                         'Remarks': _lines(f"Plasmid: {r['plasmid_name']}" if r['plasmid_name'] else '',
                                           f"Clone: {r['clone']}" if r['clone'] else '',
                                           f"Kept in: {r['location']}" if r['location'] else '',
                                           f"Made on: {r['made_on']}" if r['made_on'] else '',
                                           r['notes'], f"Lab Stocks: {r['code']}")},
                        gone, storage, from_elab=r['plasmid_name'] if r['source'] == 'elab' else None,
                        called=r['plasmid_name']))
    return out


def _storage(r) -> Optional[Dict[str, Optional[int]]]:
    return ({'storageLayerID': int(r['elab_layer_id']),
             'position': int(r['elab_position']) if (r['elab_position'] or '').isdigit() else None}
            if (r['elab_layer_id'] or '').isdigit() else None)


def _material(lab: str, defaults: Dict[str, str]) -> List[Item]:
    """Plant material, as eLab's Plant Material type has it: named as on the tube, said in its description and note."""
    with connect() as conn:
        rows = conn.execute('SELECT * FROM material WHERE lab = ? ORDER BY created_at, rowid', (lab,)).fetchall()
    out = []
    for r in rows:
        gone = 'Deleted in Lab Stocks' if r['deleted_at'] else (
            f"{r['status'].capitalize()} in Lab Stocks" if r['status'] != 'in stock' else None)
        description = ' · '.join(filter(None, [r['description'], r['tissue'] if r['tissue'].casefold() not in r['description'].casefold() else '',
                                               r['species'], f"from {r['from_plant']}" if r['from_plant'] else '']))
        collected = ' '.join(filter(None, [f"collected {r['collected_on']}" if r['collected_on'] else '',
                                           f"by {r['collected_by']}" if r['collected_by'] else '']))
        note = _lines(collected[:1].upper() + collected[1:],
                      f"Experiment: {r['experiment']}" if r['experiment'] else '', f"Kept in: {r['location']}" if r['location'] else '',
                      r['notes'], f"Lab Stocks: {r['code']}")
        out.append(Item('material', r['id'], r['code'], lab, r['name'], dict(defaults), gone, _storage(r),
                        {'description': description, 'note': note},
                        from_elab=r['name'] if r['source'] == 'elab' else None, called=r['name']))
    return out


ZYGOSITY = {'homozygous': 'Homozygous', 'heterozygous': 'Heterozygous', 'hemizygous': 'Hemizogous'}


def _seeds_db() -> Optional[sqlite3.Connection]:
    path = os.environ.get('SEEDS_DATABASE_PATH', '/seeds/seeds.db')
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _seed_lots(lab: str, defaults: Dict[str, str]) -> List[Item]:
    """
    The lab's seed lots in the Seed Bank (read only), with their line (its biosafety, stock center and
    genetics too, in a Seed Bank from 0.4.0 on), and the plants they came from.
    """
    conn = _seeds_db()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            'SELECT l.*, m.code AS mother, f.code AS father, '
            '(SELECT COUNT(*) FROM line_plasmids p WHERE p.line_id = l.line_id) AS plasmids '
            'FROM lots l LEFT JOIN plants m ON m.id = l.from_plant_id LEFT JOIN plants f ON f.id = l.father_plant_id '
            'WHERE l.lab = ? ORDER BY l.created_at, l.rowid', (lab,)).fetchall()
        lines = {r['id']: dict(r) for r in conn.execute('SELECT * FROM lines')}
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    out = []
    for r in rows:
        n = lines.get(r['line_id'])
        if n is None:
            continue
        line = lambda key: n.get(key) or ''      # noqa: E731  a column an older Seed Bank lacks: empty
        kind = line('kind')
        gmo = 'Yes' if kind == 'transgenic' or r['plasmids'] or line('gmo_type') in (
            'T-DNA insertion', 'Plasmid introduction') else 'No' if kind == 'wild type' else 'Unknown'
        gone = 'Deleted in the Seed Bank' if r['deleted_at'] else 'Used up in the Seed Bank' if r['used_up'] else None
        source = (r['source'] or '').strip()
        out.append(Item('seed', r['id'], r['code'], lab, f"{r['code']} {line('name')}",
                        {'Permit': line('permit') or defaults.get('Permit', ''),
                         'Biosafety level': line('biosafety') or defaults.get('Biosafety level', ''),
                         'Species': line('species'), 'Genetic background': line('background'),
                         'Generation': r['generation'], 'Mother plant': r['mother'] or '', 'Father plant': r['father'] or '',
                         'Cross': 'yes' if r['father'] or kind == 'cross' else 'no',
                         'Zygosity': ZYGOSITY.get(r['zygosity'], ''), 'Harvest Date': r['harvested_on'] or '', 'GMO': gmo,
                         'GMO type': line('gmo_type'), 'Gene expression': line('gene_expression'),
                         'Selection marker': line('selection_marker'), 'Mutation information': line('mutation_info'),
                         'Construction method': line('construction'),
                         'Line': line('collection'), 'Stock center number': line('stock_center_number'),
                         'Stock center line': 'yes' if line('collection') or line('stock_center_number') else 'no',
                         'Accession': line('accession'), 'Web link stock center': line('stock_center_url'),
                         'Harvested by': r['created_by'] or '',
                         'Description': _lines(f"Line: {line('name')} ({kind})", line('description'),
                                               f"Amount: {r['amount']}" if r['amount'] else '',
                                               f"Kept in: {r['location']}" if r['location'] else '',
                                               f"Germination: {r['germination']:g}%" if r['germination'] is not None else '',
                                               f"Source: {r['source']}" if r['source'] else '',
                                               r['notes'], f"Seed Bank: {r['code']}")},
                        gone, from_elab=source[5:].strip() if source.startswith('eLab ') else None))
    return out


def items(kind: str, lab: str, c: Connection) -> List[Item]:
    defaults = {f: v for f, v in (c.defaults.get(kind) or {}).items() if v}
    return {'glycerol': _glycerol, 'material': _material, 'seed': _seed_lots}[kind](lab, defaults)


def fingerprint(item: Item, c: Connection) -> str:
    sent = {'name': item.name, 'values': item.values, 'gone': bool(item.gone), 'type': c.type_name(item.kind), 'url': c.url,
            'storage': item.storage, 'props': item.props}
    return hashlib.sha256(json.dumps(sent, sort_keys=True).encode()).hexdigest()


def _metas(st: SampleType, vals: Dict[str, str]) -> List[dict]:
    """The values for fields the sample type has; for a field with options, only one of them (as eLab spells it)."""
    out = []
    for label, value in vals.items():
        meta = _field(st, label)
        if not meta:
            continue
        meta_id, key, data_type, options = meta
        if options and data_type in ('COMBO', 'RADIO', 'CHECKBOX') and value:
            # Several, for a checkbox field: each one of its options.
            wanted = [v.strip() for v in value.split(',')] if data_type == 'CHECKBOX' else [value.strip()]
            matched = [next((o for o in options if _fold(o) == _fold(w)), None) for w in wanted if w]
            if not matched or None in matched:
                continue
            value = ','.join(matched)
        out.append({'sampleTypeMetaID': meta_id, 'key': key, 'sampleDataType': data_type, 'value': value})
    return out


def _existing(client: Client, st: SampleType, item: Item) -> Optional[int]:
    """
    A sample already in eLab for this record (sent before the link here was kept), so it is not made twice:
    the one with its code as its barcode (eLab keeps the alternative id as the barcode, unique in the
    group), or, for a glycerol stock or seed lot (named by its code), one of its name without a barcode.
    """
    found = _items(client.call('GET', '/samples', query={'sampleTypeID': st.id, 'barcodes': item.code, '$records': 5}))
    same = [f for f in found if str(f.get('altID') or f.get('barcode') or '').strip() == item.code]
    if not same and item.kind in ('glycerol', 'seed'):
        found = _items(client.call('GET', '/samples', query={'sampleTypeID': st.id, 'name': item.name, '$records': 5}))
        same = [f for f in found if (f.get('name') or '').strip() == item.name and not f.get('archived')
                and not str(f.get('altID') or '').strip()]
    linked = _linked_samples()
    same = [f for f in same if int(f['sampleID']) not in linked]
    return int(same[0]['sampleID']) if same else None


def _linked_samples() -> Dict[int, str]:
    """The samples linked to a record here (none archived here): sample id -> record id."""
    with connect() as conn:
        return {int(r[0]): r[1] for r in conn.execute(
            'SELECT sample_id, record_id FROM elab_links WHERE sample_id IS NOT NULL AND archived != 1')}


def _at(sample: dict, storage: Dict[str, Optional[int]]) -> bool:
    """Whether eLab keeps this sample in that place: the compartment, and the place in it when there is one."""
    return (int(sample.get('storageLayerID') or 0) == storage['storageLayerID']
            and (storage['position'] is None or int(sample.get('position') or 0) == storage['position']))


def _adopt_found(client: Client, st: SampleType, item: Item, c: Connection, name: Optional[str] = None,
                 place: bool = False) -> dict:
    """
    One brought over from eLab, not linked yet (its link was not made, say): linked now to the sample of
    its name there, never made a second time; of several of that name, the one in its place. None such,
    or more than one: not sent at all. place: only the one in its place. A glycerol stock or tube is then
    made by the sample's owner.
    """
    name = name or item.from_elab
    found = _items(client.call('GET', '/samples', query={'sampleTypeID': st.id, 'name': name, '$records': 50}))
    linked = _linked_samples()
    same = [f for f in found if (f.get('name') or '').strip() == name and not f.get('archived')
            and int(f['sampleID']) not in linked]
    if item.storage and (place or len(same) > 1):
        same = [f for f in same if _at(f, item.storage)]
    if len(same) != 1:
        raise ElabError(0, f"Brought over from eLab as {name}, which eLab has {'twice' if same else 'no more (or it is linked already)'}: "
                           'not sent, so as not to make it twice')
    if item.kind in TABLES:
        with connect() as conn:
            set_maker(conn, item.kind, item.id, same[0].get('owner'))
    item.name = name
    sent = {'name': name, 'values': {m['key']: m['value'] for m in _metas(st, item.values)},
            'storage': item.storage, 'props': item.props}
    return {'sample_id': int(same[0]['sampleID']), 'archived': 0, 'sent': json.dumps(sent), 'elab_name': name,
            'synced': fingerprint(item, c)}


TABLES = {'glycerol': 'glycerol', 'material': 'material'}     # the kinds kept here (seed lots are the Seed Bank's)

HELD = 2         # elab_links.archived: archived in eLab, not here; sent no more, and not made again


def _refused(client: Client, sample_id: int, exc: ElabError) -> Optional[dict]:
    """
    eLab refused to change a sample, or has it no more: archived (or deleted) in eLab, it is held, no more
    sent; else it is someone else's, which this token may not change.
    """
    try:
        found = client.call('GET', f'/samples/{sample_id}')
    except ElabError as missing:
        if missing.status != 404:
            raise exc
        found = None
    if found is None or (isinstance(found, dict) and found.get('archived')):
        return {'sample_id': sample_id, 'archived': HELD, 'sent': '{}'}
    owner = (found or {}).get('owner') if isinstance(found, dict) else None
    raise ElabError(exc.status, f"eLab does not let this account change it{f': it is {owner}' + chr(39) + 's' if owner else ''}")


def push(client: Client, st: SampleType, item: Item, link: Optional[dict]) -> dict:
    """
    Sends one item; gives what to keep of the link: sample_id, archived, sent (the values sent).
    link: what was last sent to this eLab, or None.
    """
    sample_id = link['sample_id'] if link and not link['archived'] else None
    if link and link['archived'] == HELD:
        return dict(link)                   # archived in eLab: left so
    sent = json.loads(link['sent']) if link and link['sent'] and sample_id else {}
    if item.gone:
        if sample_id:
            try:
                client.call('DELETE', f'/samples/{sample_id}', item.gone)
            except ElabError as exc:
                if exc.status != 404:
                    raise
        return {'sample_id': link['sample_id'] if link else None, 'archived': 1, 'sent': '{}'}
    if sample_id is None and not link:
        sample_id = _existing(client, st, item)
    if sample_id:
        try:
            if sent.get('name') != item.name or sent.get('storage') != item.storage or sent.get('props', {}) != item.props:
                client.call('PATCH', f'/samples/{sample_id}', {'name': item.name, **(item.storage or {}), **item.props})
            old = sent.get('values', {})
            for meta in _metas(st, item.values):
                if old.get(meta['key']) != meta['value']:
                    client.call('PUT', f'/samples/{sample_id}/meta', meta)
        except ElabError as exc:
            if exc.status not in (403, 404):
                raise
            refused = _refused(client, sample_id, exc)
            if refused is not None:
                return refused
    if not sample_id:
        new = {'sampleTypeID': st.id, 'name': item.name, 'altID': item.code, 'sampleMetas': _metas(st, item.values),
               **{k: v for k, v in (item.storage or {}).items() if v is not None}, **item.props}
        try:
            sample_id = int(client.call('POST', '/samples', new))
        except ElabError as exc:
            if exc.status != 409:
                raise
            # Its code is already a barcode in the group. A live sample's (another Lab Stocks sending the
            # same lab, say): not made twice. An archived one's (its own, archived here once): one without it.
            holders = [h for h in _items(client.call('GET', '/samples', query={'barcodes': item.code, '$records': 5}))
                       if str(h.get('altID') or h.get('barcode') or '').strip() == item.code and not h.get('archived')]
            if holders:
                h = holders[0]
                raise ElabError(409, f"{item.code} is already in eLab, as {h.get('name')!r}"
                                     f"{' (' + h['owner'] + chr(39) + 's)' if h.get('owner') else ''}: not made twice")
            del new['altID']
            sample_id = int(client.call('POST', '/samples', new))
    sent_values = {m['key']: m['value'] for m in _metas(st, item.values)}
    return {'sample_id': sample_id, 'archived': 0,
            'sent': json.dumps({'name': item.name, 'values': sent_values, 'storage': item.storage, 'props': item.props})}


# --- the rounds ------------------------------------------------------------------

def _labs() -> List[str]:
    labs = set()
    with connect() as conn:
        for table in ('glycerol', 'material'):
            labs |= {r[0] for r in conn.execute(f'SELECT DISTINCT lab FROM {table}')}
        labs |= {r[0] for r in conn.execute('SELECT lab FROM elab_settings')}
    seeds = _seeds_db()
    if seeds is not None:
        try:
            labs |= {r[0] for r in seeds.execute('SELECT DISTINCT lab FROM lots WHERE lab IS NOT NULL')}
        except sqlite3.Error:
            pass
        finally:
            seeds.close()
    return sorted(lab for lab in labs if lab)


def run_once(opener=None) -> dict:
    """Sends every glycerol stock and seed lot that differs from what eLab was last sent; gives how many were sent and failed."""
    sent = failed = 0
    with _lock:
        _state['running'] = True
        try:
            for lab in _labs():
                c = connection(lab)
                if c is None:
                    continue
                try:
                    s, f = _run_lab(lab, c, Client(c.url, c.token, opener))
                    sent, failed = sent + s, failed + f
                    for kind in c.kinds:
                        if kind in TABLES and time.time() - _owners_at.get(f'{lab.casefold()}|{kind}', 0) >= OWNERS_EVERY:
                            owners_as_makers(lab, kind, refresh=True, opener=opener)
                    _state['errors'].pop(lab, None)
                except ElabError as exc:
                    _state['errors'][lab] = ('eLab no longer accepts the token: connect again with a new one. '
                                             if exc.status == 401 else '') + str(exc)
        finally:
            _state['running'] = False
            _state['last_run'] = time.strftime('%Y-%m-%d %H:%M:%S')
    return {'sent': sent, 'failed': failed}


def _links(kind: str) -> Dict[str, dict]:
    with connect() as conn:
        return {r['record_id']: dict(r) for r in conn.execute('SELECT * FROM elab_links WHERE record_kind = ?', (kind,))}


def _run_lab(lab: str, c: Connection, client: Client) -> Tuple[int, int]:
    sent = failed = 0
    for kind in c.kinds:
        links, now, todo = _links(kind), time.time(), []
        for item in items(kind, lab, c):
            link = links.get(item.id)
            if link and link['elab_url'] != c.url:
                link = None                 # sent to another eLab: starts afresh in this one
            _named(item, link)
            fp = fingerprint(item, c)
            if link and link['synced'] == fp:
                continue
            if link and link['archived'] == HELD:
                continue                    # archived in eLab: not sent, nor made again
            if not link and item.gone:
                continue                    # never in eLab, and not wanted there
            if link and link['error'] and link['tried'] == fp and now - (link['tried_at'] or 0) < RETRY_AFTER:
                continue
            todo.append((item, link, fp))
        if not todo:
            continue
        st = sample_type(client, c.type_name(kind))
        for item, link, fp in todo:
            try:
                if item.from_elab and not (link and link['sample_id']):
                    _keep(kind, item.id, None, elab_url=c.url, error=None, tried=fp, tried_at=now,
                          synced_at=time.strftime('%Y-%m-%d %H:%M:%S'), **_adopt_found(client, st, item, c))
                    continue
                try:
                    kept = push(client, st, item, link)
                except ElabError as exc:
                    # Its place in eLab is taken: by its own sample, when one of its name is there and linked to
                    # nothing (brought over from eLab, its link not made). Linked to it then, not made twice.
                    if not (exc.status == 400 and 'no free space' in str(exc).lower() and item.called and item.storage):
                        raise
                    try:
                        found = _adopt_found(client, st, item, c, name=item.called, place=True)
                    except ElabError:
                        raise exc
                    _keep(kind, item.id, None, elab_url=c.url, error=None, tried=fp, tried_at=now,
                          synced_at=time.strftime('%Y-%m-%d %H:%M:%S'), **found)
                    sent += 1
                    continue
            except ElabError as exc:
                if exc.status == 401:
                    raise
                failed += 1
                _keep(kind, item.id, link, elab_url=c.url, error=str(exc)[:500], tried=fp, tried_at=now)
                continue
            sent += 1
            _keep(kind, item.id, link, elab_url=c.url, synced=fp, error=None, tried=fp, tried_at=now,
                  synced_at=time.strftime('%Y-%m-%d %H:%M:%S'), **kept)
    return sent, failed


def _named(item: Item, link: Optional[dict]) -> None:
    """One brought over from eLab keeps its name there (sLAB0000112, P130-34 F3)."""
    if link and link.get('elab_name'):
        item.name = link['elab_name']


def _keep(kind: str, record_id: str, link: Optional[dict], **values) -> None:
    merged = {'sample_id': None, 'archived': 0, 'sent': None, 'synced': None, 'error': None, 'elab_url': None,
              'tried': None, 'tried_at': None, 'synced_at': None, 'elab_name': None, **(link or {}), **values}
    with connect() as conn:
        conn.execute('INSERT OR REPLACE INTO elab_links (record_kind, record_id, elab_url, sample_id, archived, sent, '
                     'synced, error, tried, tried_at, synced_at, elab_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                     (kind, record_id, merged['elab_url'], merged['sample_id'], merged['archived'], merged['sent'],
                      merged['synced'], merged['error'], merged['tried'], merged['tried_at'], merged['synced_at'],
                      merged['elab_name']))


# --- bringing over what eLab has ---------------------------------------------------

_found: Dict[str, Tuple[float, List[dict]]] = {}


def candidates(lab: str, kind: str, refresh: bool = False, opener=None, every: bool = False) -> List[dict]:
    """
    The samples of the lab's eLab group of the kind's sample type not yet linked to a record here (none
    archived), to bring over: name, owner, note, description, species, where they are kept. every: those
    already here as well, each with here: whether it is.
    """
    c = connection(lab)
    if c is None:
        raise ValueError('Connect the lab to eLab first')
    if kind not in ('glycerol', 'material', 'seed'):
        raise ValueError('Glycerol stocks, plant material and seed lots are brought over from eLab')
    key = f'{lab.casefold()}|{c.url}|{kind}'
    cached = _found.get(key)
    if cached and not refresh and time.time() - cached[0] < PLACES_FOR:
        samples = cached[1]
    else:
        client = Client(c.url, c.token, opener)
        st = sample_type(client, c.type_name(kind))
        paths = {p['id']: p['path'] for p in locations(lab, opener=opener)['locations']}
        samples = []
        for s in _all(client, '/samples', {'sampleTypeID': st.id, '$expand': 'meta'}):
            if s.get('archived'):
                continue
            meta = {str(m.get('key') or '').strip(): m.get('value') or '' for m in (s.get('meta') or [])}
            samples.append({'id': s['sampleID'], 'name': (s.get('name') or '').strip(), 'owner': s.get('owner') or '',
                            'note': (s.get('note') or '').strip(), 'description': (s.get('description') or '').strip(),
                            'species': meta.get('Species', ''), 'created': (s.get('created') or '')[:10],
                            'strain': meta.get('Name of host strain', ''), 'selection': meta.get('Bacterial Markers', ''),
                            'layer': s.get('storageLayerID') or None, 'position': s.get('position') or None,
                            'path': paths.get(s.get('storageLayerID'), ''), 'meta': meta})
        _found[key] = (time.time(), samples)
    linked = _linked_samples()
    brought = set()
    if kind == 'seed':
        seeds = _seeds_db()
        if seeds is not None:
            try:
                brought = {r[0][5:].strip() for r in seeds.execute(
                    "SELECT source FROM lots WHERE source LIKE 'eLab %' AND deleted_at IS NULL")}
            except sqlite3.Error:
                pass
            finally:
                seeds.close()
    if every:
        return [{**s, 'here': s['id'] in linked or s['name'] in brought} for s in samples]
    return [s for s in samples if s['id'] not in linked and s['name'] not in brought]


def sample_url(url: str, sample_id: int) -> str:
    """A sample's page in eLab's inventory."""
    return f"{url.rstrip('/')}/members/inventory-rebuild/#/samples/{sample_id}"


def record_state(kind: str, lab: str, record_id: str) -> Optional[dict]:
    """
    Where one record is in eLab, for its page: its sample (and a link to it), and whether it is sent,
    waiting, failed (why), archived in eLab, or not in eLab. None when the lab is not connected or the
    kind not copied.
    """
    c = connection(lab)
    if c is None or kind not in c.kinds:
        return None
    item = next((i for i in items(kind, lab, c) if i.id == record_id), None)
    link = _links(kind).get(record_id)
    if link and link['elab_url'] != c.url:
        link = None
    out = {'sample_id': None, 'url': None, 'state': 'not sent', 'error': None, 'synced_at': None}
    if link and link['sample_id']:
        out.update(sample_id=link['sample_id'], url=sample_url(c.url, link['sample_id']), synced_at=link['synced_at'])
    if item is None:
        return out
    _named(item, link)
    if link and link['archived'] == HELD:
        out['state'] = 'archived in eLab'
    elif link and link['archived'] == 1 and item.gone:
        out['state'] = 'archived'
    elif link and link['synced'] == fingerprint(item, c):
        out['state'] = 'sent'
    elif link and link['error']:
        out.update(state='failed', error=link['error'])
    elif not item.gone:
        out['state'] = 'waiting'
    return out


def send_again(kind: str, lab: str, record_id: str, opener=None) -> dict:
    """
    A record whose sample was archived in eLab, sent there again: to that sample, when it was restored
    in eLab meanwhile; else as a new one (eLab cannot be asked to restore it).
    """
    c = connection(lab)
    link = _links(kind).get(record_id)
    if c is None or link is None or link['archived'] != HELD:
        raise ValueError('Only one whose sample was archived in eLab is sent again')
    try:
        found = Client(c.url, c.token, opener).call('GET', f"/samples/{link['sample_id']}")
    except ElabError as exc:
        if exc.status != 404:
            raise ValueError(f'eLab could not be asked: {exc}') from exc
        found = None
    restored = isinstance(found, dict) and not found.get('archived')
    # Restored: the same sample, every field sent again. Not: one archived here, so a new one is made.
    _keep(kind, record_id, link, archived=0 if restored else 1, sent='{}', synced=None, error=None, tried=None)
    nudge()
    return {'restored': restored}


@contextlib.contextmanager
def paused():
    """No round while records are made and linked (brought over from eLab): none is sent as new meanwhile."""
    with _lock:
        yield


def adopt(lab: str, kind: str, pairs: List[Tuple[str, int, str]], opener=None) -> int:
    """
    Links records just brought over from eLab to their samples there: (record id, sample id, its name in eLab).
    What they would send is taken as sent, so nothing is changed in eLab until they are changed here.
    """
    c = connection(lab)
    if c is None:
        raise ValueError('Connect the lab to eLab first')
    st = sample_type(Client(c.url, c.token, opener), c.type_name(kind))
    by_id = {i.id: i for i in items(kind, lab, c)}
    linked = _linked_samples()
    done = 0
    for record_id, sample_id, name in pairs:
        item = by_id.get(record_id)
        if item is None or linked.get(int(sample_id), record_id) != record_id:
            continue                        # gone, or its sample linked to another record already
        linked[int(sample_id)] = record_id
        item.name = name
        sent = {'name': name, 'values': {m['key']: m['value'] for m in _metas(st, item.values)},
                'storage': item.storage, 'props': item.props}
        _keep(kind, record_id, None, elab_url=c.url, sample_id=int(sample_id), archived=0, sent=json.dumps(sent),
              synced=fingerprint(item, c), elab_name=name, synced_at=time.strftime('%Y-%m-%d %H:%M:%S'))
        done += 1
    for k in [k for k in _found if k.startswith(f'{lab.casefold()}|')]:
        del _found[k]
    return done


def place_of(sample: dict) -> Tuple[str, Optional[int], Optional[int]]:
    """A sample to bring over, by its name and place in eLab's storage."""
    return ((sample.get('name') or '').strip().casefold(), int(sample['layer']) if sample.get('layer') else None,
            int(sample['position']) if sample.get('position') else None)


def unlinked(lab: str, kind: str) -> Dict[Tuple[str, Optional[int], Optional[int]], str]:
    """
    Glycerol stocks or tubes here in a place in eLab's storage but linked to no sample there (brought over,
    and their link not made): (their name, compartment, place) -> record id, to be linked, not brought twice.
    """
    c = connection(lab)
    if c is None:
        return {}
    links, out = _links(kind), {}
    for i in items(kind, lab, c):
        link = links.get(i.id)
        if i.gone or not i.storage or (link and link['sample_id']):
            continue
        out.setdefault((i.called.strip().casefold(), i.storage['storageLayerID'], i.storage['position']), i.id)
    return out


def set_maker(conn, kind: str, record_id: str, owner: Optional[str]) -> bool:
    """
    One brought over from eLab is made by its sample's owner there: so set when it is not (who brought it
    over, or the owner changed in eLab since), in its history too. Gives whether it changed.
    """
    owner = (owner or '').strip()
    if kind not in TABLES or not owner:
        return False
    if not conn.execute(f'UPDATE {TABLES[kind]} SET created_by = ? WHERE id = ? AND created_by IS NOT ?',
                        (owner, record_id, owner)).rowcount:
        return False
    conn.execute('INSERT INTO changes (record_kind, record_id, changed_by, what) VALUES (?, ?, ?, ?)',
                 (kind, record_id, 'eLab', f'made by {owner}, as its owner in eLab'))
    return True


OWNERS_EVERY = 3600             # seconds between looking up, in eLab, the owners of what was brought over
_owners_at: Dict[str, float] = {}


def owners_as_makers(lab: str, kind: str, refresh: bool = False, opener=None) -> int:
    """
    Those brought over from eLab: made by their sample's owner there, as eLab has it now; where they differ,
    eLab is right. Those made here and sent there are left (eLab's owner of those is whose token sends them).
    """
    if kind not in TABLES:
        return 0
    owner = {s['id']: s['owner'] for s in candidates(lab, kind, refresh=refresh, opener=opener, every=True) if s['here']}
    fixed = 0
    with connect() as conn:
        for r in conn.execute(f'SELECT l.record_id, l.sample_id FROM elab_links l JOIN {TABLES[kind]} t ON t.id = l.record_id '
                              'WHERE l.record_kind = ? AND l.elab_name IS NOT NULL AND l.sample_id IS NOT NULL '
                              'AND l.archived = 0 AND t.lab = ?', (kind, lab)).fetchall():
            fixed += set_maker(conn, kind, r['record_id'], owner.get(r['sample_id']))
    _owners_at[f'{lab.casefold()}|{kind}'] = time.time()
    return fixed


# --- taking what was changed in eLab ------------------------------------------------

# A glycerol stock's fields in eLab (by the start of their name there) and here. The others eLab has are
# made from several here (Remarks, the sequence), and plant material's description and note likewise.
FROM_ELAB = {'Permit': 'permit', 'Biosafety level': 'biosafety', 'Name of host strain': 'host',
             'Host system': 'host_system', 'Bacterial Markers': 'selection', 'Plant Markers': 'plant_markers',
             'Yeast Markers': 'yeast_markers', 'Insert(s)?': 'inserts', 'geneID(s)': 'gene_ids',
             'Donororganism(s)': 'donor', 'Harmful gene product?': 'harmful', 'Remarks on harmful effects': 'harmful_notes'}


def _as_here(field: str, value: str) -> str:
    """A value from eLab as it is kept here: for a field with options, one of those (else none)."""
    from app import records
    allowed = {'biosafety': records.BIOSAFETY, 'host_system': records.HOST_SYSTEMS, 'inserts': records.YES_NO,
               'harmful': records.HARMFUL}.get(field)
    if allowed is None:
        return value
    first = str(value or '').split(',')[0].strip().casefold()
    if field == 'host_system' and 'other' in first:
        return 'other'
    return next((a for a in allowed if a and a.casefold() == first), '')


def update_from_elab(lab: str, by: str, opener=None) -> dict:
    """
    What was changed in eLab since it was last sent, taken here for every glycerol stock and tube linked to a
    sample there (eLab is right, where both were changed): a glycerol stock's fields, where it is kept, and
    the name of one brought over from eLab. What was changed only here stays, and is sent at the next round.
    Gives how many were looked at and changed.
    """
    from app import records
    c = connection(lab)
    if c is None:
        raise ValueError('Connect the lab to eLab first')
    looked = changed = 0
    with _lock:                     # no round meanwhile
        paths = {p['id']: p['path'] for p in locations(lab, refresh=True, opener=opener)['locations']}
        for kind in [k for k in c.kinds if k in TABLES]:
            now = {s['id']: s for s in candidates(lab, kind, refresh=True, opener=opener, every=True)}
            with connect() as conn:
                mine = {r[0] for r in conn.execute(f'SELECT id FROM {TABLES[kind]} WHERE lab = ? AND deleted_at IS NULL', (lab,))}
            for record_id, link in _links(kind).items():
                s = now.get(link['sample_id']) if link['sample_id'] else None
                if record_id not in mine or link['elab_url'] != c.url or link['archived'] or s is None:
                    continue                # not this lab's, not linked, or archived in eLab (the round sees to that)
                looked += 1
                sent = json.loads(link['sent'] or '{}')
                values, data = dict(sent.get('values') or {}), {}
                if kind == 'glycerol':
                    for key, value in s['meta'].items():
                        field = next((f for start, f in FROM_ELAB.items() if key.startswith(start)), None)
                        if field and str(value) != str(values.get(key, '')):
                            data[field], values[key] = _as_here(field, value), value
                storage = sent.get('storage') or {}
                if (s['layer'], s['position']) != (storage.get('storageLayerID'), storage.get('position')):
                    data.update(elab_layer_id=str(s['layer'] or ''), elab_position=str(s['position'] or ''),
                                elab_layer_path=paths.get(s['layer'], '') if s['layer'] else '')
                    storage = {'storageLayerID': s['layer'], 'position': s['position']} if s['layer'] else None
                name = sent.get('name')
                if link['elab_name'] and s['name'] and s['name'] != link['elab_name']:
                    data['plasmid_name' if kind == 'glycerol' else 'name'] = name = s['name']
                if not data:
                    continue
                if records.take_from_elab(kind, record_id, data, by):
                    changed += 1
                # As eLab has it now, so the round sends only what was changed here.
                _keep(kind, record_id, link, elab_name=name if link['elab_name'] else None,
                      sent=json.dumps({**sent, 'name': name, 'values': values, 'storage': storage}))
    nudge()
    return {'looked': looked, 'changed': changed}


def seed_lot_ids(codes: List[str]) -> Dict[str, str]:
    """The Seed Bank's lots of these codes: code -> id (read only)."""
    conn = _seeds_db()
    if conn is None or not codes:
        return {}
    try:
        return {r['code']: r['id'] for r in conn.execute(
            f'SELECT id, code FROM lots WHERE code IN ({", ".join("?" * len(codes))})', list(codes))}
    finally:
        conn.close()


def seed_lot(code: str) -> Optional[dict]:
    """The Seed Bank's lot of this code, not deleted: {id, code, lab} (read only)."""
    conn = _seeds_db()
    if conn is None:
        return None
    try:
        r = conn.execute('SELECT id, code, lab FROM lots WHERE code = ? AND deleted_at IS NULL AND lab IS NOT NULL',
                         (code,)).fetchone()
        return dict(r) if r else None
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def nudge() -> None:
    """Something changed: send it now, not at the next round."""
    _wake.set()


def _loop(interval: float) -> None:
    time.sleep(5)
    while True:
        _wake.clear()
        try:
            run_once()
        except Exception as exc:        # the thread must outlive anything one round meets
            _state['errors']['*'] = f'{type(exc).__name__}: {exc}'
        _wake.wait(interval)
        time.sleep(2)                   # a burst of changes goes in one round


def start() -> None:
    """The thread that sends; it does nothing while no lab is connected."""
    global _thread
    if _thread is not None or os.environ.get('ELAB_THREAD') == '0':
        return
    interval = max(30.0, float(os.environ.get('ELAB_INTERVAL', '120') or 120))
    _thread = threading.Thread(target=_loop, args=(interval,), name='elab-sync', daemon=True)
    _thread.start()


def status(lab: str, only: Optional[str] = None) -> dict:
    """
    Where the lab's stocks are copied, and how far: sent, waiting, and what failed (only: of that kind).
    Never the token.
    """
    c = connection(lab)
    out = {'lab': lab, 'connected': c is not None, 'default_url': os.environ.get('ELAB_URL', '').strip() or DEFAULT_URL,
           'all_kinds': [[k, SAMPLE_TYPES[k], TITLES[k]] for k in SAMPLE_TYPES], 'lab_fields': LAB_FIELDS,
           'last_run': _state['last_run'], 'running': _state['running'],
           'last_error': _state['errors'].get(lab) or _state['errors'].get('*'),
           'synced': 0, 'waiting': 0, 'failed': [], 'held': 0}
    if c is None:
        return out
    out.update(url=c.url, source=c.source, kinds=c.kinds, sample_types={k: c.type_name(k) for k in c.kinds},
               defaults=c.defaults, set_by=c.set_by, set_at=c.set_at)
    for kind in c.kinds:
        if only and kind != only:
            continue
        links = _links(kind)
        for item in items(kind, lab, c):
            link = links.get(item.id)
            if link and link['elab_url'] != c.url:
                link = None
            _named(item, link)
            if link and link['archived'] == HELD:
                out['held'] += 1
            elif link and link['synced'] == fingerprint(item, c):
                out['synced'] += 0 if item.gone else 1
            elif link and link['error']:
                out['failed'].append({'kind': kind, 'code': item.code, 'error': link['error']})
            elif link or not item.gone:
                out['waiting'] += 1
    return out
