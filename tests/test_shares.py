"""
Sharing stock lists between labs: a lab shares a list (or all) with another lab
or its chair group, to see or to change; a whole chair group shares everything.
"""

import io

from test_chairs import _chair_groups
from test_orders import _lab_admins


def _ok(r, code=200):
    assert r.status_code == code, (r.status_code, r.get_json())
    return r.get_json()


def _codes(payload, key):
    return {r['code'] for r in payload[key]}


def test_a_lab_shares_one_list_with_another_lab_to_see_only(as_user, world):
    """Gardiner Lab shares its chemicals with Other Lab: seen there, not changed; primers stay private."""
    _lab_admins(world, 'lead', 'olga')
    lead, ana, zoe, olga, loner = (as_user(u) for u in ('lead', 'ana', 'zoe', 'olga', 'loner'))

    chem = _ok(ana.post('/api/chemicals', json={'name': 'Ethanol'}), 201)['record']
    primer = _ok(ana.post('/api/primers', json={'name': 'M13', 'sequence': 'GTAAAACGACGGCCAGT'}), 201)['record']

    # Before sharing: Other Lab sees neither.
    assert chem['code'] not in _codes(_ok(zoe.get('/api/chemicals')), 'chemicals')
    assert zoe.get(f"/api/chemicals/{chem['code']}").status_code == 404

    # The lead of Gardiner Lab shares its chemicals with Other Lab, to see.
    out = _ok(lead.post('/api/shares', json={'kind': 'chemical', 'target_kind': 'lab',
                                             'target': 'Other Lab', 'can_edit': False}))
    assert len(out['shares']) == 1 and out['shares'][0]['kind'] == 'chemical' and not out['shares'][0]['can_edit']

    # Now Other Lab sees the chemical, tagged as Gardiner Lab's and read-only.
    seen = {c['code']: c for c in _ok(zoe.get('/api/chemicals'))['chemicals']}
    assert chem['code'] in seen
    assert not seen[chem['code']]['mine'] and seen[chem['code']]['owner_lab'] == 'Gardiner Lab'
    assert not _ok(zoe.get(f"/api/chemicals/{chem['code']}"))['record']['mine']

    # Only chemicals: the primer is not shared.
    assert primer['code'] not in _codes(_ok(zoe.get('/api/primers')), 'primers')
    assert zoe.get(f"/api/primers/{primer['code']}").status_code == 404

    # Seeing is not changing, even on a shared-to-see list.
    assert zoe.put(f"/api/chemicals/{chem['code']}", json={'room': 'x'}).status_code == 403
    assert zoe.delete(f"/api/chemicals/{chem['code']}").status_code == 403

    # Someone outside both labs still sees nothing.
    assert loner.get(f"/api/chemicals/{chem['code']}").status_code == 404


def test_an_editable_share_lets_the_other_lab_change_and_delete_with_history(as_user, world):
    """An editable share: Other Lab edits and deletes Gardiner Lab's chemical; the history keeps who did it."""
    _lab_admins(world, 'lead', 'olga')
    lead, ana, zoe = (as_user(u) for u in ('lead', 'ana', 'zoe'))
    chem = _ok(ana.post('/api/chemicals', json={'name': 'Acetone'}), 201)['record']

    _ok(lead.post('/api/shares', json={'kind': 'chemical', 'target_kind': 'lab',
                                       'target': 'Other Lab', 'can_edit': True}))

    seen = {c['code']: c for c in _ok(zoe.get('/api/chemicals'))['chemicals']}
    assert seen[chem['code']]['mine']                       # editable: shown as changeable

    # Zoe (Other Lab) edits it.
    _ok(zoe.put(f"/api/chemicals/{chem['code']}", json={'room': 'Cold room'}))
    detail = _ok(ana.get(f"/api/chemicals/{chem['code']}"))['record']
    assert detail['room'] == 'Cold room' and detail['lab'] == 'Gardiner Lab'   # owner lab unchanged
    # The change is in the history, credited to zoe.
    assert any(c['changed_by'] == 'zoe' and 'room' in c['what'] for c in detail['changes'])

    # Zoe deletes it: a soft delete, so it is recoverable, and the deletion is logged.
    _ok(zoe.delete(f"/api/chemicals/{chem['code']}"))
    assert ana.get(f"/api/chemicals/{chem['code']}").status_code == 404


def test_a_lab_shares_everything_with_a_single_lab(as_user, world):
    """kind 'all' shares every list with one lab."""
    _lab_admins(world, 'lead', 'olga')
    lead, ana, zoe = (as_user(u) for u in ('lead', 'ana', 'zoe'))
    chem = _ok(ana.post('/api/chemicals', json={'name': 'Ethanol'}), 201)['record']
    ab = _ok(ana.post('/api/antibodies', json={'short_code': 'aGFP', 'description': 'Anti-GFP'}), 201)['record']

    _ok(lead.post('/api/shares', json={'kind': 'all', 'target_kind': 'lab', 'target': 'Other Lab'}))
    assert chem['code'] in _codes(_ok(zoe.get('/api/chemicals')), 'chemicals')
    assert ab['code'] in _codes(_ok(zoe.get('/api/antibodies')), 'antibodies')


def test_only_a_leader_or_lab_admin_shares_a_labs_stocks(as_user, world):
    """A plain member cannot share; the lab's lead or lab admin can; and only for their own lab."""
    _lab_admins(world, 'lead', 'olga')
    ana, lead = (as_user(u) for u in ('ana', 'lead'))
    # Ana is a plain member of Gardiner Lab.
    assert ana.post('/api/shares', json={'kind': 'chemical', 'target': 'Other Lab'}).status_code == 403
    assert ana.get('/api/shares').status_code == 403
    # The lead can, and cannot share a lab that is not theirs.
    _ok(lead.post('/api/shares', json={'kind': 'chemical', 'target': 'Other Lab'}))
    assert lead.post('/api/shares', json={'lab': 'Other Lab', 'kind': 'chemical',
                                          'target': 'Gardiner Lab'}).status_code == 403
    # A lab cannot share with itself, and a share needs a real list.
    assert lead.post('/api/shares', json={'kind': 'chemical', 'target': 'Gardiner Lab'}).status_code == 400
    assert lead.post('/api/shares', json={'kind': 'nonsense', 'target': 'Other Lab'}).status_code == 400


def test_a_share_can_be_removed(as_user, world):
    _lab_admins(world, 'lead', 'olga')
    lead, ana, zoe = (as_user(u) for u in ('lead', 'ana', 'zoe'))
    chem = _ok(ana.post('/api/chemicals', json={'name': 'Ethanol'}), 201)['record']
    out = _ok(lead.post('/api/shares', json={'kind': 'chemical', 'target': 'Other Lab'}))
    share_id = out['shares'][0]['id']
    assert chem['code'] in _codes(_ok(zoe.get('/api/chemicals')), 'chemicals')

    _ok(lead.delete(f'/api/shares/{share_id}'))
    assert chem['code'] not in _codes(_ok(zoe.get('/api/chemicals')), 'chemicals')
    assert zoe.get(f"/api/chemicals/{chem['code']}").status_code == 404


def test_a_lab_shares_a_list_with_its_whole_chair_group(as_user, world):
    """target_kind 'chair' shares with every other lab of the owner's chair group."""
    _lab_admins(world, 'lead', 'olga')
    _chair_groups(world, l1='Plant Biology', l2='Plant Biology')
    lead, ana, zoe = (as_user(u) for u in ('lead', 'ana', 'zoe'))
    primer = _ok(ana.post('/api/primers', json={'name': 'M13', 'sequence': 'GTAAAACGACGGCCAGT'}), 201)['record']

    # The chair group already sees each other's stocks read-only; here we share primers to EDIT.
    _ok(lead.post('/api/shares', json={'kind': 'primer', 'target_kind': 'chair', 'can_edit': True}))
    seen = {p['code']: p for p in _ok(zoe.get('/api/primers'))['primers']}
    assert primer['code'] in seen and seen[primer['code']]['mine']       # now editable by the group
    _ok(zoe.put(f"/api/primers/{primer['code']}", json={'location': 'Box 2'}))


def test_a_whole_chair_group_can_share_everything_admins_only(as_user, world):
    """An administrator turns on share-everything for a chair group: its labs may change each other's stocks."""
    _lab_admins(world, 'lead', 'olga')
    _chair_groups(world, l1='Plant Biology', l2='Plant Biology')
    boss, lead, ana, zoe = (as_user(u) for u in ('boss', 'lead', 'ana', 'zoe'))
    chem = _ok(ana.post('/api/chemicals', json={'name': 'Ethanol'}), 201)['record']

    # A lab lead cannot turn it on for the group.
    assert lead.put('/api/shares/chair', json={'on': True, 'can_edit': True}).status_code == 403

    # The administrator can, editable. Now Other Lab may change Gardiner Lab's chemical.
    _ok(boss.put('/api/shares/chair', json={'lab': 'Gardiner Lab', 'on': True, 'can_edit': True}))
    seen = {c['code']: c for c in _ok(zoe.get('/api/chemicals'))['chemicals']}
    assert seen[chem['code']]['mine']
    _ok(zoe.put(f"/api/chemicals/{chem['code']}", json={'room': 'Shared store'}))

    # Turned off again: back to the read-only chair-group view.
    _ok(boss.put('/api/shares/chair', json={'lab': 'Gardiner Lab', 'on': False}))
    seen = {c['code']: c for c in _ok(zoe.get('/api/chemicals'))['chemicals']}
    assert chem['code'] in seen and not seen[chem['code']]['mine']       # still seen (chair group), not changed
    assert zoe.put(f"/api/chemicals/{chem['code']}", json={'room': 'x'}).status_code == 403


def test_chair_wide_and_single_lab_shares_stack(as_user, world):
    """
    Gardiner Lab's chair group shares everything; and Gardiner Lab shares one list with a single lab of a
    DIFFERENT chair group. The far lab sees only that list; the group sees all.
    """
    _lab_admins(world, 'lead', 'olga')
    # Three labs: 1 and 2 in one chair group, and add a third lab in another.
    import sqlite3
    conn = sqlite3.connect(world['paths']['suite'])
    conn.execute("INSERT INTO labs VALUES (3, 'Far Lab')")
    conn.execute("INSERT INTO lab_members (username, lab_id, role, lab_admin, joined_at) VALUES ('fay', 3, 'lab_lead', 1, '1')")
    conn.commit(); conn.close()
    _chair_groups(world, l1='Plant Biology', l2='Plant Biology', l3='Microbiology')

    lead, ana, zoe, fay = (as_user(u) for u in ('lead', 'ana', 'zoe', 'fay'))
    chem = _ok(ana.post('/api/chemicals', json={'name': 'Ethanol'}), 201)['record']
    primer = _ok(ana.post('/api/primers', json={'name': 'M13', 'sequence': 'GTAAAACGACGGCCAGT'}), 201)['record']

    # Share everything within Gardiner's own chair group (editable), and only chemicals with Far Lab.
    _ok(lead.post('/api/shares', json={'kind': 'all', 'target_kind': 'chair', 'can_edit': True}))
    _ok(lead.post('/api/shares', json={'kind': 'chemical', 'target_kind': 'lab', 'target': 'Far Lab'}))

    # Other Lab (same group) sees and may change both lists.
    assert primer['code'] in _codes(_ok(zoe.get('/api/primers')), 'primers')
    assert {c['code']: c for c in _ok(zoe.get('/api/chemicals'))['chemicals']}[chem['code']]['mine']

    # Far Lab (other group) sees only the chemical, read-only, and not the primer.
    far_chem = {c['code']: c for c in _ok(fay.get('/api/chemicals'))['chemicals']}
    assert chem['code'] in far_chem and not far_chem[chem['code']]['mine']
    assert primer['code'] not in _codes(_ok(fay.get('/api/primers')), 'primers')
    assert fay.put(f"/api/chemicals/{chem['code']}", json={'room': 'x'}).status_code == 403


def test_the_list_tells_a_shared_stock_from_a_chair_groups(as_user, world):
    """
    The page always shows a stock shared with you, but a chair group's other stocks only when asked for: the
    list marks which is which with `shared`, and names the owning lab in `owner_lab`.
    """
    _lab_admins(world, 'lead', 'olga')
    _chair_groups(world, l1='Plant Biology', l2='Plant Biology')
    lead, ana, zoe = (as_user(u) for u in ('lead', 'ana', 'zoe'))
    ethanol = _ok(ana.post('/api/chemicals', json={'name': 'Ethanol'}), 201)['record']
    primer = _ok(ana.post('/api/primers', json={'name': 'M13', 'sequence': 'GTAAAACGACGGCCAGT'}), 201)['record']
    _ok(lead.post('/api/shares', json={'kind': 'chemical', 'target_kind': 'chair'}))

    # Zoe is in the same chair group: the chemical is shared (always shown), the primer only chair-seen.
    chems = {c['code']: c for c in _ok(zoe.get('/api/chemicals'))['chemicals']}
    prims = {p['code']: p for p in _ok(zoe.get('/api/primers'))['primers']}
    assert chems[ethanol['code']]['shared'] and chems[ethanol['code']]['owner_lab'] == 'Gardiner Lab'
    assert not prims[primer['code']]['shared'] and prims[primer['code']]['owner_lab'] == 'Gardiner Lab'
    # Your own stocks are never marked shared.
    mine = _ok(ana.get('/api/chemicals'))['chemicals'][0]
    assert not mine['shared'] and mine['mine']


def test_the_share_form_lists_the_other_labs_to_share_with(as_user, world):
    _lab_admins(world, 'lead', 'olga')
    out = _ok(as_user('lead').get('/api/shares'))
    assert out['lab'] == 'Gardiner Lab' and 'Other Lab' in out['other_labs'] and 'Gardiner Lab' not in out['other_labs']
    assert out['kinds'] == ['glycerol', 'primer', 'chemical', 'antibody', 'material']
    assert out['can_set_chair'] is False
    assert _ok(as_user('boss').get('/api/shares?lab=Gardiner%20Lab'))['can_set_chair'] is True
