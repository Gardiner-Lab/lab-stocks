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


PDF = b'%PDF-1.4\n' + b'\x00' * 64


def test_a_primers_5_and_3_prime_modifications_go_on_its_order(as_user, world):
    ana = as_user('ana')
    assert '6-FAM' in _ok(ana.get('/api/me'))['mods']['5'] and 'BHQ-1' in _ok(ana.get('/api/me'))['mods']['3']
    p = _ok(ana.post('/api/primers', json={'name': 'probe', 'sequence': 'GTAAAACGACGGCCAGT', 'mod5': '6-FAM', 'mod3': 'BHQ-1',
                                           'modifications': 'internal dT-TAMRA'}), 201)['record']
    assert (p['mod5'], p['mod3'], p['length']) == ('6-FAM', 'BHQ-1', 17)          # not in the sequence or its length
    assert [r['code'] for r in _ok(ana.get('/api/primers?q=BHQ'))['primers']] == [p['code']]
    order = _ok(ana.post('/api/orders', json={'record': p['code']}), 201)['order']
    assert order['details'] == ('5′-[6-FAM]GTAAAACGACGGCCAGT[BHQ-1]-3′ (17 nt); 5′ 6-FAM, 3′ BHQ-1; '
                                'other modifications: internal dT-TAMRA')
    plain = _ok(ana.post('/api/primers', json={'name': 'plain', 'sequence': 'ACGTACGTACGT'}), 201)['record']
    assert _ok(ana.post('/api/orders', json={'record': plain['code']}), 201)['order']['details'] == '5′-ACGTACGTACGT-3′ (12 nt)'
    _ok(ana.put(f"/api/primers/{plain['code']}", json={'mod5': 'Phosphate'}))
    assert _ok(ana.get(f"/api/primers/{plain['code']}"))['record']['mod5'] == 'Phosphate'


def test_chemicals_with_their_cas_number_and_safety_data_sheet(as_user):
    ana, ben, zoe = as_user('ana'), as_user('ben'), as_user('zoe')
    made = _ok(ana.post('/api/chemicals', json={'name': 'Ethanol absolute', 'cas': ' 64-17-5 ', 'room': 'O.703',
                                                 'size': '2.5 L'}), 201)['record']
    assert made['code'] == 'GARD-C-0001' and made['cas'] == '64-17-5' and made['sds'] is None
    # CAS numbers are checked, check digit too; one may be left out.
    assert 'check digit' in ana.post('/api/chemicals', json={'name': 'Typo', 'cas': '64-17-6'}).get_json()['error']
    assert ana.post('/api/chemicals', json={'name': 'Odd', 'cas': '6417-5'}).status_code == 400
    assert ana.post('/api/chemicals', json={'cas': '7732-18-5'}).status_code == 400, 'it needs a name'
    _ok(ana.post('/api/chemicals', json={'name': 'agarose'}), 201)
    # Listed by name; found by CAS number or room; the lab's, not another lab's.
    assert [c['name'] for c in _ok(ben.get('/api/chemicals'))['chemicals']] == ['agarose', 'Ethanol absolute']
    assert [c['code'] for c in _ok(ben.get('/api/chemicals?q=64-17'))['chemicals']] == ['GARD-C-0001']
    assert _ok(zoe.get('/api/chemicals'))['chemicals'] == []
    assert zoe.get('/api/chemicals/GARD-C-0001').status_code == 404
    # Its safety data sheet: a PDF captioned SDS, shown apart from its other files and marked in the list.
    _ok(ana.post('/api/chemicals/GARD-C-0001/attachments', content_type='multipart/form-data',
                 data={'file': [(io.BytesIO(PNG), 'bottle.png')]}), 201)
    _ok(ben.post('/api/chemicals/GARD-C-0001/attachments', content_type='multipart/form-data',
                 data={'file': [(io.BytesIO(PDF), 'ethanol-sds.pdf')], 'caption': 'SDS'}), 201)
    rec = _ok(ana.get('/api/chemicals/GARD-C-0001'))['record']
    assert rec['sds']['filename'] == 'ethanol-sds.pdf' and rec['sds']['preview']
    assert {c['code']: c['has_sds'] for c in _ok(ana.get('/api/chemicals'))['chemicals']} == {'GARD-C-0001': 1, 'GARD-C-0002': 0}
    assert zoe.get(f"/api/attachments/{rec['sds']['id']}").status_code == 404
    # Edited, logged; a code like any other stock's.
    _ok(ana.put('/api/chemicals/GARD-C-0001', json={'room': 'O.705', 'status': 'out'}))
    assert ana.put('/api/chemicals/GARD-C-0001', json={'status': 'used up'}).status_code == 400, 'a chemical is out'
    assert 'out' in _ok(ana.get('/api/me'))['chemical_status']
    assert "room: 'O.703' → 'O.705'" in _ok(ana.get('/api/chemicals/GARD-C-0001'))['record']['changes'][0]['what']
    assert ana.put('/api/chemicals/GARD-C-0001', json={'cas': '1-2-3'}).status_code == 400
    from app import records
    assert records.kind_of('gard-c-0001') == 'chemical'
    # Offered to the notebook's links.
    assert _ok(ana.get('/api/search?q=Ethanol'))['results'] == [
        {'kind': 'chemical', 'code': 'GARD-C-0001', 'label': 'GARD-C-0001 Ethanol absolute (CAS 64-17-5)'}]


def test_the_page_links_to_the_safety_registers(as_user):
    page = as_user('ana').get('/').get_data(as_text=True)
    assert 'uusofos.itis.software' in page and 'chemwatch' in page and 'data-view="chemicals"' in page and 'data-view="antibodies"' in page


def test_antibodies(as_user):
    ana, ben, zoe = as_user('ana'), as_user('ben'), as_user('zoe')
    made = _ok(ana.post('/api/antibodies', json={
        'short_code': 'aGFP-m', 'description': 'Anti-GFP, monoclonal (B-2)', 'type': 'Primary', 'producer': 'Santa Cruz',
        'host': 'mouse', 'product_number': 'sc-9996', 'notes': '1:1000 in 5% milk for westerns'}), 201)['record']
    assert made['code'] == 'GARD-A-0001' and made['type'] == 'primary'
    _ok(ana.post('/api/antibodies', json={'short_code': 'aMs-HRP', 'type': 'secondary', 'host': 'goat'}), 201)
    assert ana.post('/api/antibodies', json={'type': 'secondary'}).status_code == 400, 'it needs a short code or description'
    assert ana.post('/api/antibodies', json={'short_code': 'x', 'type': 'tertiary'}).status_code == 400
    assert 'other' in _ok(ana.get('/api/me'))['antibody_types']
    # The lab's, found by any of its fields; not another lab's.
    assert [a['short_code'] for a in _ok(ben.get('/api/antibodies'))['antibodies']] == ['aGFP-m', 'aMs-HRP']
    assert [a['code'] for a in _ok(ben.get('/api/antibodies?q=sc-9996'))['antibodies']] == ['GARD-A-0001']
    assert [a['code'] for a in _ok(ben.get('/api/antibodies?q=goat'))['antibodies']] == ['GARD-A-0002']
    assert _ok(zoe.get('/api/antibodies'))['antibodies'] == []
    assert zoe.get('/api/antibodies/GARD-A-0001').status_code == 404
    _ok(ben.put('/api/antibodies/GARD-A-0001', json={'notes': '1:2000', 'status': 'used up'}))
    rec = _ok(ana.get('/api/antibodies/GARD-A-0001'))['record']
    assert rec['notes'] == '1:2000' and "status: 'in stock' → 'used up'" in rec['changes'][0]['what']
    from app import records
    assert records.kind_of('gard-a-0002') == 'antibody'
    # Linked from the notebook.
    assert _ok(ana.get('/api/search?q=aMs'))['results'] == [
        {'kind': 'antibody', 'code': 'GARD-A-0002', 'label': 'GARD-A-0002 aMs-HRP (secondary, goat)'}]


def test_label_codes_open_the_public_address_set_on_the_dashboard(world, monkeypatch):
    from app import people
    monkeypatch.setenv('SUITE_PUBLIC_URL', 'https://old.example.org/')
    assert people.public_url() == 'https://old.example.org'
    conn = sqlite3.connect(world['paths']['suite'])
    conn.execute('CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)')
    conn.execute("INSERT INTO settings VALUES ('hosting.public_url', 'https://lab.example.org')")
    conn.commit()
    conn.close()
    assert people.public_url() == 'https://lab.example.org'


def test_someone_who_left_is_not_offered_any_more(world):
    from app import people
    assert 'ben' in people.people()
    conn = sqlite3.connect(world['paths']['suite'])
    conn.execute('CREATE TABLE archived (username TEXT PRIMARY KEY, archived_at TEXT, archived_by TEXT)')
    conn.execute("INSERT INTO archived VALUES ('ben', '2026-10-23T10:00:00Z', 'lead')")
    conn.commit()
    conn.close()
    assert 'ben' not in people.people() and people.archived() == {'ben': '2026-10-23T10:00:00Z'}


def test_office_and_text_files_open_in_the_browser(as_user, monkeypatch):
    import http.server
    import threading
    calls = []

    class Converter(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            calls.append((self.path, b'filename="plan.docx"' in body))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'%PDF-1.4 the plan')

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(('127.0.0.1', 0), Converter)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    ana = as_user('ana')
    g = _ok(ana.post('/api/glycerol', json={'plasmid_name': 'pGFP', 'clone': '2'}), 201)['record']
    docx = b'PK\x03\x04' + b'\x00' * 40
    word, fasta = _ok(ana.post(f"/api/glycerol/{g['code']}/attachments", content_type='multipart/form-data',
                               data={'file': [(io.BytesIO(docx), 'plan.docx'), (io.BytesIO(b'>p1\nACGT\n'), 'p1.fa')]}),
                      201)['attachments']
    # Without the suite's converter an office file only downloads.
    assert word['view'] is False and fasta['view'] is True
    assert ana.get(f"/api/attachments/{word['id']}?view").headers['Content-Disposition'].startswith('attachment')
    shown = ana.get(f"/api/attachments/{fasta['id']}?view")
    assert shown.mimetype == 'text/plain' and shown.headers['Content-Disposition'].startswith('inline')
    assert 'sandbox' in shown.headers['Content-Security-Policy']
    monkeypatch.setenv('CONVERTER_URL', f'http://127.0.0.1:{server.server_port}')
    assert _ok(ana.get(f"/api/glycerol/{g['code']}"))['record']['attachments'][0]['view'] is True
    for _ in range(2):
        pdf = ana.get(f"/api/attachments/{word['id']}?view")
        assert pdf.mimetype == 'application/pdf' and pdf.data == b'%PDF-1.4 the plan'
        assert pdf.headers['Content-Disposition'] == "inline; filename*=UTF-8''plan.docx.pdf"
    assert calls == [('/forms/libreoffice/convert', True)], 'converted once, then kept'
    # The original still downloads, and others' files stay hidden.
    assert ana.get(f"/api/attachments/{word['id']}?download").data == docx
    assert as_user('zoe').get(f"/api/attachments/{word['id']}?view").status_code == 404
    server.shutdown()
    # A converter that is down: a message, and the download still works.
    monkeypatch.setenv('CONVERTER_URL', 'http://127.0.0.1:9')
    other = _ok(ana.post(f"/api/glycerol/{g['code']}/attachments", content_type='multipart/form-data',
                         data={'file': [(io.BytesIO(docx + b'x'), 'other.xls')]}), 201)['attachments'][0]
    failed = ana.get(f"/api/attachments/{other['id']}?view")
    assert failed.status_code == 502 and b'Download it' in failed.data
