"""
Sharing stock lists between labs.

A lab's stocks are its own: everyone in the lab sees and changes them, other
labs do not see them. On top of that, two kinds of sharing widen who sees — or
may change — a lab's stocks:

* **A lab shares a list.** Its lead or lab admin shares one list (glycerol
  stocks, primers, chemicals, antibodies or plant material) or *all* of them,
  with another lab, with its own chair group, or with any other chair group
  (every lab in it, as the group stands). The share is read-only, or lets
  the other lab change and delete the records too. Kept in `shares`.

* **A whole chair group shares everything.** An administrator turns on sharing
  for a chair group, so all its labs see each other's stocks; it can also let
  them change each other's. Kept in `chair_sharing`, keyed by the group's id in
  the suite. This is the group-wide switch; it stacks with any per-lab shares,
  so a lab can share everything with its own chair group and, as well, one list
  with a single lab of another group.

The records themselves always belong to the lab that made them: eLab is still
sent by that lab, with its own token, and a record's owner never changes. A
share only widens who may see or change it; every change is logged with who made
it, and a delete is a soft delete, so a shared lab's edits are in the history and
recoverable like any other.

Chair groups are the suite's (app/chairs.py), read from suite.db and never
written; this module only records each group's own opt-in and the per-lab shares,
in the stocks database.
"""

import secrets
from typing import Dict, List, Optional, Set

from werkzeug.exceptions import Forbidden

from app import chairs
from app.db import connect
from app.people import Person

# The stock lists that can be shared; 'all' means every one of them.
KINDS = ('glycerol', 'primer', 'chemical', 'antibody', 'material')
# Whom a share is for: one named 'lab'; the owner's own 'chair' group; or any other chair 'group', by its id.
TARGET_KINDS = ('lab', 'chair', 'group')


# --- resolving: which labs' stocks a person sees or may change -------------------

def _rows(conn) -> List:
    return conn.execute('SELECT * FROM shares').fetchall()


def _chair_rows(conn) -> Dict[str, int]:
    """chair_group_id -> can_edit, for every group that has opted in."""
    return {r['chair_group_id']: r['can_edit'] for r in conn.execute('SELECT * FROM chair_sharing')}


def _targets_person(person: Person, conn) -> Set[str]:
    """
    The targets a person counts as, for matching a share: every casefolded lab
    name they are in ('lab' shares aimed at one of their labs), and the id and
    name of each of their labs' chair groups ('chair' shares, which name the
    owner's group — a member of that group is a target).
    """
    labs = {n.casefold() for n in person.lab_names()}
    targets = set(labs)
    for lab in labs:
        gid = chairs.group_id(lab)
        if gid is not None:
            targets.add(f'chair:{gid}')
    return targets


def _granted(person: Person, conn, want_edit: bool) -> Dict[str, Set[str]]:
    """
    kind -> set of casefolded owner-lab names whose stocks of that kind this
    person may see (want_edit False) or change (want_edit True) through a share.
    'all' shares are expanded to every kind.
    """
    own = {n.casefold() for n in person.lab_names()}
    me = _targets_person(person, conn)
    out: Dict[str, Set[str]] = {k: set() for k in KINDS}
    for row in _rows(conn):
        owner = (row['owner_lab'] or '').casefold()
        if owner in own:
            continue                                   # a lab's share with itself: nothing to add
        if want_edit and not row['can_edit']:
            continue
        if row['target_kind'] == 'lab':
            if (row['target'] or '').casefold() not in me:
                continue
        elif row['target_kind'] == 'chair':
            gid = chairs.group_id(owner)               # the owner's own chair group
            if gid is None or f'chair:{gid}' not in me:
                continue
        elif row['target_kind'] == 'group':
            # Another chair group, named by its id: every lab in it, as the group stands now.
            if f"chair:{row['target']}" not in me:
                continue
        else:
            continue
        for k in (KINDS if row['kind'] == 'all' else (row['kind'],)):
            if k in out:
                out[k].add(owner)
    return out


def _chair_wide(person: Person, conn, want_edit: bool) -> Set[str]:
    """
    Casefolded names of labs a person sees (or may change) because their shared
    chair group has opted in to sharing everything. A person in that group sees
    every lab of it.
    """
    optins = _chair_rows(conn)
    if not optins:
        return set()
    out: Set[str] = set()
    for lab in {n.casefold() for n in person.lab_names()}:
        gid = chairs.group_id(lab)
        if gid is None or str(gid) not in {str(k) for k in optins}:
            continue
        can_edit = next((v for k, v in optins.items() if str(k) == str(gid)), 0)
        if want_edit and not can_edit:
            continue
        out |= {n.casefold() for n in chairs.labs_in(gid)}
    return out


def shared_in(person: Person) -> Dict[str, Set[str]]:
    """
    kind -> casefolded owner-lab names whose stocks of that kind this person may
    **see** through any sharing (per-lab shares or a chair-group opt-in), beyond
    their own labs and the read-only chair-group view in app/chairs.py. The
    '_wide' key holds only the chair-group opt-in labs (sharing every list), so a
    listless order request can be widened by the opt-in but not by a per-list share.
    """
    with connect() as conn:
        out = _granted(person, conn, want_edit=False)
        wide = _chair_wide(person, conn, want_edit=False)
    for k in out:
        out[k] |= wide
    out['_wide'] = wide
    return out


def editable_in(person: Person) -> Dict[str, Set[str]]:
    """Like shared_in, but only where the share lets this person **change** the stocks."""
    with connect() as conn:
        out = _granted(person, conn, want_edit=True)
        wide = _chair_wide(person, conn, want_edit=True)
    for k in out:
        out[k] |= wide
    out['_wide'] = wide
    return out


# --- managing shares -------------------------------------------------------------

def _owner_lab(person: Person, lab: Optional[str]) -> str:
    """
    The lab a share is for. An administrator may name any lab; otherwise it must
    be one of the person's own that they lead or are lab admin of.
    """
    from app.records import lab_of, labs_of
    if person.is_admin:
        chosen = (lab or '').strip() or labs_of(person)[0]
        if not chosen or chosen.startswith('user:'):
            raise ValueError('Name the lab to share')
        return chosen
    own = {n.casefold(): n for n in labs_of(person)}
    chosen = own.get((lab or '').strip().casefold()) if lab else lab_of(person)
    if chosen is None:
        raise Forbidden("That is not one of your labs")
    if not (person.leads(chosen) or person.administers(chosen)):
        raise Forbidden("Only a lab's lead or lab admin shares its stocks")
    return chosen


def list_for(person: Person, lab: Optional[str] = None) -> dict:
    """
    The shares a lab has made, for its lead or lab admin, and whether its chair
    group shares everything. Also the labs it could share with (its chair group's
    other labs, and every other lab), for the form.
    """
    if person.is_admin and not (lab or '').strip():
        from app.records import labs_of
        if labs_of(person)[0].startswith('user:'):
            # An administrator in no lab shares on a lab's behalf: the page asks which.
            return {'needs_lab': True, 'labs': chairs.all_labs()}
    owner = _owner_lab(person, lab)
    group = chairs.info(person, owner)['group']
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(
            'SELECT * FROM shares WHERE owner_lab = ? COLLATE NOCASE ORDER BY kind, target_kind, target', (owner,))]
        gid = chairs.group_id(owner)
        optin = conn.execute('SELECT * FROM chair_sharing WHERE chair_group_id = ?',
                             (str(gid),)).fetchone() if gid is not None else None
    groups = chairs.all_groups()
    names = {g['id']: g['name'] for g in groups}
    for r in rows:
        r['can_edit'] = bool(r['can_edit'])
        if r['target_kind'] == 'group':
            r['target_name'] = names.get(str(r['target']), r['target'])     # a group since removed keeps its id
    others = [l for l in chairs.all_labs() if l.casefold() != owner.casefold()]
    own_gid = str(chairs.group_id(owner)) if chairs.group_id(owner) is not None else None
    return {'lab': owner, 'shares': rows, 'kinds': list(KINDS), 'other_labs': others,
            'other_groups': [g for g in groups if g['id'] != own_gid],
            'group': group,
            'chair_sharing': {'on': optin is not None, 'can_edit': bool(optin['can_edit']) if optin else False}
                             if group else None,
            'can_set_chair': person.is_admin}


def create(person: Person, lab: Optional[str], kind: str, target_kind: str, target: str,
           can_edit: bool) -> dict:
    """Share a lab's list (or all) with another lab, its own chair group, or any other chair group."""
    owner = _owner_lab(person, lab)
    kind = (kind or 'all').strip().lower()
    if kind != 'all' and kind not in KINDS:
        raise ValueError(f'kind must be all or one of {", ".join(KINDS)}')
    target_kind = (target_kind or 'lab').strip().lower()
    if target_kind not in TARGET_KINDS:
        raise ValueError('target_kind must be lab, chair or group')
    target = (target or '').strip()
    if target_kind == 'chair':
        if chairs.group_id(owner) is None:
            raise ValueError('This lab is not in a chair group')
        target = ''
    elif target_kind == 'group':
        # Another chair group, by id (its name is accepted too): every lab in it, now and later.
        found = next((g for g in chairs.all_groups()
                      if g['id'] == target or g['name'].casefold() == target.casefold()), None)
        if found is None:
            raise ValueError('Choose a chair group to share with')
        own_gid = chairs.group_id(owner)
        if own_gid is not None and str(own_gid) == found['id']:
            raise ValueError("That is this lab's own chair group: share with \"your chair group\" instead")
        target = found['id']
    else:
        if not target:
            raise ValueError('Choose a lab to share with')
        if target.casefold() == owner.casefold():
            raise ValueError('A lab already sees its own stocks')
    with connect() as conn:
        share_id = secrets.token_hex(12)
        conn.execute('INSERT INTO shares (id, owner_lab, kind, target_kind, target, can_edit, created_by) '
                     'VALUES (?, ?, ?, ?, ?, ?, ?) '
                     'ON CONFLICT(owner_lab, kind, target_kind, target) DO UPDATE SET '
                     'can_edit = excluded.can_edit, created_by = excluded.created_by, created_at = CURRENT_TIMESTAMP',
                     (share_id, owner, kind, target_kind, target, 1 if can_edit else 0, person.username))
    return list_for(person, owner)


def remove(person: Person, share_id: str, lab: Optional[str] = None) -> dict:
    owner = _owner_lab(person, lab)
    with connect() as conn:
        row = conn.execute('SELECT * FROM shares WHERE id = ?', (share_id,)).fetchone()
        if row is None or (row['owner_lab'] or '').casefold() != owner.casefold():
            from app.records import NotFound
            raise NotFound('No such share')
        conn.execute('DELETE FROM shares WHERE id = ?', (share_id,))
    return list_for(person, owner)


def set_chair(person: Person, lab: Optional[str], on: bool, can_edit: bool) -> dict:
    """Turn a chair group's share-everything on or off. Administrators only."""
    if not person.is_admin:
        raise Forbidden('Only an administrator turns on sharing for a chair group')
    owner = _owner_lab(person, lab)
    gid = chairs.group_id(owner)
    if gid is None:
        raise ValueError('This lab is not in a chair group')
    with connect() as conn:
        if on:
            conn.execute('INSERT INTO chair_sharing (chair_group_id, can_edit, set_by) VALUES (?, ?, ?) '
                         'ON CONFLICT(chair_group_id) DO UPDATE SET can_edit = excluded.can_edit, '
                         'set_by = excluded.set_by, set_at = CURRENT_TIMESTAMP',
                         (str(gid), 1 if can_edit else 0, person.username))
        else:
            conn.execute('DELETE FROM chair_sharing WHERE chair_group_id = ?', (str(gid),))
    return list_for(person, owner)
