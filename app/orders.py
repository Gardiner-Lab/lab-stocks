"""
The order list: what a lab needs ordered, and its lab admin ordering it.

Anyone in a lab asks for something to be ordered: from a chemical, primer or
antibody's page (its details come along), or with the order request form for
anything else (an enzyme, a kit, tips). A chemical marked out is put on the list
by itself. A lab's lab admins (and administrators) see all of the lab's orders,
and no other lab's; they mark them ordered, then received, or cancel them.
Everyone else sees the requests they made.

    requested -> ordered -> received        or cancelled, before it is received

When an order for a stock arrives, the stock is back in stock. Every change is
logged, as for stocks.
"""

import csv
import io
from typing import Any, Dict, List, Optional

from app.db import connect
from app.people import Person
from app.records import Forbidden, NotFound, _log, _text, can_see, kind_of, lab_of, labs_of, visible

STATUS = ('requested', 'ordered', 'received', 'cancelled')
OPEN = ('requested', 'ordered')
CATEGORIES = ('chemical', 'primer', 'antibody', 'enzyme', 'kit', 'consumable', 'other')
# A stock that ran out goes back in stock when its order arrives.
RESTOCK = {'chemical': ('out',), 'primer': ('used up',), 'antibody': ('used up',)}


def _out(row, person: Person) -> dict:
    out = {k: row[k] for k in row.keys()}
    out['urgent'] = bool(row['urgent'])
    out['auto'] = bool(row['auto'])
    out['can_handle'] = person.administers(row['lab'])
    out['can_change'] = out['can_handle'] or (row['requested_by'] == person.username and row['status'] == 'requested')
    return out


def _sees(person: Person, row) -> bool:
    return person.administers(row['lab']) or (row['requested_by'] == person.username and can_see(person, row))


def _row(conn, person: Person, order_id) -> Any:
    try:
        n = int(order_id)
    except (TypeError, ValueError):
        raise NotFound('No such order')
    row = conn.execute('SELECT * FROM orders WHERE id = ?', (n,)).fetchone()
    if row is None or not _sees(person, row):
        raise NotFound('No such order')
    return row


def handles(person: Person) -> List[str]:
    """The labs whose orders this person handles."""
    if person.is_admin:
        with connect() as conn:
            return sorted({r['lab'] for r in conn.execute('SELECT DISTINCT lab FROM orders')} | set(labs_of(person)))
    return [lab for lab in labs_of(person) if person.administers(lab)]


def waiting(person: Person) -> int:
    """How many requests wait to be ordered in the labs this person handles: the number on the Orders tab."""
    labs = {lab.casefold() for lab in handles(person)}
    if not labs:
        return 0
    with connect() as conn:
        rows = conn.execute("SELECT lab FROM orders WHERE status = 'requested'").fetchall()
    return sum(1 for r in rows if person.is_admin or r['lab'].casefold() in labs)


def list_orders(person: Person, status: str = '', q: str = '', limit: int = 500) -> List[dict]:
    like = f'%{(q or "").strip()}%'
    sql = ('SELECT * FROM orders WHERE (item LIKE ? OR supplier LIKE ? OR product_number LIKE ? OR details LIKE ? '
           'OR notes LIKE ? OR requested_by LIKE ? OR record_code LIKE ?)')
    args: List[Any] = [like] * 7
    if status == 'open':
        sql += " AND status IN ('requested', 'ordered')"
    elif status == 'closed':
        sql += " AND status IN ('received', 'cancelled')"
    elif status:
        if status not in STATUS:
            raise ValueError(f'status must be one of {", ".join(STATUS)}')
        sql += ' AND status = ?'
        args.append(status)
    with connect() as conn:
        rows = conn.execute(sql + ' ORDER BY urgent DESC, requested_at DESC, id DESC', args).fetchall()
    return [_out(r, person) for r in rows if _sees(person, r)][:limit]


def open_order(conn, code: str) -> Optional[dict]:
    """The order still open for a stock, if there is one: shown on its page."""
    row = conn.execute("SELECT id, status, requested_by, requested_at, ordered_at, auto FROM orders "
                       "WHERE record_code = ? AND status IN ('requested', 'ordered') ORDER BY id DESC", (code,)).fetchone()
    return dict(row) if row else None


def _from_record(conn, person: Person, code: str) -> Dict[str, Any]:
    """What an order of this stock says: its name and details, as the stock has them."""
    kind = kind_of(code)
    if kind is None:
        raise NotFound('No such stock')
    if kind == 'glycerol':
        raise ValueError('Glycerol stocks are made in the lab, not ordered')
    rec = visible(conn, person, kind, code)
    base = {'record_kind': kind, 'record_code': rec['code'], 'lab': rec['lab'], 'category': kind}
    if kind == 'chemical':
        return {**base, 'item': rec['name'], 'quantity': rec['size'],
                'details': f"CAS {rec['cas']}" if rec['cas'] else ''}
    if kind == 'primer':
        details = f"5′-{rec['sequence']}-3′ ({len(rec['sequence'])} nt)"
        if rec['modifications']:
            details += f"; modifications: {rec['modifications']}"
        return {**base, 'item': rec['name'], 'supplier': rec['supplier'], 'details': details}
    return {**base, 'item': rec['description'] or rec['short_code'], 'supplier': rec['producer'],
            'product_number': rec['product_number'],
            'details': ', '.join(filter(None, [rec['short_code'] and f"short code {rec['short_code']}",
                                               rec['type'] and f"{rec['type']} antibody",
                                               rec['host'] and f"raised in {rec['host']}"]))}


def create_many(person: Person, data: dict) -> dict:
    """Several stocks at once (primers ticked in the list), one order each, with the same quantity and note."""
    codes = [c for c in dict.fromkeys(_text(c, 40).upper() for c in (data.get('records') or [])[:200]) if c]
    if not codes:
        raise ValueError('Tick what should be ordered')
    common = {k: data[k] for k in ('quantity', 'notes', 'urgent') if k in data}
    made, already = [], []
    for code in codes:
        result = create(person, {**common, 'record': code})
        (already if result['already'] else made).append(result['order'])
    return {'made': made, 'already': already}


def open_codes(conn) -> set:
    """The stocks with an order still open: marked 🛒 in the lists."""
    return {r[0] for r in conn.execute("SELECT record_code FROM orders WHERE record_code IS NOT NULL "
                                       "AND status IN ('requested', 'ordered')")}


def _fields(data: dict, partial: bool) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, limit in (('item', 300), ('quantity', 120), ('supplier', 120), ('product_number', 120),
                       ('details', 1000), ('link', 1000), ('notes', 5000)):
        if key in data or not partial:
            out[key] = _text(data.get(key), limit)
    if out.get('link') and not out['link'].lower().startswith(('http://', 'https://')):
        raise ValueError('A link starts with http:// or https://')
    if 'category' in data or not partial:
        c = (_text(data.get('category')) or 'other').lower()
        if c not in CATEGORIES:
            raise ValueError(f'category must be one of {", ".join(CATEGORIES)}')
        out['category'] = c
    if 'urgent' in data or not partial:
        out['urgent'] = 1 if data.get('urgent') in (True, 1, '1', 'true', 'on') else 0
    return out


def _insert(conn, person: Person, lab: str, fields: Dict[str, Any], auto: bool = False) -> int:
    cols = ['lab', 'requested_by', 'auto', *fields]
    cur = conn.execute(f'INSERT INTO orders ({", ".join(cols)}) VALUES ({", ".join("?" * len(cols))})',
                       (lab, person.username, 1 if auto else 0, *fields.values()))
    n = cur.lastrowid
    _log(conn, 'order', str(n), person.username,
         f"asked for {fields['item']}" + (f" ({fields['record_code']})" if fields.get('record_code') else '')
         + (' on marking it out' if auto else ''))
    return n


def create(person: Person, data: dict) -> dict:
    """
    An order request. With 'record' (a stock's code) the stock's details come
    along; when that stock is already on the list, that order is given back
    (with 'already') instead of a second one.
    """
    with connect() as conn:
        code = _text(data.get('record'), 40).upper()
        if code:
            stock = _from_record(conn, person, code)
            found = open_order(conn, stock['record_code'])
            if found:
                row = conn.execute('SELECT * FROM orders WHERE id = ?', (found['id'],)).fetchone()
                return {'order': _out(row, person) if _sees(person, row) else found, 'already': True}
            lab = stock.pop('lab')
            # What the stock says, and what the request adds to it (how many, a note, urgent).
            given = {k: v for k, v in _fields(data, partial=True).items() if v not in ('', None)}
            fields = {**_fields({}, partial=False), **stock, **given,
                      **{k: stock[k] for k in ('category', 'record_kind', 'record_code')}}
        else:
            fields = _fields(data, partial=False)
            lab = lab_of(person, data.get('lab'), strict=True)
        if not fields['item']:
            raise ValueError('What should be ordered?')
        n = _insert(conn, person, lab, fields)
        return {'order': _out(_row(conn, person, n), person), 'already': False}


def detail(person: Person, order_id) -> dict:
    with connect() as conn:
        row = _row(conn, person, order_id)
        out = _out(row, person)
        out['changes'] = [dict(r) for r in conn.execute(
            "SELECT changed_by, changed_at, what FROM changes WHERE record_kind = 'order' AND record_id = ? "
            'ORDER BY rowid DESC LIMIT 200', (str(row['id']),))]
        return out


def update(person: Person, order_id, data: dict) -> dict:
    with connect() as conn:
        row = _row(conn, person, order_id)
        handler = person.administers(row['lab'])
        fields = _fields(data, partial=True)
        status = _text(data.get('status')) if 'status' in data else None
        if status is not None and status != row['status']:
            if status not in STATUS:
                raise ValueError(f'status must be one of {", ".join(STATUS)}')
            mine = row['requested_by'] == person.username and row['status'] == 'requested' and status == 'cancelled'
            if not handler and not mine:
                raise Forbidden("Only the lab's lab admin marks orders ordered or received")
            fields['status'] = status
            stamp = {'ordered': 'ordered', 'received': 'received', 'cancelled': 'closed'}[status] \
                if status != 'requested' else None
            if stamp:
                fields[f'{stamp}_by'] = person.username
        elif not handler and not (row['requested_by'] == person.username and row['status'] == 'requested'):
            raise Forbidden('Only the lab admin changes a request once it is being ordered')
        if 'item' in fields and not fields['item']:
            raise ValueError('What should be ordered?')
        changes = [f'{k}: {row[k]!r} → {v!r}' for k, v in fields.items() if row[k] != v and not k.endswith('_by')]
        if fields:
            stamps = ''.join(f', {s}_at = CURRENT_TIMESTAMP' for s in ('ordered', 'received', 'closed')
                             if fields.get(f'{s}_by'))
            conn.execute(f'UPDATE orders SET {", ".join(f"{k} = ?" for k in fields)}, updated_at = CURRENT_TIMESTAMP'
                         f'{stamps} WHERE id = ?', (*fields.values(), row['id']))
        if changes:
            _log(conn, 'order', str(row['id']), person.username, '; '.join(changes))
        if fields.get('status') == 'received' and row['record_code']:
            _restock(conn, person, row)
    return detail(person, order_id)


def _restock(conn, person: Person, order) -> None:
    """The stock an order was for is back in stock, when it had run out."""
    from app.records import TABLE
    kind = order['record_kind']
    if kind not in RESTOCK:
        return
    rec = conn.execute(f'SELECT id, status FROM {TABLE[kind]} WHERE code = ? AND deleted_at IS NULL',
                       (order['record_code'],)).fetchone()
    if rec and rec['status'] in RESTOCK[kind]:
        conn.execute(f"UPDATE {TABLE[kind]} SET status = 'in stock', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (rec['id'],))
        _log(conn, kind, rec['id'], person.username, f"status: {rec['status']!r} → 'in stock' (order {order['id']} received)")


def chemical_status_changed(conn, person: Person, rec, old: str, new: str) -> Optional[str]:
    """
    A chemical marked out goes on the order list by itself (unless it is on it
    already); marked in stock again before it was ordered, that request is
    taken back. Returns what happened, for the person who switched it.
    """
    if new == 'out' and old != 'out':
        if open_order(conn, rec['code']):
            return 'already on the order list'
        fields = {**_fields({}, partial=False), 'item': rec['name'], 'quantity': rec['size'],
                  'details': f"CAS {rec['cas']}" if rec['cas'] else '', 'category': 'chemical',
                  'record_kind': 'chemical', 'record_code': rec['code']}
        _insert(conn, person, rec['lab'], fields, auto=True)
        return 'added to the order list'
    if old == 'out' and new != 'out':
        found = conn.execute("SELECT id FROM orders WHERE record_code = ? AND status = 'requested' AND auto = 1",
                             (rec['code'],)).fetchone()
        if found:
            conn.execute("UPDATE orders SET status = 'cancelled', closed_by = ?, closed_at = CURRENT_TIMESTAMP, "
                         'updated_at = CURRENT_TIMESTAMP WHERE id = ?', (person.username, found['id']))
            _log(conn, 'order', str(found['id']), person.username, 'cancelled: the chemical is in stock again')
            return 'taken off the order list'
    return None


CSV_COLUMNS = (('id', 'Order'), ('lab', 'Lab'), ('item', 'Item'), ('category', 'Category'), ('quantity', 'Quantity'),
               ('supplier', 'Supplier'), ('product_number', 'Product number'), ('details', 'Details'),
               ('record_code', 'Stock'), ('sequence', 'Sequence'), ('link', 'Link'), ('notes', 'Notes'), ('urgent', 'Urgent'),
               ('requested_by', 'Asked by'), ('requested_at', 'Asked on'), ('status', 'Status'),
               ('ordered_by', 'Ordered by'), ('ordered_at', 'Ordered on'))


def as_csv(person: Person, status: str = '', q: str = '') -> str:
    """The orders in a spreadsheet, for filling in a supplier's order form."""
    buf = io.StringIO()
    out = csv.writer(buf)
    out.writerow([title for _, title in CSV_COLUMNS])
    found = list_orders(person, status, q, limit=100000)
    # A primer's sequence on its own, for a supplier's bulk order form.
    with connect() as conn:
        sequences = {r['code']: r['sequence'] for r in conn.execute('SELECT code, sequence FROM primers')}
    for o in found:
        o['sequence'] = sequences.get(o['record_code'], '') if o['record_kind'] == 'primer' else ''
        cells = []
        for key, _ in CSV_COLUMNS:
            v = o.get(key)
            v = ('yes' if v else '') if key == 'urgent' else ('' if v is None else str(v))
            # Not read as a formula by a spreadsheet.
            cells.append("'" + v if v[:1] in ('=', '+', '-', '@') else v)
        out.writerow(cells)
    return '﻿' + buf.getvalue()
