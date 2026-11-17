"""
A lab's ways of getting rid of chemicals ("Halogenated organic waste: the yellow
can in the fume hood of O.703"), kept by its lab admin. A chemical's form offers
them as a list to choose from; the chemical keeps the words chosen (its disposal
column), so changing the list later leaves what was recorded as it was.
"""

import secrets
from typing import List, Optional

from app import records
from app.db import connect
from app.people import Person

MAX_ROUTES = 50
MAX_TEXT = 300


def _lab(person: Person, lab: Optional[str]) -> str:
    """One of their labs; an administrator, any lab named."""
    if lab and person.is_admin:
        return str(lab).strip()
    return records.lab_of(person, lab, strict=True)


def routes(person: Person, lab: Optional[str] = None) -> dict:
    lab = _lab(person, lab)
    with connect() as conn:
        rows = conn.execute('SELECT text FROM disposal_routes WHERE lab = ? ORDER BY position, rowid', (lab,)).fetchall()
    return {'lab': lab, 'routes': [r['text'] for r in rows], 'can_set': person.administers(lab)}


def set_routes(person: Person, lab: Optional[str], texts) -> dict:
    lab = _lab(person, lab)
    if not person.administers(lab):
        raise records.Forbidden("Only the lab's lab admin changes its disposal routes")
    if not isinstance(texts, list):
        raise ValueError('routes must be a list')
    clean: List[str] = []
    for t in texts:
        t = ' '.join(str(t or '').split())
        if len(t) > MAX_TEXT:
            raise ValueError(f'Keep each disposal route to {MAX_TEXT} characters')
        if t and t.casefold() not in {c.casefold() for c in clean}:
            clean.append(t)
    if len(clean) > MAX_ROUTES:
        raise ValueError(f'At most {MAX_ROUTES} disposal routes')
    with connect() as conn:
        conn.execute('DELETE FROM disposal_routes WHERE lab = ?', (lab,))
        for i, t in enumerate(clean):
            conn.execute('INSERT INTO disposal_routes (id, lab, text, position, updated_by) VALUES (?, ?, ?, ?, ?)',
                         (secrets.token_hex(8), lab, t, i, person.username))
    return routes(person, lab)
