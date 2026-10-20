"""Chair groups: labs that see each other's stocks, chosen by an administrator on the suite's dashboard."""

import sqlite3

from test_elab import FakeElab, _run  # noqa: F401
from test_orders import _lab_admins


def _chair_groups(world, **assigned):
    """The suite's chair groups (as its dashboard keeps them): {lab id: chair group name or None}."""
    conn = sqlite3.connect(world['paths']['suite'])
    conn.execute('CREATE TABLE IF NOT EXISTS chair_groups (id TEXT PRIMARY KEY, name TEXT UNIQUE)')
    if 'chair_group_id' not in {r[1] for r in conn.execute('PRAGMA table_info(labs)')}:
        conn.execute('ALTER TABLE labs ADD COLUMN chair_group_id TEXT')
    for lab_id, name in assigned.items():
        if name:
            conn.execute('INSERT OR IGNORE INTO chair_groups VALUES (?, ?)', (name.lower(), name))
        conn.execute('UPDATE labs SET chair_group_id = ? WHERE id = ?', (name.lower() if name else None, int(lab_id[1:])))
    conn.commit()
    conn.close()


def _ok(r, code=200):
    assert r.status_code == code, (r.status_code, r.get_json())
    return r.get_json()


def test_labs_of_a_chair_group_see_each_others_stocks_but_change_only_their_own(as_user, world):
    _lab_admins(world, 'lead')
    ana, lead, zoe, loner = (as_user(u) for u in ('ana', 'lead', 'zoe', 'loner'))
    ours = _ok(ana.post('/api/chemicals', json={'name': 'Ethanol'}), 201)['record']
    theirs = _ok(zoe.post('/api/chemicals', json={'name': 'Acetone'}), 201)['record']
    _ok(zoe.post('/api/primers', json={'name': 'Theirs fwd', 'sequence': 'ACGTACGTACGTACGT'}), 201)
    assert [c['code'] for c in _ok(ana.get('/api/chemicals'))['chemicals']] == [ours['code']]

    # No chair groups in the suite (one from before them): each lab its own.
    assert _ok(ana.get('/api/chair'))['group'] is None
    # Chosen by an administrator on the suite's dashboard: Gardiner Lab (1) and Other Lab (2) together.
    _chair_groups(world, l1='Plant Biology')
    assert _ok(ana.get('/api/chair'))['group'] == {'name': 'Plant Biology', 'labs': ['Gardiner Lab']}
    assert theirs['code'] not in {c['code'] for c in _ok(ana.get('/api/chemicals'))['chemicals']}
    _chair_groups(world, l2='Plant Biology')
    assert _ok(ana.get('/api/chair'))['group']['labs'] == ['Gardiner Lab', 'Other Lab']
    # Here it is only seen, not chosen.
    assert lead.put('/api/chair', json={'name': 'Mine'}).status_code == 405

    # Both see both; each marked whose it is.
    seen = {c['code']: c for c in _ok(ana.get('/api/chemicals'))['chemicals']}
    assert set(seen) == {ours['code'], theirs['code']}
    assert seen[ours['code']]['mine'] and not seen[theirs['code']]['mine'] and seen[theirs['code']]['lab'] == 'Other Lab'
    assert not _ok(ana.get(f"/api/chemicals/{theirs['code']}"))['record']['mine']
    assert ours['code'] in {c['code'] for c in _ok(zoe.get('/api/chemicals'))['chemicals']}
    assert theirs['code'] in {r['code'] for r in _ok(ana.get('/api/search?q=Acetone'))['results']}
    # Not outside it.
    assert loner.get(f"/api/chemicals/{theirs['code']}").status_code == 404

    # Seeing is not changing: no edits, files, deletions or orders on another lab's stock.
    assert ana.put(f"/api/chemicals/{theirs['code']}", json={'room': 'x'}).status_code == 403
    assert ana.delete(f"/api/chemicals/{theirs['code']}").status_code == 403
    assert ana.post(f"/api/chemicals/{theirs['code']}/attachments", data={'file': (__import__('io').BytesIO(b'x'), 'a.txt')},
                    content_type='multipart/form-data').status_code == 403
    assert ana.post('/api/orders', json={'record': theirs['code']}).status_code == 403
    # The editor binds only the lab's own primers.
    assert _ok(ana.get('/api/primers/sequences'))['primers'] == []

    # Out of it again (on the dashboard): no longer seen.
    _chair_groups(world, l2=None)
    assert ana.get(f"/api/chemicals/{theirs['code']}").status_code == 404


def test_a_chair_group_changing_rewrites_nothing_in_elab(as_user, world, monkeypatch):
    monkeypatch.setenv('ELAB_URL', 'https://uu.elabjournal.com')
    monkeypatch.setenv('ELAB_TOKEN', 'secret')
    _lab_admins(world, 'lead')
    fake = FakeElab()
    g = _ok(as_user('ana').post('/api/glycerol', json={'plasmid_name': 'pX'}), 201)['record']
    assert _run(fake)['sent'] == 1
    assert 'Lab:' not in fake.live('Glycerol Stock')[g['code']]['meta']['Remarks']
    # Put in a chair group on the dashboard: eLab's samples (some perhaps others') are left alone.
    _chair_groups(world, l1='Plant Biology')
    fake.calls.clear()
    assert _run(fake) == {'sent': 0, 'failed': 0}
    assert all(m == 'GET' for m, _ in fake.calls)
