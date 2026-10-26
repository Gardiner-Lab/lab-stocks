"""The copy of glycerol stocks and seed lots in eLabJournal's inventory, against a stand-in for eLab's API."""

import io
import json
import re
import sqlite3
import urllib.error
from urllib.parse import parse_qs, urlparse

import pytest

from app import elab


def _ok(r, code=200):
    assert r.status_code == code, (r.status_code, r.get_json())
    return r.get_json()


# The shared group's own sample types, as UU's eLab has them (in part).
GLYCEROL_FIELDS = [('Permit', 'COMBO', ['IG 99-249', 'new plasmid (not yet in permit)']),
                   ('Biosafety level', 'COMBO', ['I', 'II', 'III', 'IV', 'unknown']),
                   ('Host system', 'CHECKBOX', ['Yeast', '~ Other ~', 'Agrobacterium / Rhizobium', 'E. coli']),
                   ('Name of host strain', 'TEXT', []), ('Bacterial Markers', 'TEXT', ['Kanamycin']), ('Remarks', 'TEXT', []),
                   ('Plant Markers', 'TEXT', ['BASTA', 'Hygromycin']), ('Yeast Markers', 'TEXT', []),
                   ('Insert(s)?', 'CHECKBOX', ['yes', 'no']), ('geneID(s)', 'TEXT', []), ('Donororganism(s)', 'TEXT', []),
                   ('Harmful gene product?', 'RADIO', ['unknown', 'no', 'yes']),
                   ('Remarks on harmful effects (for example; Toxic / Transposase activity)', 'TEXT', []),
                   ('Plasmid sequence', 'TEXTAREA', []), ('Molecular weight (in kb)', 'TEXT', [])]
SEED_FIELDS = [('Species', 'TEXT', ['A. Thaliana']), ('Genetic background', 'TEXT', []),
               ('Zygosity', 'COMBO', ['Hemizogous', 'Heterozygous', 'Homozygous']), ('Generation', 'TEXT', []),
               ('Cross', 'CHECKBOX', ['yes', 'no']), ('Father plant', 'TEXT', []), ('Mother plant', 'TEXT', []),
               ('Description', 'TEXT', []), ('Selection marker ', 'TEXT', []), ('GMO', 'RADIO', ['No', 'Yes', 'Unknown']),
               ('Permit', 'RADIO', ['New GMO (not yet in permit)', 'IG 99-249']),
               ('Biosafety level', 'COMBO', ['IV', 'III', 'II', 'I', 'Unknown']), ('Harvest Date', 'DATE', []),
               ('Accession', 'TEXT', []), ('Stock center line', 'CHECKBOX', ['yes', 'no']),
               ('Line', 'RADIO', ['GABI', 'SAIL', 'SALK', '~other~', 'wildtype', 'non-GMO mutant']),
               ('Stock center number', 'TEXT', []), ('Web link stock center', 'TEXT', []),
               ('GMO type', 'CHECKBOX', ['Plasmid introduction', 'Chromosomal mutation', 'Unknown', 'T-DNA insertion']),
               ('Mutation information', 'TEXTAREA', []), ('Construction  method', 'TEXTAREA', []),
               ('Gene expression', 'CHECKBOX', ['marker line', 'overexpressor line', 'knock-down', 'knock-out']),
               ('Harvested by', 'TEXT', [])]


class FakeElab:
    """Enough of eLab's /api/v1: a group with its sample types, which may not be changed, and samples."""

    def __init__(self):
        self.types = {}             # id -> {'name', 'meta': [...]}
        self.samples = {}           # id -> {'sampleTypeID', 'name', 'altID', 'meta': {key: value}, 'archived', 'reason'}
        self.calls = []
        self.next_id = 1000
        self.fail_names = set()     # samples whose names contain one of these are refused
        dim = lambda r, c: {'rows': {'count': r}, 'columns': {'count': c}}     # noqa: E731
        self.units = [{'storageID': 1844, 'name': 'Freezer 1', 'deviceType': 'STORAGE', 'storageLayerID': 10},
                      {'storageID': 57129, 'name': 'PCR1', 'deviceType': 'EQUIPMENT', 'storageLayerID': 90}]
        self.definitions = {1844: [{'storageLayerDefinitionID': 6845, 'name': 'Freezer 1', 'level': 0, 'isGrid': False, 'dimension': dim(1, 1)},
                                   {'storageLayerDefinitionID': 6848, 'name': 'Tower', 'level': 1, 'isGrid': False, 'dimension': dim(1, 1)},
                                   {'storageLayerDefinitionID': 6851, 'name': 'Box', 'level': 2, 'isGrid': True, 'dimension': dim(9, 9)}],
                            57129: []}
        self.layers = {10: {'storageLayerID': 10, 'storageID': 1844, 'parentStorageLayerID': 0, 'name': 'Freezer 1',
                            'storageLayerDefinitionID': 6845, 'isGrid': False, 'dimension': dim(1, 1)},
                       11: {'storageLayerID': 11, 'storageID': 1844, 'parentStorageLayerID': 10, 'name': 'Tower 2',
                            'storageLayerDefinitionID': 6848, 'isGrid': False, 'dimension': dim(1, 1)},
                       12: {'storageLayerID': 12, 'storageID': 1844, 'parentStorageLayerID': 11, 'name': 'Box 5',
                            'storageLayerDefinitionID': 6851, 'isGrid': True, 'dimension': dim(9, 9)}}
        for name, fields in (('Glycerol Stock', GLYCEROL_FIELDS), ('Plant Seed', SEED_FIELDS), ('Primers', []), ('Plant Material', [])):
            tid = self._id()
            self.types[tid] = {'name': name, 'meta': [{'sampleTypeMetaID': self._id(), 'key': k, 'sampleDataType': t,
                                                       'optionValues': o} for k, t, o in fields]}

    def _id(self):
        self.next_id += 1
        return self.next_id

    def __call__(self, req, timeout=None):
        u = urlparse(req.full_url)
        path, q = u.path.replace('/api/v1', ''), {k: v[0] for k, v in parse_qs(u.query).items()}
        body = json.loads(req.data) if req.data else None
        method = req.get_method()
        self.calls.append((method, path))
        if req.get_header('Authorization') != 'secret':
            raise urllib.error.HTTPError(req.full_url, 401, 'Unauthorized', {}, io.BytesIO(b'{"message":"bad token"}'))
        out = self.route(method, path, q, body)
        return io.BytesIO(b'' if out is None else json.dumps(out).encode())

    def route(self, method, path, q, body):
        if path == '/storage' and method == 'GET':
            return {'data': self.units}
        m = re.fullmatch(r'/storage/(\d+)/storageLayerDefinitions', path)
        if m and method == 'GET':
            return {'data': self.definitions[int(m.group(1))]}
        if path == '/storageLayers' and method == 'GET':
            # As eLab does: pages of $records, and hasNextPage false even when there are more.
            found = [la for la in self.layers.values() if str(la['storageID']) == q.get('storageID')]
            size, page = int(q.get('$records', 1000)), int(q.get('$page', 0))
            return {'data': found[page * size:(page + 1) * size], 'hasNextPage': False, 'totalRecords': len(found)}
        m = re.fullmatch(r'/storageLayers/(\d+)/childLayers', path)
        if m and method == 'POST':
            parent = self.layers[int(m.group(1))]
            d = next(d for d in self.definitions[parent['storageID']] if d['storageLayerDefinitionID'] == body['storageLayerDefinitionID'])
            i = self._id()
            self.layers[i] = {'storageLayerID': i, 'storageID': parent['storageID'], 'parentStorageLayerID': parent['storageLayerID'],
                              'name': body['name'], 'storageLayerDefinitionID': d['storageLayerDefinitionID'],
                              'isGrid': d['isGrid'], 'dimension': d['dimension']}
            return i
        if path == '/sampleTypes' and method == 'GET':
            return {'data': [{'sampleTypeID': i, 'name': t['name']} for i, t in self.types.items()
                             if t['name'] == q.get('name', t['name'])]}
        m = re.fullmatch(r'/sampleTypes/(\d+)/meta', path)
        if m and method == 'GET':
            return {'data': self.types[int(m.group(1))]['meta']}
        if path == '/samples' and method == 'GET':
            found = [{'sampleID': i, 'owner': 'Lab Stocks', **s, 'meta': [{'key': k, 'value': v} for k, v in s['meta'].items()]}
                     for i, s in self.samples.items() if q.get('sampleTypeID', str(s['sampleTypeID'])) == str(s['sampleTypeID'])
                     and q.get('barcodes', s['altID']) == s['altID'] and q.get('name', s['name']) == s['name']
                     and ((q.get('barcodes') is None and q.get('name') is None) or not s['archived'])]
            return {'data': found, 'totalRecords': len(found)}
        if path == '/samples' and method == 'POST':
            if any(n in body['name'] for n in self.fail_names):
                raise urllib.error.HTTPError('', 400, 'Bad Request', {}, io.BytesIO(b'{"message":"no"}'))
            # The alternative id is the sample's barcode: unique in the group, archived samples' too.
            if body.get('altID') and any(s['altID'] == body['altID'] for s in self.samples.values()):
                raise urllib.error.HTTPError('', 409, 'Conflict', {}, io.BytesIO(
                    json.dumps({'message': f"A sample with barcode '{body['altID']}' already exists."}).encode()))
            # As eLab does: one sample to a place in a box.
            if body.get('position') and any(x['storageLayerID'] == body.get('storageLayerID') and x['position'] == body['position']
                                             and not x['archived'] for x in self.samples.values()):
                raise urllib.error.HTTPError('', 400, 'Bad Request', {}, io.BytesIO(json.dumps({'message': (
                    f"There is no free space at position {body['position']} in storage layer #{body['storageLayerID']}")}).encode()))
            self._options(body['sampleTypeID'], body['sampleMetas'])
            i = self._id()
            self.samples[i] = {'sampleTypeID': body['sampleTypeID'], 'name': body['name'], 'altID': body.get('altID', ''),
                               'archived': False, 'meta': {mm['key']: mm['value'] for mm in body['sampleMetas']},
                               'storageLayerID': body.get('storageLayerID'), 'position': body.get('position'),
                               'description': body.get('description', ''), 'note': body.get('note', '')}
            return i
        m = re.fullmatch(r'/samples/(\d+)(/meta)?', path)
        if m and method == 'GET' and not m.group(2):
            s = self.samples.get(int(m.group(1)))
            if s is None:
                raise urllib.error.HTTPError('', 404, 'Not Found', {}, io.BytesIO(b''))
            return {'sampleID': int(m.group(1)), 'owner': 'Lab Stocks', **s}
        if m:
            s = self.samples.get(int(m.group(1)))
            if s is None:
                raise urllib.error.HTTPError('', 404, 'Not Found', {}, io.BytesIO(b''))
            # As eLab does: no changing an archived sample, or someone else's.
            if s['archived'] or s.get('locked'):
                raise urllib.error.HTTPError('', 403, 'Forbidden', {}, io.BytesIO(
                    b'{"message":"You don\'t have permission to update this sample"}'))
            if m.group(2):
                self._options(s['sampleTypeID'], [body])
                s['meta'][body['key']] = body['value']
                return 1
            if method == 'PATCH':
                s['name'], s['altID'] = body['name'], body.get('altID', s['altID'])
                for k in ('storageLayerID', 'position', 'description', 'note'):
                    if k in body:
                        s[k] = body[k]
                return None
            if method == 'DELETE':
                s['archived'], s['reason'] = True, body
                return None
        # Anything else, making sample types or adding fields to them above all, is not done.
        raise AssertionError(f'unexpected {method} {path}')

    def _options(self, tid, metas):
        """Values of fields with options must be among them, as eLab spells them."""
        fields = {m['sampleTypeMetaID']: m for m in self.types[tid]['meta']}
        for mm in metas:
            f = fields[mm['sampleTypeMetaID']]
            assert mm['key'] == f['key']
            if f['optionValues'] and f['sampleDataType'] != 'TEXT' and mm['value']:
                assert mm['value'] in f['optionValues'], (mm['key'], mm['value'])

    def live(self, type_name):
        tid = next(i for i, t in self.types.items() if t['name'] == type_name)
        return {s['altID']: s for s in self.samples.values() if s['sampleTypeID'] == tid and not s['archived']}


def seed_bank(world, lots):
    """The Seed Bank's tables, with a line and its lots: (code, lab, generation, zygosity, used_up, father)."""
    conn = sqlite3.connect(world['paths']['seeds'])
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS lines (id TEXT PRIMARY KEY, code TEXT, lab TEXT, name TEXT, species TEXT DEFAULT '',
            background TEXT DEFAULT '', kind TEXT DEFAULT 'other', description TEXT DEFAULT '', created_at TEXT, deleted_at TEXT);
        CREATE TABLE IF NOT EXISTS lots (id TEXT PRIMARY KEY, code TEXT, lab TEXT, line_id TEXT, generation TEXT DEFAULT '',
            from_plant_id TEXT, father_plant_id TEXT, source TEXT DEFAULT '', harvested_on TEXT, amount TEXT DEFAULT '',
            location TEXT DEFAULT '', germination REAL, zygosity TEXT DEFAULT '', used_up INTEGER DEFAULT 0, notes TEXT DEFAULT '',
            created_by TEXT DEFAULT 'ana', created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT, deleted_at TEXT);
        CREATE TABLE IF NOT EXISTS plants (id TEXT PRIMARY KEY, code TEXT, lab TEXT, lot_id TEXT, line_id TEXT);
        CREATE TABLE IF NOT EXISTS line_plasmids (line_id TEXT, plasmid_id TEXT, name TEXT);
        INSERT OR IGNORE INTO lines (id, code, lab, name, species, background, kind) VALUES
            ('ln1', 'GARD-L-0001', 'Gardiner Lab', '35S:GFP', 'A. thaliana', 'Col-0', 'transgenic');
        INSERT OR IGNORE INTO plants VALUES ('pl1', 'GARD-P-0003', 'Gardiner Lab', 'x', 'ln1'), ('pl2', 'GARD-P-0009', 'Gardiner Lab', 'x', 'ln1');
    """)
    for n, (code, lab, generation, zygosity, used_up, father) in enumerate(lots):
        conn.execute("INSERT OR REPLACE INTO lots (id, code, lab, line_id, generation, from_plant_id, father_plant_id, "
                     "harvested_on, amount, zygosity, used_up) VALUES (?, ?, ?, 'ln1', ?, 'pl1', ?, '2026-05-01', '2 g', ?, ?)",
                     (f'lot{n}', code, lab, generation, father, zygosity, used_up))
    conn.commit()
    conn.close()


@pytest.fixture()
def fake(monkeypatch):
    monkeypatch.setenv('ELAB_URL', 'https://uu.elabjournal.com')
    monkeypatch.setenv('ELAB_TOKEN', 'secret')
    monkeypatch.setenv('ELAB_THREAD', '0')
    # What another test's eLab had is not remembered.
    for cache in ('_found', '_places', '_owners_at'):
        monkeypatch.setattr(elab, cache, {})
    return FakeElab()


def _run(fake, token='secret'):
    import os
    os.environ['ELAB_TOKEN'] = token
    return elab.run_once(opener=fake)


def test_glycerol_stocks_and_seed_lots_go_to_the_groups_own_sample_types(as_user, world, fake, monkeypatch):
    monkeypatch.setenv('ELAB_LABS', 'Gardiner Lab')
    ana = as_user('ana')
    g = _ok(ana.post('/api/glycerol', json={'plasmid_name': 'pGreen-35S-GFP', 'clone': '4', 'host': 'DH5α',
                                            'selection': 'Kanamycin', 'location': '-80 box 3'}), 201)['record']
    agro = _ok(ana.post('/api/glycerol', json={'plasmid_name': 'pGreen-35S-GFP', 'host': 'GV3101'}), 201)['record']
    _ok(ana.post('/api/primers', json={'name': 'M13 fwd', 'sequence': 'GTAAAACGACGGCCAGT'}), 201)
    _ok(as_user('zoe').post('/api/glycerol', json={'plasmid_name': 'Not ours'}), 201)
    seed_bank(world, [('GARD-S-0001', 'Gardiner Lab', 'T3', 'hemizygous', 0, 'pl2'),
                      ('GARD-S-0002', 'Gardiner Lab', 'T2', 'segregating', 0, None),
                      ('GARD-S-0003', 'Gardiner Lab', 'T1', '', 1, None)])
    assert _run(fake) == {'sent': 4, 'failed': 0}       # two stocks, two lots; not the used-up lot, the primer or zoe's

    glycerol = fake.live('Glycerol Stock')
    assert set(glycerol) == {g['code'], agro['code']}
    s = glycerol[g['code']]
    assert s['name'] == f"{g['code']} pGreen-35S-GFP clone 4"
    assert s['meta']['Name of host strain'] == 'DH5α' and s['meta']['Host system'] == 'E. coli'
    assert s['meta']['Bacterial Markers'] == 'Kanamycin' and 'Kept in: -80 box 3' in s['meta']['Remarks']
    assert glycerol[agro['code']]['meta']['Host system'] == 'Agrobacterium / Rhizobium'

    seeds = fake.live('Plant Seed')
    assert set(seeds) == {'GARD-S-0001', 'GARD-S-0002'}
    lot = seeds['GARD-S-0001']
    assert lot['name'] == 'GARD-S-0001 35S:GFP'
    assert lot['meta']['Zygosity'] == 'Hemizogous'                  # as eLab spells it
    assert lot['meta']['Mother plant'] == 'GARD-P-0003' and lot['meta']['Father plant'] == 'GARD-P-0009'
    assert lot['meta']['Cross'] == 'yes' and lot['meta']['GMO'] == 'Yes' and lot['meta']['Generation'] == 'T3'
    assert lot['meta']['Harvest Date'] == '2026-05-01' and 'Amount: 2 g' in lot['meta']['Description']
    assert seeds['GARD-S-0002']['meta']['Zygosity'] == ''           # segregating: none of eLab's options

    # Nothing changed: nothing sent.
    fake.calls.clear()
    assert _run(fake) == {'sent': 0, 'failed': 0}
    assert fake.calls == []

    # A change: only the fields that changed are sent (the strain, and the host system with it).
    _ok(ana.put(f"/api/glycerol/{g['code']}", json={'host': 'GV3101'}))
    fake.calls.clear()
    assert _run(fake)['sent'] == 1
    assert fake.live('Glycerol Stock')[g['code']]['meta']['Host system'] == 'Agrobacterium / Rhizobium'
    assert [m for m, _ in fake.calls if m != 'GET'] == ['PUT', 'PUT']

    # Used up or deleted: archived.
    _ok(ana.put(f"/api/glycerol/{g['code']}", json={'status': 'used up'}))
    seed_bank(world, [('GARD-S-0001', 'Gardiner Lab', 'T3', 'hemizygous', 1, 'pl2')])
    _run(fake)
    assert g['code'] not in fake.live('Glycerol Stock') and 'GARD-S-0001' not in fake.live('Plant Seed')
    assert {s['reason'] for s in fake.samples.values() if s['archived']} == {'Used up in Lab Stocks', 'Used up in the Seed Bank'}
    # Back in stock: a new sample, without the barcode its archived one keeps.
    _ok(ana.put(f"/api/glycerol/{g['code']}", json={'status': 'in stock'}))
    assert _run(fake) == {'sent': 1, 'failed': 0}
    back = [s for s in fake.samples.values() if not s['archived'] and s['name'].startswith(g['code'])]
    assert len(back) == 1 and back[0]['altID'] == '' and back[0]['meta']['Host system'] == 'Agrobacterium / Rhizobium'


def test_a_glycerol_stocks_biosafety_insert_and_plasmid_go_to_elab(as_user, world, fake, monkeypatch):
    monkeypatch.setenv('ELAB_LABS', 'Gardiner Lab')
    ana = as_user('ana')
    # The form's fields: checked.
    assert ana.post('/api/glycerol', json={'plasmid_name': 'pX', 'biosafety': 'V'}).status_code == 400
    assert ana.post('/api/glycerol', json={'plasmid_name': 'pX', 'harmful': 'maybe'}).status_code == 400
    meta = _ok(ana.get('/api/me'))['glycerol']
    assert 'IG 99-249' in meta['permits'] and 'Agrobacterium / Rhizobium' in meta['host_systems']
    g = _ok(ana.post('/api/glycerol', json={
        'plasmid_name': 'pGreen', 'host': 'GV3101', 'permit': 'new plasmid (not yet in permit)', 'biosafety': 'II',
        'host_system': 'other', 'plant_markers': 'BASTA', 'yeast_markers': 'Ura-', 'inserts': 'yes', 'gene_ids': 'AT1G01060',
        'donor': 'Arabidopsis thaliana', 'harmful': 'no', 'harmful_notes': 'none known'}), 201)['record']
    assert g['permit'] == 'new plasmid (not yet in permit)' and g['inserts'] == 'yes'
    # Linked to a plasmid of the editor: its sequence and size go too.
    linked = _ok(ana.post('/api/glycerol', json={'plasmid_name': 'pGreen-35S-GFP', 'host': 'DH5a'}), 201)['record']
    conn = sqlite3.connect(world['paths']['stocks'])
    conn.execute("UPDATE glycerol SET plasmid_id = 'p1' WHERE code = ?", (linked['code'],))
    conn.commit()
    conn.close()
    # The lab's permit and biosafety level, for stocks without their own.
    conn = sqlite3.connect(world['paths']['stocks'])
    conn.execute('INSERT INTO elab_settings (lab, url, token, kinds, sample_types, defaults) VALUES (?, ?, ?, ?, ?, ?)',
                 ('Gardiner Lab', 'https://uu.elabjournal.com', 'secret', '["glycerol"]', '{}',
                  json.dumps({'glycerol': {'Permit': 'IG 99-249', 'Biosafety level': 'I'}})))
    conn.commit()
    conn.close()
    assert _run(fake) == {'sent': 2, 'failed': 0}
    s = fake.live('Glycerol Stock')[g['code']]['meta']
    assert s['Permit'] == 'new plasmid (not yet in permit)' and s['Biosafety level'] == 'II'
    assert s['Host system'] == '~ Other ~' and s['Plant Markers'] == 'BASTA' and s['Yeast Markers'] == 'Ura-'
    assert s['Insert(s)?'] == 'yes' and s['geneID(s)'] == 'AT1G01060' and s['Donororganism(s)'] == 'Arabidopsis thaliana'
    assert s['Harmful gene product?'] == 'no'
    assert s['Remarks on harmful effects (for example; Toxic / Transposase activity)'] == 'none known'
    t = fake.live('Glycerol Stock')[linked['code']]['meta']
    assert t['Permit'] == 'IG 99-249' and t['Biosafety level'] == 'I' and t['Host system'] == 'E. coli'
    assert t['Plasmid sequence'] == 'ACGT' * 100 and t['Molecular weight (in kb)'] == '0.4'


def test_an_older_database_gets_the_new_glycerol_columns(world):
    from app import db
    conn = sqlite3.connect(world['paths']['stocks'])
    conn.executescript("""
        ALTER TABLE glycerol RENAME TO glycerol_new;
        CREATE TABLE glycerol (id TEXT PRIMARY KEY, code TEXT UNIQUE NOT NULL, lab TEXT NOT NULL, plasmid_id TEXT,
            plasmid_name TEXT NOT NULL DEFAULT '', clone TEXT NOT NULL DEFAULT '', host TEXT NOT NULL DEFAULT '',
            selection TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '', made_on TEXT,
            source TEXT NOT NULL DEFAULT 'manual', status TEXT NOT NULL DEFAULT 'in stock', notes TEXT NOT NULL DEFAULT '',
            created_by TEXT, created_at TIMESTAMP, updated_at TIMESTAMP, deleted_at TIMESTAMP);
        INSERT INTO glycerol (id, code, lab, plasmid_name) VALUES ('old', 'GARD-G-0001', 'Gardiner Lab', 'pOld');
    """)
    conn.commit()
    conn.close()
    db.initialize(world['paths']['stocks'])
    conn = sqlite3.connect(world['paths']['stocks'])
    row = conn.execute("SELECT permit, harmful, plasmid_name FROM glycerol WHERE id = 'old'").fetchone()
    conn.close()
    assert row == ('', '', 'pOld')


def test_a_seed_lots_line_biosafety_stock_center_and_genetics_go_to_elab(as_user, world, fake, monkeypatch):
    monkeypatch.setenv('ELAB_LABS', 'Gardiner Lab')
    seed_bank(world, [])
    conn = sqlite3.connect(world['paths']['seeds'])
    for column in ('permit', 'biosafety', 'gmo_type', 'accession', 'collection', 'stock_center_number', 'stock_center_url',
                   'selection_marker', 'gene_expression', 'mutation_info', 'construction'):
        conn.execute(f"ALTER TABLE lines ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
    conn.execute("INSERT INTO lines (id, code, lab, name, species, kind, permit, biosafety, gmo_type, accession, collection, "
                 "stock_center_number, stock_center_url, selection_marker, gene_expression, mutation_info, construction) "
                 "VALUES ('ln2', 'GARD-L-0002', 'Gardiner Lab', 'myb21-1', 'A. thaliana', 'mutant', 'IG 99-249', 'I', "
                 "'T-DNA insertion', 'N512345', 'SALK', 'SALK_012345C', 'https://abrc.osu.edu/x', 'Kanamycin', 'knock-out', "
                 "'T-DNA in exon 2', 'floral dip')")
    conn.execute("INSERT INTO lots (id, code, lab, line_id, generation, created_by) "
                 "VALUES ('lotm', 'GARD-S-0010', 'Gardiner Lab', 'ln2', 'T4', 'ben')")
    conn.commit()
    conn.close()
    assert _run(fake) == {'sent': 1, 'failed': 0}
    s = fake.live('Plant Seed')['GARD-S-0010']['meta']
    assert s['Permit'] == 'IG 99-249' and s['Biosafety level'] == 'I'
    assert s['GMO'] == 'Yes' and s['GMO type'] == 'T-DNA insertion' and s['Gene expression'] == 'knock-out'
    assert s['Line'] == 'SALK' and s['Stock center line'] == 'yes' and s['Stock center number'] == 'SALK_012345C'
    assert s['Accession'] == 'N512345' and s['Web link stock center'] == 'https://abrc.osu.edu/x'
    assert s['Selection marker '] == 'Kanamycin' and s['Mutation information'] == 'T-DNA in exon 2'
    assert s['Construction  method'] == 'floral dip' and s['Harvested by'] == 'ben'


def test_a_glycerol_stock_is_kept_in_elabs_storage_chosen_or_added_from_its_form(as_user, world, fake, monkeypatch):
    monkeypatch.setenv('ELAB_LABS', 'Gardiner Lab')
    monkeypatch.setattr(elab.urllib.request, 'urlopen', fake)
    ana = as_user('ana')
    # The group's storage: its units' compartments with their paths, not its equipment.
    found = _ok(ana.get('/api/elab/locations'))
    assert found['connected']
    assert [(p['path'], p['grid']) for p in found['locations']] == [
        ('Freezer 1', False), ('Freezer 1 / Tower 2', False), ('Freezer 1 / Tower 2 / Box 5', True)]
    box = found['locations'][2]
    assert (box['rows'], box['columns'], box['level'], box['lettered']) == (9, 9, 2, False)
    assert [k['name'] for k in found['kinds']['1844']] == ['Freezer 1', 'Tower', 'Box']

    # A new location, added in eLab from the form: under a compartment that is not a box, of a kind for that level.
    assert 'Give the new location a name' in ana.post('/api/elab/locations', json={'parent': 11, 'name': '', 'kind': 6851}).get_json()['error']
    assert 'box with places' in ana.post('/api/elab/locations', json={'parent': 12, 'name': 'x', 'kind': 6851}).get_json()['error']
    assert 'what kind' in ana.post('/api/elab/locations', json={'parent': 11, 'name': 'x', 'kind': 6848}).get_json()['error']
    made = _ok(ana.post('/api/elab/locations', json={'parent': 11, 'name': 'Box 12 glycerol', 'kind': 6851}), 201)['location']
    assert made['path'] == 'Freezer 1 / Tower 2 / Box 12 glycerol' and made['grid']
    assert fake.layers[made['id']]['parentStorageLayerID'] == 11
    assert made['path'] in [p['path'] for p in _ok(ana.get('/api/elab/locations'))['locations']]

    # Kept there, in place 12 (B3): its sample is put there in eLab; moved, it moves.
    assert ana.post('/api/glycerol', json={'plasmid_name': 'pX', 'elab_layer_id': 'Box 5'}).status_code == 400
    g = _ok(ana.post('/api/glycerol', json={'plasmid_name': 'pX', 'host': 'DH5a', 'elab_layer_id': str(made['id']),
                                            'elab_layer_path': made['path'], 'elab_position': '12'}), 201)['record']
    assert g['elab_layer_path'] == made['path']
    assert _run(fake) == {'sent': 1, 'failed': 0}
    sample = fake.live('Glycerol Stock')[g['code']]
    assert (sample['storageLayerID'], sample['position']) == (made['id'], 12)
    _ok(ana.put(f"/api/glycerol/{g['code']}", json={'elab_layer_id': '11', 'elab_layer_path': 'Freezer 1 / Tower 2',
                                                    'elab_position': ''}))
    fake.calls.clear()
    assert _run(fake)['sent'] == 1
    assert ('PATCH', f"/samples/{next(i for i, x in fake.samples.items() if x['altID'] == g['code'])}") in fake.calls
    assert (fake.live('Glycerol Stock')[g['code']]['storageLayerID'], fake.live('Glycerol Stock')[g['code']]['position']) == (11, None)
    # No longer kept in eLab's storage: the path and place go with it.
    _ok(ana.put(f"/api/glycerol/{g['code']}", json={'elab_layer_id': ''}))
    assert _ok(ana.get(f"/api/glycerol/{g['code']}"))['record']['elab_layer_path'] == ''


def _type(fake, name):
    return next(i for i, t in fake.types.items() if t['name'] == name)


def test_plant_material_one_tube_or_a_box_of_them(as_user, world):
    ana = as_user('ana')
    assert ana.post('/api/material', json={'tissue': 'leaf'}).status_code == 400          # a name on the tube
    t = _ok(ana.post('/api/material', json={'name': 'P130-34 F3', 'tissue': 'flower', 'species': 'Petunia W138',
                                            'collected_on': '2025-01-17', 'collected_by': 'Noor'}), 201)['record']
    assert t['code'] == 'GARD-M-0001' and t['kind'] == 'material'
    # A box of tubes at once: their own names, the rest shared.
    many = _ok(ana.post('/api/material/many', json={'items': [{'name': f'L2201-{n}', 'elab_position': str(n)} for n in range(1, 82)],
                                                    'shared': {'tissue': 'leaf', 'experiment': 'UvA sampling'}}), 201)['material']
    assert len(many) == 81 and many[-1]['code'] == 'GARD-M-0082' and many[-1]['name'] == 'L2201-81'
    assert many[0]['tissue'] == 'leaf' and many[0]['experiment'] == 'UvA sampling'
    assert ana.post('/api/material/many', json={'items': [{'name': 'ok'}, {'tissue': 'no name'}]}).status_code == 400
    assert len(_ok(ana.get('/api/material'))['material']) == 82                            # all or none
    assert ana.post('/api/material/many', json={'items': [{'name': str(n)} for n in range(501)]}).status_code == 400
    # Found by the notebook, for tagging; not ordered.
    found = _ok(ana.get('/api/search?q=P130-34'))['results']
    assert found[0]['kind'] == 'material' and found[0]['code'] == 'GARD-M-0001' and 'flower' in found[0]['label']
    assert [r['code'] for r in _ok(ana.get('/api/material?q=Noor'))['material']] == ['GARD-M-0001']
    assert ana.post('/api/orders', json={'record': 'GARD-M-0001'}).status_code == 400
    assert _ok(ana.get('/api/material/GARD-M-0001'))['record']['name'] == 'P130-34 F3'
    assert as_user('zoe').get('/api/material/GARD-M-0001').status_code == 404


def test_plant_material_goes_to_elabs_plant_material(as_user, world, fake, monkeypatch):
    monkeypatch.setenv('ELAB_LABS', 'Gardiner Lab')
    conn = sqlite3.connect(world['paths']['stocks'])
    conn.execute('INSERT INTO elab_settings (lab, url, token, kinds, sample_types) VALUES (?, ?, ?, ?, ?)',
                 ('Gardiner Lab', 'https://uu.elabjournal.com', 'secret', '["material"]', '{}'))
    conn.commit()
    conn.close()
    t = _ok(as_user('ana').post('/api/material', json={
        'name': 'P130-34 F3', 'tissue': 'flower', 'species': 'Petunia W138', 'collected_by': 'Noor',
        'elab_layer_id': '12', 'elab_layer_path': 'Freezer 1 / Tower 2 / Box 5', 'elab_position': '7'}), 201)['record']
    assert _run(fake) == {'sent': 1, 'failed': 0}
    s = fake.live('Plant Material')[t['code']]
    assert s['name'] == 'P130-34 F3' and s['description'] == 'flower · Petunia W138'
    assert s['note'].startswith('By Noor') and (s['storageLayerID'], s['position']) == (12, 7)
    _ok(as_user('ana').put(f"/api/material/{t['code']}", json={'description': 'Petunia W138 flower tissue'}))
    _run(fake)
    assert fake.live('Plant Material')[t['code']]['description'] == 'Petunia W138 flower tissue · Petunia W138'


def test_bringing_over_elabs_plant_material_and_seed_samples(as_user, world, fake, monkeypatch):
    monkeypatch.setenv('ELAB_LABS', 'Gardiner Lab')
    monkeypatch.setattr(elab.urllib.request, 'urlopen', fake)
    _lab_admin(world)
    lead, ana = as_user('lead'), as_user('ana')
    pm, ps = _type(fake, 'Plant Material'), _type(fake, 'Plant Seed')
    for n in (1, 2, 3):
        fake.samples[100 + n] = {'sampleTypeID': pm, 'name': f'P130-34 F{n}', 'altID': '', 'archived': False, 'meta': {},
                                 'owner': 'Pat Student', 'description': 'Petunia W138 flower tissue',
                                 'note': 'collected by Noor ', 'storageLayerID': 12, 'position': n}
    fake.samples[110] = {'sampleTypeID': pm, 'name': 'theirs', 'altID': '', 'archived': False, 'meta': {}, 'owner': 'Someone Else',
                         'description': '', 'note': '', 'storageLayerID': None, 'position': None}
    for n in (1, 2):
        fake.samples[200 + n] = {'sampleTypeID': ps, 'name': f'sLAB000000{n}', 'altID': '', 'archived': False,
                                 'meta': {'Species': 'P. hybrida', 'Biosafety level': 'I'}, 'owner': 'Lab Lead',
                                 'description': '', 'note': 'W138', 'storageLayerID': None, 'position': None}
    # Only the lab admin.
    assert ana.get('/api/elab/import?kind=material').status_code == 403
    found = _ok(lead.get('/api/elab/import?kind=material'))
    assert found['owners'] == [['Pat Student', 3, 0], ['Someone Else', 1, 0]]
    assert {s['path'] for s in found['samples'] if s['owner'] == 'Pat Student'} == {'Freezer 1 / Tower 2 / Box 5'}

    # Plant material: made here, in their places, linked; nothing changed in eLab.
    res = _ok(lead.post('/api/elab/import/material', json={'ids': [101, 102, 103]}), 201)
    assert res == {'made': 3, 'linked': 3}
    tubes = {t['name']: t for t in _ok(lead.get('/api/material'))['material']}
    t = tubes['P130-34 F2']
    assert t['tissue'] == 'flower' and t['collected_by'] == 'Noor' and t['elab_layer_id'] == '12' and t['elab_position'] == '2'
    fake.calls.clear()
    assert _run(fake) == {'sent': 0, 'failed': 0}
    assert all(m == 'GET' for m, _ in fake.calls)
    found = _ok(lead.get('/api/elab/import?kind=material'))
    assert [s['id'] for s in found['samples']] == [110]
    assert found['owners'] == [['Someone Else', 1, 0], ['Pat Student', 0, 3]]       # still named, nothing to bring
    # Changed here: eLab follows, the sample keeping its name there.
    _ok(lead.put(f"/api/material/{t['code']}", json={'elab_position': '9'}))
    assert _run(fake)['sent'] == 1
    assert fake.samples[102]['name'] == 'P130-34 F2' and fake.samples[102]['position'] == 9

    # Seed samples: the page makes their lines and lots in the Seed Bank; here they are linked.
    assert {s['note'] for s in _ok(lead.get('/api/elab/import?kind=seed'))['samples']} == {'W138'}
    seed_bank(world, [('GARD-S-0001', 'Gardiner Lab', '', '', 0, None), ('GARD-S-0002', 'Gardiner Lab', '', '', 0, None)])
    monkeypatch.setenv('ELAB_KINDS', 'glycerol,material,seed')
    linked = _ok(lead.post('/api/elab/adopt', json={'pairs': [{'code': 'GARD-S-0001', 'sample_id': 201, 'name': 'sLAB0000001'},
                                                              {'code': 'GARD-S-0002', 'sample_id': 202, 'name': 'sLAB0000002'},
                                                              {'code': 'GARD-S-9999', 'sample_id': 203, 'name': 'none'}]}))
    assert linked == {'linked': 2}
    conn = sqlite3.connect(world['paths']['stocks'])
    conn.execute('INSERT INTO elab_settings (lab, url, token, kinds, sample_types) VALUES (?, ?, ?, ?, ?)',
                 ('Gardiner Lab', 'https://uu.elabjournal.com', 'secret', '["material", "seed"]', '{}'))
    conn.commit()
    conn.close()
    assert _ok(lead.get('/api/elab/import?kind=seed'))['samples'] == []
    fake.calls.clear()
    assert _run(fake) == {'sent': 0, 'failed': 0}                      # nothing rewritten in eLab
    assert fake.samples[201]['name'] == 'sLAB0000001'


def test_bringing_over_in_batches_makes_each_once(as_user, world, fake, monkeypatch):
    # The page sends a few at a time, for its progress bar; sent again, one already here is not made twice.
    monkeypatch.setenv('ELAB_LABS', 'Gardiner Lab')
    monkeypatch.setattr(elab.urllib.request, 'urlopen', fake)
    _lab_admin(world)
    lead = as_user('lead')
    pm = _type(fake, 'Plant Material')
    for n in range(1, 6):
        fake.samples[300 + n] = {'sampleTypeID': pm, 'name': f'Tube {n}', 'altID': '', 'archived': False, 'meta': {},
                                 'owner': 'Pat Student', 'description': '', 'note': '', 'storageLayerID': None, 'position': None}
    assert len(_ok(lead.get('/api/elab/import?kind=material'))['samples']) == 5
    assert _ok(lead.post('/api/elab/import/material', json={'ids': [301, 302, 303]}), 201)['made'] == 3
    assert _ok(lead.post('/api/elab/import/material', json={'ids': [303, 304, 305]}), 201)['made'] == 2
    assert sorted(t['name'] for t in _ok(lead.get('/api/material'))['material']) == [f'Tube {n}' for n in range(1, 6)]
    assert _ok(lead.get('/api/elab/import?kind=material'))['samples'] == []


def test_archived_in_elab_is_left_so_and_others_samples_fail_alone(as_user, world, fake, monkeypatch):
    monkeypatch.setenv('ELAB_LABS', 'Gardiner Lab')
    ana = as_user('ana')
    a = _ok(ana.post('/api/glycerol', json={'plasmid_name': 'pA', 'host': 'DH5a'}), 201)['record']
    b = _ok(ana.post('/api/glycerol', json={'plasmid_name': 'pB', 'host': 'DH5a'}), 201)['record']
    c = _ok(ana.post('/api/glycerol', json={'plasmid_name': 'pC', 'host': 'DH5a'}), 201)['record']
    assert _run(fake)['sent'] == 3
    ids = {x['altID']: i for i, x in fake.samples.items()}
    fake.samples[ids[a['code']]]['archived'] = True                 # archived in eLab, by someone there
    fake.samples[ids[b['code']]].update(locked=True, owner='Pat Student')   # not this account's to change
    for code in (a['code'], b['code'], c['code']):
        _ok(ana.put(f'/api/glycerol/{code}', json={'host': 'GV3101'}))
    # One refused does not stop the others; the archived one is left so, and not made again.
    assert _run(fake) == {'sent': 2, 'failed': 1}
    assert fake.samples[ids[c['code']]]['meta']['Host system'] == 'Agrobacterium / Rhizobium'
    assert sum(1 for x in fake.samples.values() if x['name'].startswith(a['code'])) == 1
    s = _ok(ana.get('/api/elab'))
    assert s['held'] == 1 and s['last_error'] is None
    assert s['failed'] == [{'kind': 'glycerol', 'code': b['code'],
                            'error': "eLab answered 403: eLab does not let this account change it: it is Pat Student's"}]
    _ok(ana.put(f"/api/glycerol/{a['code']}", json={'notes': 'still here'}))
    fake.calls.clear()
    _run(fake)
    assert not any(p.endswith(str(ids[a['code']])) or m == 'POST' for m, p in fake.calls)


def test_syncing_makes_nothing_twice(as_user, world, fake, monkeypatch):
    monkeypatch.setenv('ELAB_LABS', 'Gardiner Lab')
    ana = as_user('ana')
    ps, gs, pr = _type(fake, 'Plant Seed'), _type(fake, 'Glycerol Stock'), _type(fake, 'Primers')
    # Seed lots brought over from eLab, whose link was not made (the page closed, a network blip):
    # linked by their name there, never made a second time; one eLab has no more is not sent at all.
    fake.samples[301] = {'sampleTypeID': ps, 'name': 'sLAB0000301', 'altID': '', 'archived': False, 'meta': {}}
    seed_bank(world, [('GARD-S-0001', 'Gardiner Lab', '', '', 0, None), ('GARD-S-0002', 'Gardiner Lab', '', '', 0, None)])
    conn = sqlite3.connect(world['paths']['seeds'])
    conn.execute("UPDATE lots SET source = 'eLab sLAB0000301' WHERE code = 'GARD-S-0001'")
    conn.execute("UPDATE lots SET source = 'eLab sLAB0000999' WHERE code = 'GARD-S-0002'")
    conn.commit()
    conn.close()
    fake.calls.clear()
    assert _run(fake) == {'sent': 0, 'failed': 1}
    assert not any(m == 'POST' for m, _ in fake.calls)
    link = elab._links('seed')['lot0']
    assert link['sample_id'] == 301 and link['elab_name'] == 'sLAB0000301'
    assert 'not sent, so as not to make it twice' in elab._links('seed')['lot1']['error']
    assert _run(fake) == {'sent': 0, 'failed': 0} and fake.samples[301]['name'] == 'sLAB0000301'

    # A code already a live sample's barcode in the group (another Lab Stocks sending this lab, say):
    # not made again without its barcode, but listed as failed.
    fake.samples[302] = {'sampleTypeID': pr, 'name': 'from the other one', 'altID': 'GARD-G-0001', 'archived': False, 'meta': {}}
    _ok(ana.post('/api/glycerol', json={'plasmid_name': 'pX'}), 201)
    assert _run(fake) == {'sent': 0, 'failed': 1}
    assert [x for x in fake.samples.values() if x['sampleTypeID'] == gs] == []
    assert 'already in eLab' in _ok(ana.get('/api/elab'))['failed'][0]['error']

    # Sent once without its barcode, its link lost: found again by its name, not made again.
    fake.samples[303] = {'sampleTypeID': gs, 'name': 'GARD-G-0002 pY', 'altID': '', 'archived': False, 'meta': {}}
    y = _ok(ana.post('/api/glycerol', json={'plasmid_name': 'pY'}), 201)['record']
    _run(fake)
    assert elab._links('glycerol')[y['id']]['sample_id'] == 303
    assert sum(1 for x in fake.samples.values() if x['name'] == 'GARD-G-0002 pY') == 1

    # A sample is linked to one record only.
    assert elab.adopt('Gardiner Lab', 'glycerol', [(y['id'], 303, 'x'), ('other', 303, 'x')], opener=fake) == 1


def test_the_import_leaves_out_what_was_brought_over(as_user, world, fake, monkeypatch):
    monkeypatch.setenv('ELAB_LABS', 'Gardiner Lab')
    monkeypatch.setattr(elab.urllib.request, 'urlopen', fake)
    _lab_admin(world)
    ps = _type(fake, 'Plant Seed')
    for n in (1, 2):
        fake.samples[400 + n] = {'sampleTypeID': ps, 'name': f'sLAB000040{n}', 'altID': '', 'archived': False, 'meta': {},
                                 'owner': 'Lab Lead', 'note': 'W138', 'description': ''}
    seed_bank(world, [('GARD-S-0001', 'Gardiner Lab', '', '', 0, None)])
    conn = sqlite3.connect(world['paths']['seeds'])
    conn.execute("UPDATE lots SET source = 'eLab sLAB0000401'")
    conn.commit()
    conn.close()
    # Its lot made in the Seed Bank, but not yet linked: not offered again.
    assert [s['name'] for s in _ok(as_user('lead').get('/api/elab/import?kind=seed&refresh=1'))['samples']] == ['sLAB0000402']


def test_bringing_over_elabs_glycerol_stocks(as_user, world, fake, monkeypatch):
    monkeypatch.setenv('ELAB_LABS', 'Gardiner Lab')
    monkeypatch.setattr(elab.urllib.request, 'urlopen', fake)
    _lab_admin(world)
    lead = as_user('lead')
    gs = _type(fake, 'Glycerol Stock')
    fake.samples[501] = {'sampleTypeID': gs, 'name': 'pGreen-35S-GFP', 'altID': '', 'archived': False, 'owner': 'Robin Colleague',
                         'description': '', 'note': 'from Evelien', 'storageLayerID': 12, 'position': 4,
                         'meta': {'Name of host strain': 'E.coli DH5a', 'Host system': 'E. coli', 'Bacterial Markers': 'Kanamycin',
                                  'Permit': 'IG 99-249', 'Biosafety level': 'I', 'Insert(s)?': 'yes', 'geneID(s)': 'AT1G01060',
                                  'Harmful gene product?': 'no', 'Remarks': 'GFP fusion',
                                  'Remarks on harmful effects (for example; Toxic / Transposase activity)': 'none'}}
    fake.samples[502] = {'sampleTypeID': gs, 'name': 'gNP038', 'altID': '', 'archived': False, 'owner': 'Robin Colleague',
                         'description': '', 'note': '', 'storageLayerID': None, 'position': None,
                         'meta': {'Host system': '~ Other ~', 'Biosafety level': 'unknown'}}
    found = _ok(lead.get('/api/elab/import?kind=glycerol'))
    assert found['owners'] == [['Robin Colleague', 2, 0]] and found['samples'][0]['strain'] == 'E.coli DH5a'
    assert as_user('ana').post('/api/elab/import/glycerol', json={'ids': [501]}).status_code == 403
    res = _ok(lead.post('/api/elab/import/glycerol', json={'ids': [501, 502]}), 201)
    assert res == {'made': 2, 'linked': 2, 'plasmids': 1}
    got = {r['plasmid_name']: r for r in _ok(lead.get('/api/glycerol'))['glycerol']}
    g = got['pGreen-35S-GFP']
    assert g['plasmid_id'] == 'p1' and g['host'] == 'E.coli DH5a' and g['selection'] == 'Kanamycin'
    assert (g['permit'], g['biosafety'], g['host_system'], g['inserts'], g['harmful']) == ('IG 99-249', 'I', 'E. coli', 'yes', 'no')
    assert g['gene_ids'] == 'AT1G01060' and g['harmful_notes'] == 'none' and 'GFP fusion' in g['notes']
    assert (g['elab_layer_id'], g['elab_position'], g['elab_layer_path']) == ('12', '4', 'Freezer 1 / Tower 2 / Box 5')
    assert got['gNP038']['host_system'] == 'other' and got['gNP038']['plasmid_id'] in (None, '')
    # Made by their owner in eLab, not by who brought them over.
    assert g['created_by'] == 'Robin Colleague' and got['gNP038']['created_by'] == 'Robin Colleague'
    # Linked, keeping their names in eLab; nothing changed there; not offered again.
    fake.calls.clear()
    assert _run(fake) == {'sent': 0, 'failed': 0}
    assert all(m == 'GET' for m, _ in fake.calls)
    found = _ok(lead.get('/api/elab/import?kind=glycerol'))
    assert found['samples'] == [] and found['owners'] == [['Robin Colleague', 0, 2]]
    _ok(lead.put(f"/api/glycerol/{g['code']}", json={'clone': '2'}))
    _run(fake)
    assert fake.samples[501]['name'] == 'pGreen-35S-GFP' and 'Clone: 2' in fake.samples[501]['meta']['Remarks']
    # Its owner changed in eLab: eLab is right, and the history says so. One made here and sent keeps its maker.
    mine = _ok(lead.post('/api/glycerol', json={'plasmid_name': 'pMine', 'lab': 'Gardiner Lab'}), 201)
    _run(fake)
    fake.samples[501]['owner'] = 'Sam Postdoc'
    _ok(lead.get('/api/elab/import?kind=glycerol&refresh=1'))
    got = {r['plasmid_name']: r for r in _ok(lead.get('/api/glycerol'))['glycerol']}
    assert got['pGreen-35S-GFP']['created_by'] == 'Sam Postdoc' and got['gNP038']['created_by'] == 'Robin Colleague'
    assert got['pMine']['created_by'] == 'lead'
    with sqlite3.connect(world['paths']['stocks']) as conn:
        assert conn.execute("SELECT changed_by, what FROM changes WHERE record_id = ? ORDER BY rowid DESC",
                            (g['id'],)).fetchone() == ('eLab', 'made by Sam Postdoc, as its owner in eLab')


def test_a_records_page_links_to_its_elab_sample_and_sends_again(as_user, world, fake, monkeypatch):
    monkeypatch.setenv('ELAB_LABS', 'Gardiner Lab')
    monkeypatch.setattr(elab.urllib.request, 'urlopen', fake)
    ana = as_user('ana')
    a = _ok(ana.post('/api/glycerol', json={'plasmid_name': 'pA'}), 201)['record']
    b = _ok(ana.post('/api/glycerol', json={'plasmid_name': 'pB'}), 201)['record']
    assert _ok(ana.get(f"/api/glycerol/{a['code']}"))['record']['elab']['state'] == 'waiting'
    _run(fake)
    e = _ok(ana.get(f"/api/glycerol/{a['code']}"))['record']['elab']
    sid = {x['altID']: i for i, x in fake.samples.items()}
    assert e['state'] == 'sent' and e['sample_id'] == sid[a['code']]
    assert e['url'] == f"https://uu.elabjournal.com/members/inventory-rebuild/#/samples/{sid[a['code']]}"
    assert ana.post(f"/api/glycerol/{a['code']}/elab-again").status_code == 400     # not archived in eLab
    # Both archived in eLab; one restored there.
    for code in (a['code'], b['code']):
        fake.samples[sid[code]]['archived'] = True
        _ok(ana.put(f'/api/glycerol/{code}', json={'notes': 'changed'}))
    _run(fake)
    assert _ok(ana.get(f"/api/glycerol/{a['code']}"))['record']['elab']['state'] == 'archived in eLab'
    fake.samples[sid[a['code']]]['archived'] = False
    assert _ok(ana.post(f"/api/glycerol/{a['code']}/elab-again")) == {'restored': True}
    assert _ok(ana.post(f"/api/glycerol/{b['code']}/elab-again")) == {'restored': False}
    _run(fake)
    # The restored one follows again; the other is a new sample (without the code its archived one keeps).
    assert 'changed' in fake.samples[sid[a['code']]]['meta']['Remarks']
    news = [x for i, x in fake.samples.items() if x['name'].startswith(b['code']) and not x['archived']]
    assert len(news) == 1 and news[0]['altID'] == ''
    assert _ok(ana.get(f"/api/glycerol/{b['code']}"))['record']['elab']['state'] == 'sent'
    # An administrator sees it too.
    assert _ok(as_user('boss').get(f"/api/glycerol/{a['code']}"))['record']['elab'] is not None


def test_a_sample_already_there_is_found_by_its_code(as_user, world, fake):
    g = _ok(as_user('ana').post('/api/glycerol', json={'plasmid_name': 'pX', 'host': 'DH5a'}), 201)['record']
    tid = next(i for i, t in fake.types.items() if t['name'] == 'Glycerol Stock')
    fake.samples[5] = {'sampleTypeID': tid, 'name': 'old name', 'altID': g['code'], 'archived': False, 'meta': {}}
    assert _run(fake) == {'sent': 1, 'failed': 0}
    assert list(fake.live('Glycerol Stock')) == [g['code']] and fake.samples[5]['name'] == f"{g['code']} pX"


def test_failures_are_kept_and_shown(as_user, world, fake):
    _lab_admin(world)
    ana, lead = as_user('ana'), as_user('lead')
    _ok(ana.post('/api/glycerol', json={'plasmid_name': 'Refused'}), 201)
    _ok(ana.post('/api/glycerol', json={'plasmid_name': 'Fine'}), 201)
    fake.fail_names.add('Refused')
    assert _run(fake) == {'sent': 1, 'failed': 1}
    s = _ok(lead.get('/api/elab'))
    assert s['connected'] and s['source'] == 'settings' and s['lab'] == 'Gardiner Lab' and s['can_set']
    assert s['synced'] == 1 and [f['code'] for f in s['failed']] == ['GARD-G-0001']
    assert not _ok(ana.get('/api/elab'))['can_set']
    assert ana.post('/api/elab/sync').status_code == 403
    _ok(lead.post('/api/elab/sync'))
    # Not tried again straight away, unless it changes.
    assert _run(fake) == {'sent': 0, 'failed': 0}
    fake.fail_names.clear()
    _ok(ana.put('/api/glycerol/GARD-G-0001', json={'notes': 'try again'}))
    assert _run(fake) == {'sent': 1, 'failed': 0}
    assert _ok(lead.get('/api/elab'))['failed'] == []


def test_a_bad_token_stops_the_round(as_user, world, fake):
    _ok(as_user('ana').post('/api/glycerol', json={'plasmid_name': 'pX'}), 201)
    assert _run(fake, token='not the token') == {'sent': 0, 'failed': 0}
    assert 'no longer accepts the token' in _ok(as_user('ana').get('/api/elab'))['last_error']


def test_off_without_settings(as_user, world, monkeypatch):
    monkeypatch.delenv('ELAB_URL', raising=False)
    _ok(as_user('ana').post('/api/glycerol', json={'plasmid_name': 'pX'}), 201)
    assert elab.run_once() == {'sent': 0, 'failed': 0}
    assert not _ok(as_user('ana').get('/api/elab'))['connected']


def test_a_lab_admin_connects_the_lab_on_the_page(as_user, world, fake, monkeypatch):
    monkeypatch.delenv('ELAB_URL')
    monkeypatch.delenv('ELAB_TOKEN')
    monkeypatch.setattr(elab.urllib.request, 'urlopen', fake)
    _lab_admin(world)
    ana, lead, zoe = as_user('ana'), as_user('lead'), as_user('zoe')
    g = _ok(ana.post('/api/glycerol', json={'plasmid_name': 'pX', 'host': 'DH5α'}), 201)['record']
    _ok(zoe.post('/api/glycerol', json={'plasmid_name': 'Theirs'}), 201)
    s = _ok(lead.get('/api/elab'))
    assert not s['connected'] and s['can_set'] and s['default_url'] == 'https://uu.elabjournal.com'
    assert [k for k, _, _ in s['all_kinds']] == ['glycerol', 'material', 'seed']
    # Only the lab admin; only eLab's own hosts; a token eLab accepts.
    assert ana.post('/api/elab/check', json={'url': 'https://uu.elabjournal.com', 'token': 'secret'}).status_code == 403
    assert 'not an eLab address' in lead.post('/api/elab/check', json={'url': 'http://moclo:5000', 'token': 'secret'}).get_json()['error']
    assert 'did not accept' in lead.post('/api/elab/check', json={'url': 'uu.elabjournal.com', 'token': 'nope'}).get_json()['error']
    found = _ok(lead.post('/api/elab/check', json={'url': 'uu.elabjournal.com', 'token': 'secret'}))
    assert found['sample_types'] == ['Glycerol Stock', 'Plant Material', 'Plant Seed', 'Primers']
    assert found['fields']['Glycerol Stock']['Permit'] == ['IG 99-249', 'new plasmid (not yet in permit)']
    # Only the group's own sample types.
    assert 'no sample type called' in lead.put('/api/elab', json={
        'url': 'uu.elabjournal.com', 'token': 'secret', 'kinds': ['glycerol'], 'sample_types': {'glycerol': 'Glycerol stocks (new)'}
    }).get_json()['error']
    s = _ok(lead.put('/api/elab', json={'url': 'uu.elabjournal.com', 'token': 'secret', 'kinds': ['glycerol'],
                                        'sample_types': {'glycerol': 'glycerol stock'},
                                        'defaults': {'glycerol': {'Permit': 'IG 99-249', 'Biosafety level': 'I'}}}))
    assert s['connected'] and s['url'] == 'https://uu.elabjournal.com' and s['kinds'] == ['glycerol']
    assert s['sample_types'] == {'glycerol': 'Glycerol Stock'} and s['waiting'] == 1 and 'token' not in s
    assert elab.run_once() == {'sent': 1, 'failed': 0}          # the lab's own: not Other Lab's
    sample = fake.live('Glycerol Stock')[g['code']]
    assert sample['meta']['Permit'] == 'IG 99-249' and sample['meta']['Biosafety level'] == 'I'
    # Settings changed, the token kept.
    _ok(lead.post('/api/elab/check', json={'url': 'https://uu.elabjournal.com', 'token': ''}))
    _ok(lead.put('/api/elab', json={'url': 'https://uu.elabjournal.com', 'kinds': ['glycerol', 'seed']}))
    assert elab.connection('Gardiner Lab').token == 'secret'
    _ok(lead.delete('/api/elab', json={}))
    assert not _ok(lead.get('/api/elab'))['connected']


def _lab_admin(world):
    conn = sqlite3.connect(world['paths']['suite'])
    conn.executescript("""
        CREATE TABLE lab_members (username TEXT, lab_id INTEGER, role TEXT, lab_admin INTEGER DEFAULT 0,
                                  joined_at TEXT, PRIMARY KEY (username, lab_id));
        INSERT INTO lab_members (username, lab_id, role, joined_at) SELECT username, lab_id, role, '1' FROM members;
        UPDATE lab_members SET lab_admin = 1 WHERE username = 'lead';
    """)
    conn.commit()
    conn.close()


def test_a_seed_lots_page_in_the_seed_bank_shows_it_in_elab_and_sends_it(as_user, world, fake, monkeypatch):
    monkeypatch.setenv('ELAB_LABS', 'Gardiner Lab')
    monkeypatch.setattr(elab.urllib.request, 'urlopen', fake)
    seed_bank(world, [('GARD-S-0001', 'Gardiner Lab', 'T3', 'hemizygous', 0, None)])
    ana = as_user('ana')
    assert _ok(ana.get('/api/elab/seed-lots/GARD-S-0001'))['elab']['state'] == 'waiting'
    nudged = []
    monkeypatch.setattr(elab, 'nudge', lambda: nudged.append(1))
    assert _ok(ana.post('/api/elab/seed-lots/GARD-S-0001/send')) == {'sent': True} and nudged     # any of the lab
    _run(fake)
    e = _ok(ana.get('/api/elab/seed-lots/GARD-S-0001'))['elab']
    sid = {x['altID']: i for i, x in fake.samples.items()}['GARD-S-0001']
    assert e['state'] == 'sent' and e['sample_id'] == sid
    # Archived in eLab: sent again from the lot's page.
    fake.samples[sid]['archived'] = True
    seed_bank(world, [('GARD-S-0001', 'Gardiner Lab', 'T3', 'homozygous', 0, None)])
    _run(fake)
    assert _ok(ana.get('/api/elab/seed-lots/GARD-S-0001'))['elab']['state'] == 'archived in eLab'
    assert _ok(ana.post('/api/elab/seed-lots/GARD-S-0001/send')) == {'restored': False}
    # Another lab's, or none: not shown.
    assert as_user('zoe').get('/api/elab/seed-lots/GARD-S-0001').status_code == 403
    assert ana.get('/api/elab/seed-lots/GARD-S-0099').status_code == 404
    assert _ok(as_user('boss').get('/api/elab/seed-lots/GARD-S-0001'))['elab'] is not None


def test_a_seed_lots_page_shows_nothing_when_its_lab_does_not_copy_them(as_user, world, monkeypatch):
    seed_bank(world, [('GARD-S-0001', 'Gardiner Lab', 'T3', '', 0, None)])
    assert _ok(as_user('ana').get('/api/elab/seed-lots/GARD-S-0001')) == {'elab': None}
    assert as_user('ana').post('/api/elab/seed-lots/GARD-S-0001/send').status_code == 400


def test_the_seed_banks_lists_show_how_far_the_labs_seed_lots_are_in_elab(as_user, world, fake, monkeypatch):
    monkeypatch.setenv('ELAB_LABS', 'Gardiner Lab')
    monkeypatch.setattr(elab.urllib.request, 'urlopen', fake)
    ana = as_user('ana')
    _ok(ana.post('/api/glycerol', json={'plasmid_name': 'pA'}), 201)
    seed_bank(world, [('GARD-S-0001', 'Gardiner Lab', 'T3', '', 0, None), ('GARD-S-0002', 'Gardiner Lab', 'T2', '', 0, None)])
    s = _ok(ana.get('/api/elab/seed-lots'))
    assert s['copies'] and s['waiting'] == 2 and s['synced'] == 0       # the seed lots only, not the glycerol stock
    nudged = []
    monkeypatch.setattr(elab, 'nudge', lambda: nudged.append(1))
    _ok(ana.post('/api/elab/seed-lots/sync', json={'lab': 'Gardiner Lab'}))      # any of the lab
    assert nudged
    assert as_user('ana').post('/api/elab/seed-lots/sync', json={'lab': 'Other Lab'}).status_code == 400
    _run(fake)
    assert _ok(ana.get('/api/elab/seed-lots'))['synced'] == 2


def test_the_seed_banks_lists_without_elab(as_user, world, monkeypatch):
    s = _ok(as_user('ana').get('/api/elab/seed-lots'))
    assert not s['connected'] and not s['copies'] and 'token' not in s
    assert as_user('ana').post('/api/elab/seed-lots/sync', json={}).status_code == 400


def _stopped_import(world, fake):
    """Two glycerol stocks in eLab, in Box 5; here, as a bringing over left them when it stopped before linking."""
    gs = _type(fake, 'Glycerol Stock')
    for n in (1, 2):
        fake.samples[700 + n] = {'sampleTypeID': gs, 'name': f'pStop{n}', 'altID': '', 'archived': False, 'owner': 'Pat Student',
                                 'description': '', 'note': '', 'storageLayerID': 12, 'position': 20 + n, 'meta': {}}
    with sqlite3.connect(world['paths']['stocks']) as conn:
        for n in (1, 2):
            conn.execute("INSERT INTO glycerol (id, code, lab, plasmid_name, elab_layer_id, elab_position, created_by) "
                         "VALUES (?, ?, 'Gardiner Lab', ?, '12', ?, 'lead')", (f'stop{n}', f'GL-G-090{n}', f'pStop{n}', str(20 + n)))


def test_a_bringing_over_that_stopped_is_linked_by_the_next_round(as_user, world, fake, monkeypatch):
    # Their places in eLab are taken by their own samples: linked to those, never made a second time.
    monkeypatch.setenv('ELAB_LABS', 'Gardiner Lab')
    monkeypatch.setattr(elab.urllib.request, 'urlopen', fake)
    _lab_admin(world)
    _stopped_import(world, fake)
    before = len(fake.samples)
    assert _run(fake) == {'sent': 2, 'failed': 0}
    assert len(fake.samples) == before
    links = elab._links('glycerol')
    assert (links['stop1']['sample_id'], links['stop2']['sample_id'], links['stop1']['error']) == (701, 702, None)
    got = {r['code']: r for r in _ok(as_user('lead').get('/api/glycerol'))['glycerol']}
    assert got['GL-G-0901']['created_by'] == 'Pat Student'
    assert _ok(as_user('lead').get('/api/elab/import?kind=glycerol&refresh=1'))['samples'] == []
    # Another of the name in another place is not taken for it.
    fake.samples[703] = {**fake.samples[701], 'position': 30}
    with sqlite3.connect(world['paths']['stocks']) as conn:
        conn.execute("INSERT INTO glycerol (id, code, lab, plasmid_name, elab_layer_id, elab_position) "
                     "VALUES ('stop3', 'GL-G-0903', 'Gardiner Lab', 'pStop1', '12', '22')")
    assert _run(fake)['failed'] == 1
    assert 'no free space' in elab._links('glycerol')['stop3']['error']


def test_bringing_over_again_links_what_a_stopped_one_left(as_user, world, fake, monkeypatch):
    monkeypatch.setenv('ELAB_LABS', 'Gardiner Lab')
    monkeypatch.setattr(elab.urllib.request, 'urlopen', fake)
    _lab_admin(world)
    _stopped_import(world, fake)
    lead = as_user('lead')
    assert len(_ok(lead.get('/api/elab/import?kind=glycerol'))['samples']) == 2
    res = _ok(lead.post('/api/elab/import/glycerol', json={'ids': [701, 702]}), 201)
    assert (res['made'], res['linked']) == (0, 2)
    got = _ok(lead.get('/api/glycerol'))['glycerol']
    assert sorted(r['code'] for r in got) == ['GL-G-0901', 'GL-G-0902'] and {r['created_by'] for r in got} == {'Pat Student'}
    fake.calls.clear()
    assert _run(fake) == {'sent': 0, 'failed': 0} and not any(m == 'POST' for m, _ in fake.calls)


def test_one_brought_over_is_never_made_again_in_elab(as_user, world, fake, monkeypatch):
    # Brought over, then its link lost (the bringing over stopped between): linked again, not made.
    monkeypatch.setenv('ELAB_LABS', 'Gardiner Lab')
    monkeypatch.setattr(elab.urllib.request, 'urlopen', fake)
    _lab_admin(world)
    gs = _type(fake, 'Glycerol Stock')
    fake.samples[801] = {'sampleTypeID': gs, 'name': 'pLoose', 'altID': '', 'archived': False, 'owner': 'Pat Student',
                         'description': '', 'note': '', 'storageLayerID': None, 'position': None, 'meta': {}}
    _ok(as_user('lead').post('/api/elab/import/glycerol', json={'ids': [801]}), 201)
    with sqlite3.connect(world['paths']['stocks']) as conn:
        conn.execute("DELETE FROM elab_links")
    fake.calls.clear()
    assert _run(fake)['failed'] == 0 and not any(m == 'POST' for m, _ in fake.calls)
    assert [l['sample_id'] for l in elab._links('glycerol').values()] == [801]
