"""
Chair groups: labs that work together (a university chair, a department), and
share what they have.

They are the suite's: an administrator puts labs in chair groups on the
dashboard's Labs tab, kept in the suite's database (suite.db: chair_groups, and
labs.chair_group_id), which is read here, never written. A lab is in one at
most. Labs of a chair group see each other's stocks (without changing them).
Each lab still sends its own stocks to eLab with its own token (app/elab.py),
where a sample's owner says whose it is.
"""

import os
from typing import List, Optional, Set

from app.people import Person
from app.sources import _read


def _path() -> str:
    return os.environ.get('SUITE_DATABASE_PATH', '/suite/suite.db')


def _known() -> bool:
    """A suite with chair groups (2.9.0 on)."""
    return 'chair_group_id' in {r['name'] for r in _read(_path(), 'PRAGMA table_info(labs)')}


def _group(lab: str):
    if not _known():
        return None
    rows = _read(_path(), 'SELECT g.id, g.name FROM labs l JOIN chair_groups g ON g.id = l.chair_group_id '
                          'WHERE l.name = ? COLLATE NOCASE', (lab,))
    return rows[0] if rows else None


def name_of(lab: str) -> Optional[str]:
    """The name of the lab's chair group, or None."""
    row = _group(lab)
    return row['name'] if row else None


def labs_in(group_id) -> List[str]:
    return [r['name'] for r in _read(_path(), 'SELECT name FROM labs WHERE chair_group_id = ? ORDER BY name COLLATE NOCASE',
                                     (group_id,))]


def mates(labs: Set[str]) -> Set[str]:
    """Every lab (casefolded) in a chair group with one of these labs (casefolded)."""
    if not labs or not _known():
        return set()
    rows = _read(_path(), 'SELECT m.name FROM labs l JOIN labs m ON m.chair_group_id = l.chair_group_id '
                          f'WHERE l.chair_group_id IS NOT NULL AND lower(l.name) IN ({", ".join("?" * len(labs))})',
                 sorted(labs))
    return {r['name'].casefold() for r in rows}


def info(person: Person, lab: str) -> dict:
    """The lab's chair group with its labs; chosen by an administrator on the suite's dashboard."""
    row = _group(lab)
    return {'lab': lab, 'group': {'name': row['name'], 'labs': labs_in(row['id'])} if row else None,
            'dashboard': os.environ.get('SUITE_DASHBOARD_URL', '/account/').rstrip('/') + '/#labs'}
