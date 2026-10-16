"""
What Lab Stocks reads from the other tools, never changing it.

    Plasmids        from the Plasmid Editor's library: the plasmid a glycerol
                    stock holds; a plasmid opens in the editor.
    Notebook pages  that link to a glycerol stock or primer (data-stock="GL-G-0042"),
                    shown on that record to whoever may open the page.
"""

import os
import sqlite3
from typing import List

from app.people import Person


def _read(path: str, sql: str, args=()) -> List[sqlite3.Row]:
    if not path or not os.path.exists(path):
        return []
    try:
        conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql, args).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return []


def plasmids(person: Person, query: str = '', limit: int = 25) -> List[dict]:
    """Plasmids in the editor's library this person may open, best matches first."""
    q = (query or '').strip()
    rows = _read(os.environ.get('EDITOR_DATABASE_PATH', '/editor/plasmid_editor.db'),
                 'SELECT s.id, s.name, length(s.sequence) AS length, s.shared, s.confirmed_at, u.username AS owner '
                 'FROM sequences s LEFT JOIN users u ON u.id = s.owner_id '
                 "WHERE (? = '' OR s.name LIKE ?) ORDER BY CASE WHEN s.name LIKE ? THEN 0 ELSE 1 END, "
                 's.updated_at DESC LIMIT 400', (q, f'%{q}%', f'{q}%'))
    found = []
    for r in rows:
        if r['shared'] or person.oversees(r['owner']):
            found.append({'id': r['id'], 'name': r['name'], 'length': r['length'], 'owner': r['owner'],
                          'confirmed': bool(r['confirmed_at'])})
        if len(found) >= limit:
            break
    return found


def plasmid(person: Person, plasmid_id: str) -> dict:
    """
    A plasmid in the editor's library, as a stock links to it: {'state': 'open'}
    with its id and name when this person may open it, 'private' when it is
    someone's own (not shared), 'missing' when it is not in the library.
    """
    rows = _read(os.environ.get('EDITOR_DATABASE_PATH', '/editor/plasmid_editor.db'),
                 'SELECT s.id, s.name, s.shared, u.username AS owner FROM sequences s '
                 'LEFT JOIN users u ON u.id = s.owner_id WHERE s.id = ?', (plasmid_id or '',))
    if not rows:
        return {'state': 'missing'}
    r = rows[0]
    if r['shared'] or person.oversees(r['owner']):
        return {'state': 'open', 'id': r['id'], 'name': r['name']}
    return {'state': 'private', 'owner': r['owner']}


def notebook_mentions(person: Person, code: str) -> List[dict]:
    """Notebook pages that link to this record, which this person may open."""
    rows = _read(os.environ.get('NOTEBOOK_DATABASE_PATH', '/notebook/notebook.db'),
                 "SELECT n.id, n.title, n.type, n.owner, n.updated_at FROM links l JOIN notes n ON n.id = l.note_id "
                 "WHERE l.target_type = 'stock' AND l.target_id = ? AND n.deleted_at IS NULL "
                 'ORDER BY n.updated_at DESC LIMIT 100', (code,))
    return [dict(r) for r in rows if r['owner'] is None or person.oversees(r['owner'])]
