"""Lab Stocks: glycerol stocks and primers, their codes, and who sees them."""

import io
import sqlite3

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64


def _ok(r, code=200):
    assert r.status_code == code, (r.status_code, r.get_json())
    return r.get_json()


def test_nothing_without_the_suite_saying_who_you_are(world):
    client = world['app'].test_client()
    assert client.get('/api/glycerol').status_code == 401
    assert client.get('/').status_code == 302
    assert client.get('/health').get_json()['status'] == 'healthy'


def test_a_glycerol_stock_for_a_confirmed_plasmid(as_user):
    ana = as_user('ana')
    made = _ok(ana.post('/api/glycerol', json={
        'plasmid_id': 'p1', 'plasmid_name': 'pGreen-35S-GFP', 'clone': '4', 'host': 'DH5α',
        'selection': 'kanamycin', 'location': 'Freezer -80 / box 2 / A3', 'source': 'sequencing'}), 201)['record']
    # The lab's code as the seed bank has it (GARD), and its own numbering.
    assert made['code'] == 'GARD-G-0001' and made['source'] == 'sequencing'
    assert _ok(ana.post('/api/glycerol', json={'plasmid_id': 'p1', 'plasmid_name': 'pGreen-35S-GFP', 'clone': '7'}), 201)['record']['code'] == 'GARD-G-0002'
    # Found by the plasmid it holds, by code and by name; and the others of the same plasmid.
    assert [g['clone'] for g in _ok(ana.get('/api/glycerol?plasmid=p1'))['glycerol']] == ['7', '4']
    detail = _ok(ana.get('/api/glycerol/gard-g-0001'))['record']
    assert detail['plasmid_name'] == 'pGreen-35S-GFP' and [s['code'] for s in detail['same_plasmid']] == ['GARD-G-0002']
    assert 'created GARD-G-0001 on confirming the plasmid by sequencing' in detail['changes'][0]['what']
    assert ana.post('/api/glycerol', json={'clone': '1'}).status_code == 400, 'it must say which plasmid'
    _ok(ana.put('/api/glycerol/GARD-G-0001', json={'status': 'used up'}))
    assert ana.put('/api/glycerol/GARD-G-0001', json={'status': 'lost'}).status_code == 400


def test_primers_with_their_tm_and_sequence_search(as_user):
    ana = as_user('ana')
    p = _ok(ana.post('/api/primers', json={'name': 'M13 fwd', 'sequence': "5'-gtaaaacgacggccagt-3'",
                                           'direction': 'forward', 'supplier': 'IDT', 'location': 'Primer box 1 / A1'}), 201)['record']
    assert p['code'] == 'GARD-O-0001' and p['sequence'] == 'GTAAAACGACGGCCAGT'
    assert p['length'] == 17 and p['gc'] == 52.9 and 48 < p['tm'] < 56, p['tm']
    assert ana.post('/api/primers', json={'name': 'bad', 'sequence': 'ACGTXQ'}).status_code == 400
    assert ana.post('/api/primers', json={'name': '', 'sequence': 'ACGT'}).status_code == 400
    deg = _ok(ana.post('/api/primers', json={'name': 'degenerate', 'sequence': 'GAYTGGCARAARTTYGG'}), 201)['record']
    assert deg['tm'] is not None
    # By name, and by any piece of the sequence.
    assert [x['code'] for x in _ok(ana.get('/api/primers?q=M13'))['primers']] == ['GARD-O-0001']
    assert [x['code'] for x in _ok(ana.get('/api/primers?q=acg acg gcc'))['primers']] == ['GARD-O-0001']
    # Several at once, as from the editor's primer design.
    many = _ok(ana.post('/api/primers/many', json={'primers': [
        {'name': 'GFP-F', 'sequence': 'ATGGTGAGCAAGGGCGAG', 'direction': 'forward', 'target': 'pGreen-35S-GFP'},
        {'name': 'GFP-R', 'sequence': 'TTACTTGTACAGCTCGTCCATG', 'direction': 'reverse', 'target': 'pGreen-35S-GFP'}]}), 201)['primers']
    assert [m['code'] for m in many] == ['GARD-O-0003', 'GARD-O-0004']
    # The sequences for finding where they bind: in-stock primers only.
    _ok(ana.put('/api/primers/GARD-O-0002', json={'status': 'used up'}))
    assert {x['code'] for x in _ok(ana.get('/api/primers/sequences'))['primers']} == {'GARD-O-0001', 'GARD-O-0003', 'GARD-O-0004'}


def test_tm_calculation():
    from app import oligo
    # Values as published nearest-neighbour calculators give them (50 mM Na+, 250 nM).
    assert abs(oligo.tm('GTAAAACGACGGCCAGT') - 52.5) < 2
    assert abs(oligo.tm('ATGGTGAGCAAGGGCGAGGAG') - 62.5) < 2.5
    assert oligo.tm('ACGT') is None
    assert oligo.gc('GGCC') == 100.0 and oligo.gc('AATT') == 0.0


def test_a_lab_keeps_its_stocks_and_other_labs_do_not_see_them(as_user):
    ana, ben, zoe, boss = as_user('ana'), as_user('ben'), as_user('zoe'), as_user('boss')
    g = _ok(ana.post('/api/glycerol', json={'plasmid_name': 'pX', 'clone': '1'}), 201)['record']
    pr = _ok(ana.post('/api/primers', json={'name': 'P1', 'sequence': 'ACGTACGTACGTACGTAC'}), 201)['record']
    assert _ok(ben.get(f"/api/glycerol/{g['code']}"))['record']['code'] == g['code']
    _ok(ben.put(f"/api/primers/{pr['code']}", json={'location': 'Box 3'}))
    for path in (f"/api/glycerol/{g['code']}", f"/api/primers/{pr['code']}"):
        assert zoe.get(path).status_code == 404
        assert zoe.put(path, json={'notes': 'x'}).status_code == 404
    assert _ok(zoe.get('/api/glycerol'))['glycerol'] == [] and _ok(zoe.get('/api/primers/sequences'))['primers'] == []
    assert _ok(zoe.get('/api/search?q=P1'))['results'] == []
    # Zoe's lab has its own code and numbering; the admin sees both.
    zg = _ok(zoe.post('/api/glycerol', json={'plasmid_name': 'pY'}), 201)['record']
    assert zg['code'] == 'OL-G-0001'
    assert {x['code'] for x in _ok(boss.get('/api/glycerol'))['glycerol']} == {g['code'], zg['code']}


def test_lab_code_follows_the_seed_bank_and_can_be_chosen_before_the_first_stock(as_user):
    lead, zoe = as_user('lead'), as_user('zoe')
    assert _ok(lead.get('/api/lab'))['code'] == 'GARD', 'as the seed bank has it'
    assert _ok(zoe.get('/api/lab'))['code'] == 'OL'
    assert zoe.put('/api/lab', json={'code': 'OTH'}).status_code == 403, 'a member does not choose it'
    assert lead.put('/api/lab', json={'code': 'OL'}).status_code == 400, "another lab's code"
    _ok(as_user('ana').post('/api/primers', json={'name': 'P', 'sequence': 'ACGTACGTACGTACGTAC'}), 201)
    assert lead.put('/api/lab', json={'code': 'GDL'}).status_code == 400, 'fixed once the lab has stocks'


def test_files_mentions_and_search_for_links(as_user, world):
    ana = as_user('ana')
    g = _ok(ana.post('/api/glycerol', json={'plasmid_name': 'pGFP', 'clone': '2'}), 201)['record']
    att = _ok(ana.post(f"/api/glycerol/{g['code']}/attachments", content_type='multipart/form-data',
                       data={'file': [(io.BytesIO(PNG), 'colony.png')]}), 201)['attachments'][0]
    assert ana.get(f"/api/attachments/{att['id']}").headers['Content-Disposition'].startswith('inline')
    assert as_user('zoe').get(f"/api/attachments/{att['id']}").status_code == 404
    conn = sqlite3.connect(world['paths']['notebook'])
    conn.execute("INSERT INTO notes VALUES ('n1', 'Minipreps', 'page', 'ana', '2026-10-15', NULL)")
    conn.execute("INSERT INTO links VALUES ('n1', 'stock', ?)", (g['code'],))
    conn.commit()
    conn.close()
    assert [m['title'] for m in _ok(ana.get(f"/api/glycerol/{g['code']}"))['record']['mentions']] == ['Minipreps']
    assert _ok(as_user('ben').get(f"/api/glycerol/{g['code']}"))['record']['mentions'] == []
    found = _ok(ana.get(f"/api/search?q={g['code']}"))['results']
    assert found[0] == {'kind': 'glycerol', 'code': g['code'], 'label': f"{g['code']} pGFP clone 2"}
    assert ana.delete(f"/api/glycerol/{g['code']}").status_code == 200
    assert ana.get(f"/api/glycerol/{g['code']}").status_code == 404


def test_a_glycerol_stock_is_linked_to_its_plasmid_and_says_when_it_cannot_be_opened(as_user, world):
    import sqlite3
    ana, ben = as_user('ana'), as_user('ben')
    # A stock made with only the plasmid's name: not linked yet.
    made = ana.post('/api/glycerol', json={'plasmid_name': 'pOld from the freezer list', 'clone': '2'}).get_json()['record']
    assert made['plasmid'] == {'state': 'unlinked'}
    # Linked to the editor's plasmid, it takes the name the plasmid has there.
    assert ana.put(f"/api/glycerol/{made['code']}", json={'plasmid_id': 'p1'}).status_code == 200
    rec = ana.get(f"/api/glycerol/{made['code']}").get_json()['record']
    assert (rec['plasmid_id'], rec['plasmid_name']) == ('p1', 'pGreen-35S-GFP')
    assert rec['plasmid'] == {'state': 'open', 'id': 'p1', 'name': 'pGreen-35S-GFP'}
    assert any('plasmid_id' in c['what'] for c in rec['changes']), 'the change is logged'
    # Only to plasmids this person may open, and ones that exist; an empty link changes nothing.
    conn = sqlite3.connect(world['paths']['editor'])
    conn.execute("INSERT INTO users VALUES ('zoe', 'zoe')")
    conn.execute("INSERT INTO sequences (id, name, sequence, shared, owner_id) VALUES ('p3', 'pZoes', 'ACGT', 1, 'zoe')")
    conn.commit()
    assert ana.put(f"/api/glycerol/{made['code']}", json={'plasmid_id': 'p3'}).status_code == 400   # another lab's
    assert ana.put(f"/api/glycerol/{made['code']}", json={'plasmid_id': 'nothing-like-it'}).status_code == 400
    assert ana.put(f"/api/glycerol/{made['code']}", json={'plasmid_id': ''}).status_code == 200
    assert ana.get(f"/api/glycerol/{made['code']}").get_json()['record']['plasmid_id'] == 'p1'
    # A lab mate's plasmid, even one not public: always the lab's to link and open.
    assert ben.put(f"/api/glycerol/{made['code']}", json={'plasmid_id': 'p2'}).status_code == 200
    assert ben.get(f"/api/glycerol/{made['code']}").get_json()['record']['plasmid']['state'] == 'open'
    # Pointing at another lab's plasmid (linked when it was public, say): it says why it will not open.
    sconn = sqlite3.connect(world['paths']['stocks'])
    sconn.execute("UPDATE glycerol SET plasmid_id = 'p3' WHERE code = ?", (made['code'],))
    sconn.commit()
    assert ana.get(f"/api/glycerol/{made['code']}").get_json()['record']['plasmid'] == {'state': 'other_lab', 'owner': 'zoe'}
    sconn.execute("UPDATE glycerol SET plasmid_id = 'p2' WHERE code = ?", (made['code'],))
    sconn.commit()
    # Gone from the editor's library: said so, rather than a link that goes nowhere.
    conn.execute("DELETE FROM sequences WHERE id = 'p2'")
    conn.commit()
    assert ana.get(f"/api/glycerol/{made['code']}").get_json()['record']['plasmid'] == {'state': 'missing'}


def test_someone_in_two_labs_sees_both_and_chooses_where_new_stocks_go(as_user, world):
    import sqlite3
    conn = sqlite3.connect(world['paths']['suite'])
    conn.executescript("""
        CREATE TABLE lab_members (username TEXT, lab_id INTEGER, role TEXT, lab_admin INTEGER DEFAULT 0,
                                  joined_at TEXT, PRIMARY KEY (username, lab_id));
        INSERT INTO lab_members (username, lab_id, role, joined_at) SELECT username, lab_id, role, '1' FROM members;
        INSERT INTO lab_members (username, lab_id, role, joined_at) VALUES ('zoe', 1, 'lab_lead', '9');
    """)
    conn.commit()
    ana, zoe = as_user('ana'), as_user('zoe')
    gardiner = ana.post('/api/glycerol', json={'plasmid_id': 'p1', 'plasmid_name': 'pGreen-35S-GFP'}).get_json()['record']
    assert zoe.get(f"/api/glycerol/{gardiner['code']}").status_code == 200
    mine = zoe.post('/api/primers', json={'name': 'oZ1', 'sequence': 'ACGTACGTACGTACGTAC', 'lab': 'Gardiner Lab'})
    assert mine.status_code == 201 and mine.get_json()['record']['lab'] == 'Gardiner Lab'
    first = zoe.post('/api/primers', json={'name': 'oZ2', 'sequence': 'ACGTACGTACGTACGTAC'}).get_json()['record']
    assert first['lab'] == 'Other Lab'
    assert zoe.post('/api/primers', json={'name': 'x', 'sequence': 'ACGTACGTACGT', 'lab': 'Smith Lab'}).status_code == 400
    assert zoe.get('/api/lab').get_json()['labs'] == ['Other Lab', 'Gardiner Lab']
    assert zoe.put('/api/lab', json={'code': 'OTH', 'lab': 'Other Lab'}).status_code == 403
    # Shared plasmids are seen within the owner's labs: Zoe, now in Gardiner Lab, sees Ana's.
    assert 'p1' in {p['id'] for p in zoe.get('/api/plasmids').get_json()['plasmids']}
    assert 'p1' not in {p['id'] for p in as_user('loner').get('/api/plasmids').get_json()['plasmids']}
