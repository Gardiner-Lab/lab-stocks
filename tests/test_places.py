"""Stocks' places on the Lab Map: each kind keeps a place's id, and the map asks what is kept at one."""

PLACE = 'c3cd09ba9f18'


def _ok(res, status=200):
    assert res.status_code == status, res.get_json()
    return res.get_json()


def test_every_kind_keeps_its_place_and_the_map_lists_what_is_there(as_user):
    ana = as_user('ana')
    made = [
        _ok(ana.post('/api/glycerol', json={'plasmid_name': 'pSoup', 'host': 'GV3101', 'place_id': PLACE}), 201)['record'],
        _ok(ana.post('/api/primers', json={'name': 'GFP-F', 'sequence': 'ACGTACGTACGTACGTAC', 'place_id': PLACE}), 201)['record'],
        _ok(ana.post('/api/chemicals', json={'name': 'Ethanol', 'place_id': PLACE}), 201)['record'],
        _ok(ana.post('/api/antibodies', json={'short_code': 'aGFP', 'place_id': PLACE}), 201)['record'],
    ]
    assert all(r['place_id'] == PLACE for r in made)
    elsewhere = _ok(ana.post('/api/chemicals', json={'name': 'Methanol'}), 201)['record']
    assert elsewhere['place_id'] == ''

    there = _ok(ana.get(f'/api/places/{PLACE}'))['records']
    assert sorted(r['kind'] for r in there) == ['antibody', 'chemical', 'glycerol', 'primer']
    glycerol = next(r for r in there if r['kind'] == 'glycerol')
    assert glycerol['label'].endswith('pSoup') and glycerol['status'] == 'in stock'

    # Moved: off this place, and the history says so.
    code = made[2]['code']
    _ok(ana.put(f'/api/chemicals/{code}', json={'place_id': ''}))
    assert 'chemical' not in [r['kind'] for r in _ok(ana.get(f'/api/places/{PLACE}'))['records']]
    assert any('place_id' in c['what'] for c in _ok(ana.get(f'/api/chemicals/{code}'))['record']['changes'])


def test_another_lab_sees_nothing_at_the_place(as_user):
    _ok(as_user('ana').post('/api/glycerol', json={'plasmid_name': 'pSoup', 'place_id': PLACE}), 201)
    assert _ok(as_user('zoe').get(f'/api/places/{PLACE}'))['records'] == []


def test_a_place_is_an_id_from_the_map(as_user):
    ana = as_user('ana')
    res = ana.post('/api/chemicals', json={'name': 'Ethanol', 'place_id': 'the -80 in B7'})
    assert res.status_code == 400
    assert _ok(ana.get('/api/places/not-an-id'))['records'] == []


def test_search_labels_are_unchanged(as_user):
    ana = as_user('ana')
    _ok(ana.post('/api/chemicals', json={'name': 'Ethanol', 'cas': '64-17-5'}), 201)
    _ok(ana.post('/api/glycerol', json={'plasmid_name': 'pSoup', 'clone': '3'}), 201)
    labels = {r['kind']: r['label'] for r in _ok(ana.get('/api/search?q=GARD'))['results']}
    assert labels['chemical'] == 'GARD-C-0001 Ethanol (CAS 64-17-5)'
    assert labels['glycerol'] == 'GARD-G-0001 pSoup clone 3'


def test_a_box_of_tubes_goes_in_one_place(as_user):
    ana = as_user('ana')
    made = _ok(ana.post('/api/material/many', json={'items': [{'name': 'T1'}, {'name': 'T2'}], 'shared': {'tissue': 'leaf', 'place_id': PLACE}}), 201)
    codes = {r['code'] for r in _ok(ana.get(f'/api/places/{PLACE}'))['records']}
    assert len(codes) == 2, made
