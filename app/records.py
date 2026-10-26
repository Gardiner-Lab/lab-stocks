"""
Glycerol stocks, primers, chemicals and antibodies: making, changing, finding them, and who sees what.

A record belongs to the lab of whoever made it. Everyone in that lab sees and
changes it; other labs do not see it at all; administrators see all. Every
change is logged.

Codes start with the lab's code (the same as in the Seed Bank, when the lab has
one there), then G for a glycerol stock, O for an oligo (primer), C for a
chemical or A for an antibody, then the lab's own number: GL-G-0042, GL-O-0007,
GL-C-0003, GL-A-0005.
"""

import os
import re
import secrets
import sqlite3
from typing import Any, Dict, List, Optional

from app import elab, oligo
from app.db import connect
from app.people import Person

KINDS = {'glycerol': 'G', 'primer': 'O', 'chemical': 'C', 'antibody': 'A', 'material': 'M'}
TABLE = {'glycerol': 'glycerol', 'primer': 'primers', 'chemical': 'chemicals', 'antibody': 'antibodies', 'material': 'material'}
NAMES = {'glycerol': 'glycerol stock', 'primer': 'primer', 'chemical': 'chemical', 'antibody': 'antibody',
         'material': 'plant material'}
# Plant material: what tissue, suggested in its form.
TISSUES = ('leaf', 'flower', 'petal', 'root', 'stem', 'seedling', 'seed', 'fruit', 'callus', 'whole plant', 'RNA', 'DNA')
ANTIBODY_TYPES = ('primary', 'secondary', 'other')
CAS = re.compile(r'(\d{2,7})-(\d{2})-(\d)')
SDS = 'SDS'                 # the caption of a chemical's safety data sheet
STATUS = ('in stock', 'used up', 'discarded')
# A chemical runs out (and is ordered again), or is got rid of.
CHEMICAL_STATUS = ('in stock', 'out', 'discarded')
DIRECTIONS = ('', 'forward', 'reverse')
# A glycerol stock's biosafety, as the GMO register (and eLab) has it. Empty: the
# lab's own permit and biosafety level (chosen with eLab), the host system from the strain.
BIOSAFETY = ('', 'I', 'II', 'III', 'IV', 'unknown')
HOST_SYSTEMS = ('', 'E. coli', 'Agrobacterium / Rhizobium', 'Yeast', 'Pseudomonas', 'Fungi', 'other')
YES_NO = ('', 'yes', 'no')
HARMFUL = ('', 'unknown', 'no', 'yes')
PERMITS = ('IG 99-249', 'new plasmid (not yet in permit)')
PLANT_MARKERS = ('BASTA', 'Hygromycin', 'Kanamycin', 'Norflurazon', 'Methotrexate', 'GFP', 'DsRed', 'Ruby', 'Fluorescent Seed')
# A primer's 5' and 3' modifications, as oligo suppliers offer them: suggested in its form (others may be typed).
MODS_5 = ('Phosphate', 'Biotin', 'Biotin-TEG', '6-FAM', 'HEX', 'TET', 'JOE', 'Cy3', 'Cy5', 'TAMRA', 'ROX', 'Texas Red',
          'ATTO 550', 'Amino C6', 'Amino C12', 'Thiol C6', 'Digoxigenin', 'Acrydite', 'DBCO', 'Azide')
MODS_3 = ('Phosphate', 'Biotin', 'Amino C3', 'Amino C6', 'Thiol C3', 'BHQ-1', 'BHQ-2', 'BHQ-3', 'TAMRA', 'Dabcyl',
          'Iowa Black FQ', 'Inverted dT', 'ddC', 'C3 spacer', 'Cholesterol-TEG', '6-FAM')
YEAST_MARKERS = ('Ura-', 'Trp-', 'Leu-', 'His-', 'Lys-', 'Met-', 'Ade-', 'Gal-', 'Cycloheximide')
LAB_CODE = re.compile(r'[A-Z][A-Z0-9]{0,5}')


class Forbidden(Exception):
    pass


class NotFound(Exception):
    pass


def labs_of(person: Person) -> List[str]:
    """Every lab whose records this person sees: theirs, or their own without a lab."""
    names = [m['lab'] for m in person.labs if m.get('lab')] or ([person.lab] if person.lab else [])
    return names or [f'user:{person.username}']


def lab_of(person: Person, chosen: Optional[str] = None, strict: bool = False) -> str:
    """
    The lab a new record joins: the one chosen, of theirs, else their first;
    their own without a lab. strict: a lab chosen that is not theirs is refused.
    """
    names = labs_of(person)
    if chosen:
        found = next((n for n in names if n.casefold() == str(chosen).strip().casefold()), None)
        if found:
            return found
        if strict:
            raise ValueError('Choose one of your labs')
    return names[0]


def leads(person: Person, lab: str) -> bool:
    """Chooses this lab's code: its lead, an admin, or anyone for their own records without a lab."""
    return person.is_admin or person.leads(lab) or lab.startswith('user:')


def sees(person: Person) -> set:
    """The labs (casefolded) whose stocks this person sees: theirs, and the other labs of their chair groups."""
    cached = getattr(person, '_sees', None)
    if cached is None:
        from app import chairs
        own = {n.casefold() for n in labs_of(person)}
        cached = own | chairs.mates(own)
        person._sees = cached
    return cached


def can_see(person: Person, row) -> bool:
    return person.is_admin or (row['lab'] or '').casefold() in sees(person)


def can_change(person: Person, row) -> bool:
    """Their own lab's: a chair group's other labs see a stock, but do not change it."""
    return person.is_admin or (row['lab'] or '').casefold() in {n.casefold() for n in labs_of(person)}


def _text(value: Any, limit: int = 500) -> str:
    return str(value if value is not None else '').strip()[:limit]


def _date(value: Any) -> Optional[str]:
    v = _text(value, 10)
    if not v:
        return None
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', v):
        raise ValueError('Dates are written YYYY-MM-DD')
    return v


def cas_number(value: Any) -> str:
    """A CAS registry number, checked: 2-7 digits, 2 digits, and the check digit (e.g. 64-17-5)."""
    v = re.sub(r'\s', '', _text(value, 20))
    if not v:
        return ''
    m = CAS.fullmatch(v)
    if not m:
        raise ValueError('A CAS number is written like 64-17-5: 2 to 7 digits, 2 digits, and a check digit')
    digits = (m.group(1) + m.group(2))[::-1]
    if sum((i + 1) * int(d) for i, d in enumerate(digits)) % 10 != int(m.group(3)):
        raise ValueError(f'{v} is not a valid CAS number: its check digit does not match (a typing error?)')
    return v


def _log(conn, kind: str, record_id: str, by: str, what: str) -> None:
    conn.execute('INSERT INTO changes (record_kind, record_id, changed_by, what) VALUES (?, ?, ?, ?)',
                 (kind, record_id, by, what[:1000]))


# --- lab codes -------------------------------------------------------------------

def _seed_bank_code(lab: str) -> Optional[str]:
    """The lab's code in the Seed Bank, when it has one, so a lab is the same everywhere."""
    path = os.environ.get('SEEDS_DATABASE_PATH', '/seeds/seeds.db')
    if not os.path.exists(path):
        return None
    try:
        conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=5)
        try:
            row = conn.execute('SELECT code FROM lab_codes WHERE lab = ?', (lab,)).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    return row[0] if row else None


def _suggest(lab: str) -> str:
    if lab.startswith('user:'):
        letters = re.sub(r'[^A-Za-z]', '', lab[5:])[:3]
    else:
        words = re.findall(r'[A-Za-z0-9]+', lab)
        letters = ''.join(w[0] for w in words if w[0].isalpha())[:4]
        if len(letters) < 2:
            letters = re.sub(r'[^A-Za-z]', '', lab)[:3]
    return (letters or 'LAB').upper()


def lab_code(conn, lab: str) -> str:
    row = conn.execute('SELECT code FROM lab_codes WHERE lab = ?', (lab,)).fetchone()
    if row:
        return row['code']
    base = _seed_bank_code(lab) or _suggest(lab)
    code, n = base, 2
    while conn.execute('SELECT 1 FROM lab_codes WHERE code = ?', (code,)).fetchone():
        code, n = f'{base[:5]}{n}', n + 1
    conn.execute('INSERT INTO lab_codes (lab, code) VALUES (?, ?)', (lab, code))
    return code


def _has_records(conn, lab: str) -> bool:
    return any(conn.execute(f'SELECT 1 FROM {t} WHERE lab = ? LIMIT 1', (lab,)).fetchone() for t in TABLE.values())


def lab_info(person: Person, chosen: Optional[str] = None) -> dict:
    lab = lab_of(person, chosen)
    with connect() as conn:
        code = lab_code(conn, lab)
        fixed = _has_records(conn, lab)
    return {'lab': lab, 'code': code, 'fixed': fixed, 'labs': labs_of(person),
            'can_change': not fixed and leads(person, lab)}


def set_lab_code(person: Person, code: str, chosen: Optional[str] = None) -> dict:
    lab = lab_of(person, chosen, strict=True)
    code = (code or '').strip().upper()
    if not LAB_CODE.fullmatch(code):
        raise ValueError('A lab code is 1 to 6 letters and digits, starting with a letter, e.g. GL')
    if not leads(person, lab):
        raise Forbidden("Only the lab's lead or an administrator chooses the lab's code")
    with connect() as conn:
        if _has_records(conn, lab):
            raise ValueError('The lab already has stocks: its code is fixed, as codes on labels never change')
        if conn.execute('SELECT 1 FROM lab_codes WHERE code = ? AND lab != ?', (code, lab)).fetchone():
            raise ValueError(f"{code} is already another lab's code")
        conn.execute('INSERT INTO lab_codes (lab, code, set_by) VALUES (?, ?, ?) ON CONFLICT(lab) DO UPDATE '
                     'SET code = excluded.code, set_by = excluded.set_by, set_at = CURRENT_TIMESTAMP',
                     (lab, code, person.username))
    return lab_info(person, lab)


def _code(conn, kind: str, lab: str) -> str:
    prefix = f'{lab_code(conn, lab)}-{KINDS[kind]}'
    conn.execute('INSERT INTO counters (prefix, value) VALUES (?, 1) '
                 'ON CONFLICT(prefix) DO UPDATE SET value = value + 1', (prefix,))
    n = conn.execute('SELECT value FROM counters WHERE prefix = ?', (prefix,)).fetchone()[0]
    return f'{prefix}-{n:04d}'


def kind_of(code: str) -> Optional[str]:
    m = re.fullmatch(r'[A-Z][A-Z0-9]{0,5}-([GOCAM])-\d+', (code or '').strip().upper())
    return {'G': 'glycerol', 'O': 'primer', 'C': 'chemical', 'A': 'antibody', 'M': 'material'}[m.group(1)] if m else None


# --- reading ---------------------------------------------------------------------

def _row(conn, kind: str, ident: str):
    row = conn.execute(f'SELECT * FROM {TABLE[kind]} WHERE (id = ? OR code = ?) AND deleted_at IS NULL',
                       (ident, (ident or '').strip().upper())).fetchone()
    if row is None:
        raise NotFound(f'No such {NAMES[kind]}')
    return row


def visible(conn, person: Person, kind: str, ident: str):
    row = _row(conn, kind, ident)
    if not can_see(person, row):
        raise NotFound(f'No such {NAMES[kind]}')
    return row


def changeable(conn, person: Person, kind: str, ident: str):
    """A record this person may change: their own lab's."""
    row = visible(conn, person, kind, ident)
    if not can_change(person, row):
        raise Forbidden(f"This {NAMES[kind]} is {row['lab']}'s: only its own lab changes it")
    return row


def _out(kind: str, row, person: Optional[Person] = None) -> dict:
    out = {k: row[k] for k in row.keys()}
    out['kind'] = kind
    out['mine'] = person is None or can_change(person, row)
    if kind == 'primer':
        out.update(oligo.describe(row['sequence']))
    return out


def detail(person: Person, kind: str, ident: str) -> dict:
    from app import attachments
    with connect() as conn:
        row = visible(conn, person, kind, ident)
        out = _out(kind, row, person)
        out['attachments'] = attachments.listed(conn, kind, row['id'])
        if kind == 'chemical':
            # Its safety data sheet: the latest file captioned SDS.
            out['sds'] = next((a for a in reversed(out['attachments']) if a['caption'] == SDS), None)
        out['changes'] = [dict(r) for r in conn.execute(
            'SELECT changed_by, changed_at, what FROM changes WHERE record_kind = ? AND record_id = ? '
            'ORDER BY rowid DESC LIMIT 200', (kind, row['id']))]
        if kind not in ('glycerol', 'material'):
            from app import orders
            # Its order, when it is on the order list.
            out['order'] = orders.open_order(conn, row['code'])
        if kind == 'glycerol':
            from app import sources
            # Whether the plasmid it holds can be opened in the editor, and its name there now.
            out['plasmid'] = sources.plasmid(person, row['plasmid_id']) if row['plasmid_id'] else {'state': 'unlinked'}
        if kind == 'glycerol' and row['plasmid_id']:
            out['same_plasmid'] = [{'code': r['code'], 'clone': r['clone'], 'status': r['status']} for r in conn.execute(
                'SELECT * FROM glycerol WHERE plasmid_id = ? AND id != ? AND deleted_at IS NULL ORDER BY created_at',
                (row['plasmid_id'], row['id'])) if can_see(person, r)]
        return out


def list_records(person: Person, kind: str, q: str = '', plasmid: str = '', limit: int = 1000) -> List[dict]:
    q = (q or '').strip()
    like = f'%{q}%'
    with connect() as conn:
        if kind == 'chemical':
            sql = ("SELECT c.*, EXISTS (SELECT 1 FROM attachments a WHERE a.record_kind = 'chemical' AND "
                   'a.record_id = c.id AND a.caption = ? AND a.deleted_at IS NULL) AS has_sds FROM chemicals c '
                   'WHERE c.deleted_at IS NULL AND (c.code LIKE ? OR c.name LIKE ? OR c.cas LIKE ? OR c.room LIKE ? '
                   'OR c.size LIKE ? OR c.notes LIKE ?)')
            args = [SDS] + [like] * 6
            rows = conn.execute(sql + ' ORDER BY c.name COLLATE NOCASE, c.rowid', args).fetchall()
            return [_out(kind, r, person) for r in rows if can_see(person, r)][:limit]
        if kind == 'material':
            sql = ('SELECT * FROM material WHERE deleted_at IS NULL AND (code LIKE ? OR name LIKE ? OR tissue LIKE ? '
                   'OR species LIKE ? OR from_plant LIKE ? OR description LIKE ? OR experiment LIKE ? OR collected_by LIKE ? '
                   'OR location LIKE ? OR elab_layer_path LIKE ? OR notes LIKE ?) ORDER BY created_at DESC, rowid DESC')
            rows = conn.execute(sql, [like] * 11).fetchall()
            return [_out(kind, r, person) for r in rows if can_see(person, r)][:limit]
        if kind == 'antibody':
            sql = ('SELECT * FROM antibodies WHERE deleted_at IS NULL AND (code LIKE ? OR short_code LIKE ? '
                   'OR description LIKE ? OR type LIKE ? OR producer LIKE ? OR host LIKE ? OR product_number LIKE ? '
                   "OR notes LIKE ?) ORDER BY short_code = '', short_code COLLATE NOCASE, description COLLATE NOCASE, rowid")
            rows = conn.execute(sql, [like] * 8).fetchall()
            return [_out(kind, r, person) for r in rows if can_see(person, r)][:limit]
        if kind == 'glycerol':
            sql = ('SELECT * FROM glycerol WHERE deleted_at IS NULL AND (code LIKE ? OR plasmid_name LIKE ? OR clone LIKE ? '
                   'OR host LIKE ? OR selection LIKE ? OR location LIKE ? OR notes LIKE ?)')
            args: List[Any] = [like] * 7
            if plasmid:
                sql += ' AND plasmid_id = ?'
                args.append(plasmid)
        else:
            # Letters of DNA alone, four or more: also a piece of a primer's sequence.
            seq = re.sub(r'\s', '', q.upper())
            by_sequence = len(seq) >= 4 and not set(seq) - oligo.IUPAC
            sql = ('SELECT * FROM primers WHERE deleted_at IS NULL AND (code LIKE ? OR name LIKE ? OR target LIKE ? '
                   'OR purpose LIKE ? OR location LIKE ? OR notes LIKE ? OR mod5 LIKE ? OR mod3 LIKE ? OR modifications LIKE ?'
                   + (' OR sequence LIKE ?' if by_sequence else '') + ')')
            args = [like] * 9 + ([f'%{seq}%'] if by_sequence else [])
        rows = conn.execute(sql + ' ORDER BY created_at DESC, rowid DESC', args).fetchall()
    return [_out(kind, r, person) for r in rows if can_see(person, r)][:limit]


def search(person: Person, q: str, limit: int = 20) -> List[dict]:
    """Glycerol stocks, primers, chemicals and antibodies by code or name, for links from elsewhere (the notebook)."""
    q = (q or '').strip()
    found = [dict(kind='glycerol', code=r['code'], label=f"{r['code']} {r['plasmid_name']}"
                  + (f" clone {r['clone']}" if r['clone'] else '')) for r in list_records(person, 'glycerol', q, limit=limit)]
    found += [dict(kind='primer', code=r['code'], label=f"{r['code']} {r['name']}") for r in list_records(person, 'primer', q, limit=limit)]
    found += [dict(kind='chemical', code=r['code'], label=f"{r['code']} {r['name']}" + (f" (CAS {r['cas']})" if r['cas'] else ''))
              for r in list_records(person, 'chemical', q, limit=limit)]
    found += [dict(kind='antibody', code=r['code'], label=f"{r['code']} " + ' '.join(
                   filter(None, [r['short_code'], r['description'] if not r['short_code'] else '',
                                 f"({', '.join(filter(None, [r['type'], r['host']]))})"])))
              for r in list_records(person, 'antibody', q, limit=limit)]
    found += [dict(kind='material', code=r['code'], label=f"{r['code']} {r['name']}"
                   + (f" ({', '.join(filter(None, [r['tissue'], r['species'] or r['from_plant']]))})" if r['tissue'] or r['species'] or r['from_plant'] else ''))
              for r in list_records(person, 'material', q, limit=limit)]
    exact = [f for f in found if f['code'].upper() == q.upper()]
    return (exact + [f for f in found if f not in exact])[:limit]


# --- changing --------------------------------------------------------------------

def _glycerol_fields(data: dict, partial: bool) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, limit in (('plasmid_id', 80), ('plasmid_name', 200), ('clone', 60), ('host', 120),
                       ('selection', 120), ('location', 200), ('notes', 5000), ('permit', 120),
                       ('plant_markers', 200), ('yeast_markers', 200), ('gene_ids', 300), ('donor', 200),
                       ('harmful_notes', 2000), ('elab_layer_path', 500)):
        if key in data or not partial:
            out[key] = _text(data.get(key), limit)
    # Where it is kept in eLab's storage: a compartment's number there, and a place in a box.
    for key in ('elab_layer_id', 'elab_position'):
        if key in data or not partial:
            v = _text(data.get(key), 12)
            if v and not v.isdigit():
                raise ValueError('A storage location in eLab is chosen from the list')
            out[key] = v
    if out.get('elab_layer_id') == '':
        out['elab_layer_path'], out['elab_position'] = '', ''
    for key, allowed, what in (('biosafety', BIOSAFETY, 'biosafety level'), ('host_system', HOST_SYSTEMS, 'host system'),
                               ('inserts', YES_NO, 'insert(s)'), ('harmful', HARMFUL, 'harmful gene product')):
        if key in data or not partial:
            v = _text(data.get(key))
            if v not in allowed:
                raise ValueError(f'{what} must be one of {", ".join(a for a in allowed if a)}, or empty')
            out[key] = v
    if 'made_on' in data or not partial:
        out['made_on'] = _date(data.get('made_on'))
    if 'status' in data or not partial:
        s = _text(data.get('status')) or 'in stock'
        if s not in STATUS:
            raise ValueError(f'status must be one of {", ".join(STATUS)}')
        out['status'] = s
    if not partial and not (out['plasmid_id'] or out['plasmid_name']):
        raise ValueError('Which plasmid is in this glycerol stock?')
    return out


def _primer_fields(data: dict, partial: bool) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if 'name' in data or not partial:
        out['name'] = _text(data.get('name'), 120)
        if not out['name']:
            raise ValueError('A primer needs a name')
    if 'sequence' in data or not partial:
        out['sequence'] = oligo.clean(data.get('sequence'))
    if 'direction' in data or not partial:
        d = _text(data.get('direction'))
        if d not in DIRECTIONS:
            raise ValueError('direction is forward, reverse, or empty')
        out['direction'] = d
    for key, limit in (('target', 200), ('purpose', 300), ('modifications', 200), ('mod5', 60), ('mod3', 60),
                       ('supplier', 120), ('concentration', 60), ('location', 200), ('notes', 5000)):
        if key in data or not partial:
            out[key] = _text(data.get(key), limit)
    if 'ordered_on' in data or not partial:
        out['ordered_on'] = _date(data.get('ordered_on'))
    if 'status' in data or not partial:
        s = _text(data.get('status')) or 'in stock'
        if s not in STATUS:
            raise ValueError(f'status must be one of {", ".join(STATUS)}')
        out['status'] = s
    return out


def ordered_as(rec) -> str:
    """A primer as an oligo is ordered: 5'-[FAM]ACGT...[BHQ-1]-3' (17 nt), with any other modifications."""
    keys = rec.keys() if hasattr(rec, 'keys') else rec
    mod5 = rec['mod5'] if 'mod5' in keys else ''
    mod3 = rec['mod3'] if 'mod3' in keys else ''
    out = (f"5′-{f'[{mod5}]' if mod5 else ''}{rec['sequence']}{f'[{mod3}]' if mod3 else ''}-3′ "
           f"({len(rec['sequence'])} nt)")
    if mod5 or mod3:
        out += '; ' + ', '.join(filter(None, [mod5 and f"5′ {mod5}", mod3 and f"3′ {mod3}"]))
    if rec['modifications']:
        out += f"; other modifications: {rec['modifications']}"
    return out


def _chemical_fields(data: dict, partial: bool) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if 'name' in data or not partial:
        out['name'] = _text(data.get('name'), 200)
        if not out['name']:
            raise ValueError('A chemical needs a name')
    if 'cas' in data or not partial:
        out['cas'] = cas_number(data.get('cas'))
    for key, limit in (('room', 120), ('size', 60), ('notes', 5000)):
        if key in data or not partial:
            out[key] = _text(data.get(key), limit)
    if 'status' in data or not partial:
        s = _text(data.get('status')) or 'in stock'
        if s not in CHEMICAL_STATUS:
            raise ValueError(f'status must be one of {", ".join(CHEMICAL_STATUS)}')
        out['status'] = s
    return out


def _antibody_fields(data: dict, partial: bool) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, limit in (('short_code', 60), ('description', 300), ('producer', 120), ('host', 60),
                       ('product_number', 80), ('notes', 5000)):
        if key in data or not partial:
            out[key] = _text(data.get(key), limit)
    if not partial and not (out['short_code'] or out['description']):
        raise ValueError('An antibody needs its short code in the lab or a description')
    if 'type' in data or not partial:
        t = (_text(data.get('type')) or 'primary').lower()
        if t not in ANTIBODY_TYPES:
            raise ValueError(f'type must be one of {", ".join(ANTIBODY_TYPES)}')
        out['type'] = t
    if 'status' in data or not partial:
        s = _text(data.get('status')) or 'in stock'
        if s not in STATUS:
            raise ValueError(f'status must be one of {", ".join(STATUS)}')
        out['status'] = s
    return out


def _material_fields(data: dict, partial: bool) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if 'name' in data or not partial:
        out['name'] = _text(data.get('name'), 120)
        if not out['name']:
            raise ValueError('Plant material needs a name: what is written on the tube')
    for key, limit in (('tissue', 80), ('species', 120), ('from_plant', 120), ('description', 500), ('collected_by', 120),
                       ('experiment', 200), ('location', 200), ('elab_layer_path', 500), ('notes', 5000)):
        if key in data or not partial:
            out[key] = _text(data.get(key), limit)
    if 'collected_on' in data or not partial:
        out['collected_on'] = _date(data.get('collected_on'))
    for key in ('elab_layer_id', 'elab_position'):
        if key in data or not partial:
            v = _text(data.get(key), 12)
            if v and not v.isdigit():
                raise ValueError('A storage location in eLab is chosen from the list')
            out[key] = v
    if out.get('elab_layer_id') == '':
        out['elab_layer_path'], out['elab_position'] = '', ''
    if 'status' in data or not partial:
        s = _text(data.get('status')) or 'in stock'
        if s not in STATUS:
            raise ValueError(f'status must be one of {", ".join(STATUS)}')
        out['status'] = s
    return out


FIELDS = {'glycerol': _glycerol_fields, 'primer': _primer_fields, 'chemical': _chemical_fields,
          'antibody': _antibody_fields, 'material': _material_fields}


MANY = 500                  # plant material made at once, at most: a few boxes of tubes


def create_material(person: Person, items: List[dict], shared: dict, lab: Optional[str] = None,
                    owners: Optional[List[str]] = None) -> List[str]:
    """
    Several tubes of plant material at once (a box of them): each item its own name and fields, the
    shared fields for all. Gives their ids, in order. All or none are made. owners: brought over from
    eLab, each tube's owner there, who made it (the history says who brought it over).
    """
    items = [i for i in (items or []) if isinstance(i, dict)]
    if not items:
        raise ValueError('Give the names of the tubes')
    if len(items) > MANY:
        raise ValueError(f'At most {MANY} tubes at once')
    lab = lab_of(person, lab, strict=True)
    rows = [_material_fields({**(shared or {}), **i}, partial=False) for i in items]
    made = []
    with connect() as conn:
        for n, fields in enumerate(rows):
            record_id = secrets.token_hex(12)
            code = _code(conn, 'material', lab)
            if owners is not None:
                fields = {**fields, 'source': 'elab'}
            cols = ['id', 'code', 'lab', 'created_by', *fields]
            conn.execute(f'INSERT INTO material ({", ".join(cols)}) VALUES ({", ".join("?" * len(cols))})',
                         (record_id, code, lab, (owners[n] if owners is not None else '') or person.username, *fields.values()))
            _log(conn, 'material', record_id, person.username, f'created {code}' + (
                ' (brought over from eLab)' if owners is not None else ' (one of several)' if len(rows) > 1 else ''))
            made.append(record_id)
    elab.nudge()
    return made


def create(person: Person, kind: str, data: dict, owner: Optional[str] = None) -> str:
    return create_noting(person, kind, data, owner)[0]


def create_noting(person: Person, kind: str, data: dict, owner: Optional[str] = None):
    """
    Makes a record; gives its id, and what it did to the order list (a chemical made out), or None.
    owner: a glycerol stock brought over from eLab, its owner there, who made it (the history says who
    brought it over).
    """
    fields = FIELDS[kind](data, partial=False)
    if kind == 'glycerol':
        fields['source'] = 'elab' if owner is not None else 'sequencing' if data.get('source') == 'sequencing' else 'manual'
    lab = lab_of(person, data.get('lab'), strict=True)
    with connect() as conn:
        record_id = secrets.token_hex(12)
        code = _code(conn, kind, lab)
        cols = ['id', 'code', 'lab', 'created_by', *fields]
        conn.execute(f'INSERT INTO {TABLE[kind]} ({", ".join(cols)}) VALUES ({", ".join("?" * len(cols))})',
                     (record_id, code, lab, owner or person.username, *fields.values()))
        _log(conn, kind, record_id, person.username,
             f'created {code}' + {'sequencing': ' on confirming the plasmid by sequencing',
                                  'elab': ' (brought over from eLab)'}.get(fields.get('source'), ''))
        ordered = None
        if kind == 'chemical' and fields['status'] == 'out':
            from app import orders
            ordered = orders.chemical_status_changed(conn, person, _row(conn, kind, record_id), 'in stock', 'out')
    elab.nudge()
    return record_id, ordered


def update(person: Person, kind: str, ident: str, data: dict) -> Optional[str]:
    """Changes a record; gives what that did to the order list (a chemical marked out or in stock), or None."""
    fields = FIELDS[kind](data, partial=True)
    if kind == 'glycerol' and fields.get('plasmid_id'):
        # Linked to a plasmid of the editor's library: one this person may open, named as it is there.
        from app import sources
        found = sources.plasmid(person, fields['plasmid_id'])
        if found['state'] != 'open':
            raise ValueError("That plasmid is not in the Plasmid Editor's library, or is not one you may open")
        fields['plasmid_id'], fields['plasmid_name'] = found['id'], found['name']
    elif kind == 'glycerol' and 'plasmid_id' in fields:
        fields.pop('plasmid_id')            # a link is changed, not taken away
    with connect() as conn:
        row = changeable(conn, person, kind, ident)
        changes = [f'{k}: {row[k]!r} → {v!r}' for k, v in fields.items() if row[k] != v]
        if fields:
            conn.execute(f'UPDATE {TABLE[kind]} SET {", ".join(f"{k} = ?" for k in fields)}, '
                         'updated_at = CURRENT_TIMESTAMP WHERE id = ?', (*fields.values(), row['id']))
        if changes:
            _log(conn, kind, row['id'], person.username, '; '.join(changes))
        ordered = None
        if kind == 'chemical' and fields.get('status', row['status']) != row['status']:
            from app import orders
            ordered = orders.chemical_status_changed(conn, person, _row(conn, kind, row['id']), row['status'], fields['status'])
    elab.nudge()
    return ordered


def take_from_elab(kind: str, record_id: str, data: dict, by: str) -> List[str]:
    """
    Values changed in eLab, taken here (eLab is right): checked as any change is, and in the history as
    changed in eLab. Gives the fields that changed.
    """
    fields = FIELDS[kind](data, partial=True)
    with connect() as conn:
        row = _row(conn, kind, record_id)
        fields = {k: v for k, v in fields.items() if row[k] != v}
        if fields:
            conn.execute(f'UPDATE {TABLE[kind]} SET {", ".join(f"{k} = ?" for k in fields)}, '
                         'updated_at = CURRENT_TIMESTAMP WHERE id = ?', (*fields.values(), row['id']))
            _log(conn, kind, row['id'], by, 'changed in eLab: ' + '; '.join(f'{k}: {row[k]!r} → {v!r}' for k, v in fields.items()))
    return list(fields)


def delete(person: Person, kind: str, ident: str) -> None:
    with connect() as conn:
        row = changeable(conn, person, kind, ident)
        conn.execute(f'UPDATE {TABLE[kind]} SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?', (row['id'],))
        _log(conn, kind, row['id'], person.username, f'deleted {row["code"]}')
    elab.nudge()


def all_primers(person: Person) -> List[dict]:
    """Every primer of the lab still in stock, with its sequence: for finding where they bind."""
    return [{'code': p['code'], 'name': p['name'], 'sequence': p['sequence'], 'tm': p['tm'],
             'direction': p['direction'], 'location': p['location']}
            for p in list_records(person, 'primer') if p['status'] == 'in stock' and p['mine']]
