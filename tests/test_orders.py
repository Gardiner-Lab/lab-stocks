"""The order list: requests from anyone in a lab, handled by its lab admin."""

import sqlite3


def _ok(r, code=200):
    assert r.status_code == code, (r.status_code, r.get_json())
    return r.get_json()


def _lab_admins(world, *admins):
    """The suite of 2.7.0 on: lab_members, with these people lab admins of their lab, and olga of Other Lab."""
    conn = sqlite3.connect(world['paths']['suite'])
    conn.executescript("""
        CREATE TABLE lab_members (username TEXT, lab_id INTEGER, role TEXT, lab_admin INTEGER DEFAULT 0,
                                  joined_at TEXT, PRIMARY KEY (username, lab_id));
        INSERT INTO lab_members (username, lab_id, role, joined_at) SELECT username, lab_id, role, '1' FROM members;
        INSERT INTO lab_members (username, lab_id, role, lab_admin, joined_at) VALUES ('olga', 2, 'lab_lead', 1, '1');
    """)
    conn.executemany("UPDATE lab_members SET role = 'lab_lead', lab_admin = 1 WHERE username = ?", [(a,) for a in admins])
    conn.commit()
    conn.close()


def test_order_requests_reach_their_labs_lab_admin(as_user, world):
    _lab_admins(world, 'lead')
    ana, ben, lead, zoe, olga, boss = (as_user(u) for u in ('ana', 'ben', 'lead', 'zoe', 'olga', 'boss'))
    assert _ok(lead.get('/api/me'))['orders']['handles'] == ['Gardiner Lab']
    assert _ok(ana.get('/api/me'))['orders']['handles'] == []
    # Anything, with the order request form.
    taq = _ok(ana.post('/api/orders', json={'item': 'Phusion polymerase', 'category': 'enzyme', 'quantity': '2 × 100 U',
                                            'supplier': 'NEB', 'product_number': 'M0530S', 'urgent': True,
                                            'link': 'https://www.neb.com/M0530'}), 201)['order']
    assert taq['lab'] == 'Gardiner Lab' and taq['status'] == 'requested' and taq['urgent'] and not taq['can_handle']
    assert ana.post('/api/orders', json={'item': ''}).status_code == 400
    assert ana.post('/api/orders', json={'item': 'x', 'category': 'pony'}).status_code == 400
    assert ana.post('/api/orders', json={'item': 'x', 'link': 'javascript:alert(1)'}).status_code == 400
    _ok(zoe.post('/api/orders', json={'item': 'Tips', 'category': 'consumable'}), 201)
    # From a stock's page: its details come along, and once is enough.
    _ok(ben.post('/api/primers', json={'name': 'M13 fwd', 'sequence': 'GTAAAACGACGGCCAGT', 'supplier': 'IDT'}), 201)
    _ok(ben.post('/api/antibodies', json={'short_code': 'aGFP', 'description': 'Anti-GFP', 'producer': 'Merck',
                                          'product_number': '11814460001', 'host': 'mouse'}), 201)
    primer = _ok(ben.post('/api/orders', json={'record': 'gard-o-0001', 'quantity': '25 nmol'}), 201)['order']
    assert (primer['item'], primer['supplier'], primer['quantity'], primer['category']) == ('M13 fwd', 'IDT', '25 nmol', 'primer')
    assert 'GTAAAACGACGGCCAGT' in primer['details']
    ab = _ok(ben.post('/api/orders', json={'record': 'GARD-A-0001'}), 201)['order']
    assert (ab['item'], ab['supplier'], ab['product_number']) == ('Anti-GFP', 'Merck', '11814460001')
    again = _ok(ana.post('/api/orders', json={'record': 'GARD-A-0001'}))
    assert again['already'] and again['order']['id'] == ab['id']
    assert _ok(ana.get('/api/antibodies/GARD-A-0001'))['record']['order']['status'] == 'requested'
    assert zoe.post('/api/orders', json={'record': 'GARD-A-0001'}).status_code == 404, "another lab's stock"
    _ok(ben.post('/api/glycerol', json={'plasmid_id': 'p1', 'plasmid_name': 'pGreen'}), 201)
    assert ben.post('/api/orders', json={'record': 'GARD-G-0001'}).status_code == 400, 'glycerol stocks are made'
    # Everyone in the lab sees the lab's orders, and no other lab's (in no chair group with it).
    assert {o['item'] for o in _ok(lead.get('/api/orders'))['orders']} == {'Phusion polymerase', 'M13 fwd', 'Anti-GFP'}
    assert _ok(lead.get('/api/orders'))['waiting'] == 3
    assert {o['item'] for o in _ok(ana.get('/api/orders'))['orders']} == {'Phusion polymerase', 'M13 fwd', 'Anti-GFP'}
    assert _ok(ana.get('/api/orders'))['waiting'] == 0                 # the number is for those who order
    assert [o['item'] for o in _ok(olga.get('/api/orders'))['orders']] == ['Tips']
    assert lead.get(f"/api/orders/{_ok(zoe.get('/api/orders'))['orders'][0]['id']}").status_code == 404
    assert len(_ok(boss.get('/api/orders'))['orders']) == 4
    # Only the lab admin orders; the one who asked may change or cancel it until then.
    assert ana.put(f"/api/orders/{taq['id']}", json={'status': 'ordered'}).status_code == 403
    _ok(ana.put(f"/api/orders/{taq['id']}", json={'quantity': '1 × 100 U'}))
    assert ben.put(f"/api/orders/{taq['id']}", json={'quantity': '9'}).status_code == 403, "not ben's request"
    done = _ok(lead.put(f"/api/orders/{taq['id']}", json={'status': 'ordered'}))['order']
    assert done['ordered_by'] == 'lead' and done['ordered_at']
    assert ana.put(f"/api/orders/{taq['id']}", json={'quantity': '5'}).status_code == 403
    assert ana.put(f"/api/orders/{taq['id']}", json={'status': 'cancelled'}).status_code == 403
    _ok(ben.put(f"/api/orders/{primer['id']}", json={'status': 'cancelled'}))
    assert _ok(lead.get('/api/orders/waiting'))['waiting'] == 1
    assert [o['item'] for o in _ok(lead.get('/api/orders?status=open'))['orders']] == ['Phusion polymerase', 'Anti-GFP']
    # A spreadsheet of them, for the supplier's form.
    sheet = lead.get('/api/orders.csv?status=open').get_data(as_text=True)
    assert 'M0530S' in sheet and 'Tips' not in sheet and 'M13 fwd' not in sheet
    # Primers ticked in the list, all at once: one order each, none twice.
    _ok(ben.post('/api/primers', json={'name': 'M13 rev', 'sequence': 'CAGGAAACAGCTATGAC'}), 201)
    bulk = _ok(ana.post('/api/orders/many', json={'records': ['GARD-O-0001', 'gard-o-0002', 'GARD-O-0002'],
                                                  'quantity': '25 nmol'}), 201)
    assert [o['item'] for o in bulk['made']] == ['M13 fwd', 'M13 rev'] and bulk['already'] == []
    assert {o['quantity'] for o in bulk['made']} == {'25 nmol'}
    assert _ok(ana.post('/api/orders/many', json={'records': ['GARD-O-0002']}), 201)['already'][0]['item'] == 'M13 rev'
    assert ana.post('/api/orders/many', json={'records': []}).status_code == 400
    assert [p['on_order'] for p in _ok(ana.get('/api/primers'))['primers']] == [True, True]
    assert 'CAGGAAACAGCTATGAC' in lead.get('/api/orders.csv?status=requested').get_data(as_text=True)
    history = _ok(lead.get(f"/api/orders/{taq['id']}"))['order']['changes']
    assert any("'requested' → 'ordered'" in c['what'] for c in history)


def test_a_chair_group_sees_its_labs_orders_and_each_lab_orders_its_own(as_user, world):
    _lab_admins(world, 'lead')
    ana, lead, zoe, olga = (as_user(u) for u in ('ana', 'lead', 'zoe', 'olga'))
    mine = _ok(ana.post('/api/orders', json={'item': 'Phusion polymerase', 'supplier': 'NEB'}), 201)['order']
    theirs = _ok(zoe.post('/api/orders', json={'item': 'Tips', 'category': 'consumable'}), 201)['order']
    assert zoe.get(f"/api/orders/{mine['id']}").status_code == 404
    # Gardiner Lab (1) and Other Lab (2) put in one chair group on the suite's dashboard.
    conn = sqlite3.connect(world['paths']['suite'])
    conn.executescript("""
        CREATE TABLE chair_groups (id TEXT PRIMARY KEY, name TEXT UNIQUE);
        ALTER TABLE labs ADD COLUMN chair_group_id TEXT;
        INSERT INTO chair_groups VALUES ('pb', 'Plant Biology');
        UPDATE labs SET chair_group_id = 'pb';
    """)
    conn.commit()
    conn.close()
    seen = {o['item']: o for o in _ok(zoe.get('/api/orders'))['orders']}
    assert set(seen) == {'Phusion polymerase', 'Tips'}
    assert not seen['Phusion polymerase']['own_lab'] and seen['Tips']['own_lab']
    assert not seen['Phusion polymerase']['can_handle'] and not seen['Phusion polymerase']['can_change']
    # Seen across the chair group, handled by each lab's own lab admin only.
    assert zoe.put(f"/api/orders/{mine['id']}", json={'quantity': '9'}).status_code == 403
    assert olga.put(f"/api/orders/{mine['id']}", json={'status': 'ordered'}).status_code == 403
    assert lead.put(f"/api/orders/{theirs['id']}", json={'status': 'ordered'}).status_code == 403
    _ok(lead.put(f"/api/orders/{mine['id']}", json={'status': 'ordered'}))
    assert _ok(lead.get('/api/orders'))['waiting'] == 0 and _ok(olga.get('/api/orders'))['waiting'] == 1
    # The lab admin's spreadsheet: their own lab's orders, not the chair group's.
    sheet = lead.get('/api/orders.csv').get_data(as_text=True)
    assert 'Phusion polymerase' in sheet and 'Tips' not in sheet


def test_a_chemical_marked_out_goes_on_the_order_list_and_comes_back_in_stock(as_user, world):
    _lab_admins(world, 'lead')
    ana, lead = as_user('ana'), as_user('lead')
    _ok(ana.post('/api/chemicals', json={'name': 'Ethanol', 'cas': '64-17-5', 'size': '2.5 L'}), 201)
    assert _ok(ana.put('/api/chemicals/GARD-C-0001', json={'status': 'out'}))['ordered'] == 'added to the order list'
    order = _ok(lead.get('/api/orders'))['orders'][0]
    assert (order['item'], order['quantity'], order['details'], order['auto']) == ('Ethanol', '2.5 L', 'CAS 64-17-5', True)
    # Switched back before it was ordered: taken off again. Out again: back on.
    assert _ok(ana.put('/api/chemicals/GARD-C-0001', json={'status': 'in stock'}))['ordered'] == 'taken off the order list'
    assert _ok(lead.get('/api/orders/waiting'))['waiting'] == 0
    _ok(ana.put('/api/chemicals/GARD-C-0001', json={'status': 'out'}))
    assert _ok(ana.put('/api/chemicals/GARD-C-0001', json={'notes': 'big bottle'}))['ordered'] is None
    order = _ok(lead.get('/api/orders?status=requested'))['orders'][0]
    # Made out: on the list at once.
    assert _ok(ana.post('/api/chemicals', json={'name': 'Agar', 'status': 'out'}), 201)['ordered'] == 'added to the order list'
    # Once ordered, switching it back keeps the order; received, the chemical is in stock again.
    _ok(lead.put(f"/api/orders/{order['id']}", json={'status': 'ordered'}))
    assert _ok(ana.put('/api/chemicals/GARD-C-0001', json={'status': 'in stock'}))['ordered'] is None
    _ok(ana.put('/api/chemicals/GARD-C-0001', json={'status': 'out'}))
    _ok(lead.put(f"/api/orders/{order['id']}", json={'status': 'received'}))
    rec = _ok(ana.get('/api/chemicals/GARD-C-0001'))['record']
    assert rec['status'] == 'in stock' and rec['order'] is None
    assert f"(order {order['id']} received)" in rec['changes'][0]['what']
