"""Lab Stocks' JSON API, under /api."""

import re
from functools import wraps
from urllib.parse import quote

from flask import Blueprint, Response, jsonify, request

from app import attachments, chairs, elab, oligo, orders, people, records, sources, viewer
from app.db import connect

api = Blueprint('api', __name__)
PLURAL = {'glycerol': 'glycerol', 'primers': 'primer', 'chemicals': 'chemical', 'antibodies': 'antibody', 'material': 'material'}


def signed_in(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        person = people.current()
        if person is None:
            return jsonify({'error': 'Sign in through the lab suite first'}), 401
        try:
            return view(person, *args, **kwargs)
        except records.Forbidden as exc:
            return jsonify({'error': str(exc)}), 403
        except records.NotFound as exc:
            return jsonify({'error': str(exc)}), 404
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
    return wrapper


def _body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _kind(collection: str) -> str:
    if collection not in PLURAL:
        raise records.NotFound('No such kind of stock')
    return PLURAL[collection]


@api.get('/me')
@signed_in
def me(person):
    return jsonify({'person': person.to_dict(), 'lab': records.lab_info(person),
                    'status': records.STATUS, 'chemical_status': records.CHEMICAL_STATUS,
                    'antibody_types': records.ANTIBODY_TYPES, 'tissues': records.TISSUES,
                    'mods': {'5': records.MODS_5, '3': records.MODS_3},
                    'glycerol': {'biosafety': records.BIOSAFETY, 'host_systems': records.HOST_SYSTEMS,
                                 'yes_no': records.YES_NO, 'harmful': records.HARMFUL, 'permits': records.PERMITS,
                                 'plant_markers': records.PLANT_MARKERS, 'yeast_markers': records.YEAST_MARKERS},
                    'directions': records.DIRECTIONS,
                    'orders': {'handles': orders.handles(person), 'waiting': orders.waiting(person),
                               'categories': orders.CATEGORIES, 'status': orders.STATUS}})


@api.get('/lab')
@signed_in
def get_lab(person):
    return jsonify(records.lab_info(person, request.args.get('lab')))


@api.put('/lab')
@signed_in
def put_lab(person):
    return jsonify(records.set_lab_code(person, str(_body().get('code') or ''), _body().get('lab')))


@api.get('/search')
@signed_in
def search(person):
    return jsonify({'results': records.search(person, request.args.get('q', ''))})


@api.get('/primers/sequences')
@signed_in
def primer_sequences(person):
    """The lab's primers in stock with their sequences, for the editor to find where they bind."""
    return jsonify({'primers': records.all_primers(person)})


@api.get('/oligo')
@signed_in
def describe_oligo(person):
    return jsonify(oligo.describe(oligo.clean(request.args.get('sequence', ''))))


# --- the copy in eLabJournal -----------------------------------------------------

@api.get('/chair')
@signed_in
def get_chair(person):
    """The lab's chair group (chosen by an administrator on the suite's dashboard), with its labs."""
    return jsonify(chairs.info(person, records.lab_of(person, request.args.get('lab'))))


@api.get('/elab')
@signed_in
def elab_status(person):
    """Where the lab's stocks are copied in eLab, and how far; whether this person may change it."""
    lab = records.lab_of(person, request.args.get('lab'))
    found = elab.status(lab)
    found['can_set'] = person.administers(lab)
    return jsonify(found)


def _elab_lab(person) -> str:
    lab = records.lab_of(person, _body().get('lab') or request.args.get('lab'), strict=True)
    if not person.administers(lab):
        raise records.Forbidden("Only the lab's lab admin connects its stocks to eLab")
    return lab


@api.post('/elab/check')
@signed_in
def elab_check(person):
    """Tries a token made in eLab: the sample types it sees there, and their permit and biosafety options."""
    lab = _elab_lab(person)
    url, token = _body().get('url'), str(_body().get('token') or '').strip()
    saved = elab.connection(lab)
    if not token and saved and saved.source == 'lab' and saved.url == elab.clean_url(url):
        token = saved.token             # settings changed, the token kept
    return jsonify(elab.check(url, token))


@api.put('/elab')
@signed_in
def elab_connect(person):
    lab = _elab_lab(person)
    elab.save(lab, person.username, _body())
    return jsonify({**elab.status(lab), 'can_set': True})


@api.delete('/elab')
@signed_in
def elab_disconnect(person):
    lab = _elab_lab(person)
    elab.remove(lab)
    return jsonify({**elab.status(lab), 'can_set': True})


@api.get('/elab/locations')
@signed_in
def elab_locations(person):
    """The storage locations of the lab's eLab group, for a stock's form."""
    lab = records.lab_of(person, request.args.get('lab'))
    try:
        return jsonify(elab.locations(lab, refresh=request.args.get('refresh') == '1'))
    except elab.ElabError as exc:
        raise ValueError(f'eLab could not be asked for its storage: {exc}') from exc


@api.post('/elab/locations')
@signed_in
def elab_add_location(person):
    """Adds a storage location in eLab, from a stock's form: anyone in the lab."""
    lab = records.lab_of(person, _body().get('lab'), strict=True)
    try:
        return jsonify({'location': elab.add_location(lab, _body().get('parent'), _body().get('name'), _body().get('kind'))}), 201
    except elab.ElabError as exc:
        raise ValueError(f'eLab did not add it: {exc}') from exc


def _elab_admin_lab(person) -> str:
    lab = records.lab_of(person, _body().get('lab') or request.args.get('lab'), strict=True)
    if not person.administers(lab):
        raise records.Forbidden("Only the lab's lab admin brings stocks over from eLab")
    return lab


@api.get('/elab/import')
@signed_in
def elab_import_list(person):
    """
    eLab's samples of the kind not yet here, to choose what to bring over, and everyone owning any there:
    owners [owner, not yet here, already here], also those with nothing left to bring.
    """
    lab = _elab_admin_lab(person)
    found = elab.candidates(lab, request.args.get('kind', ''), refresh=request.args.get('refresh') == '1', every=True)
    elab.owners_as_makers(lab, request.args.get('kind', ''))      # as eLab has them now: from the list just fetched
    owners: dict = {}
    for s in found:
        counts = owners.setdefault(s['owner'], [0, 0])
        counts[1 if s['here'] else 0] += 1
    return jsonify({'samples': [{k: v for k, v in s.items() if k not in ('meta', 'here')} for s in found if not s['here']],
                    'owners': sorted(([o, *n] for o, n in owners.items()), key=lambda o: (-o[1], -o[2])),
                    **_lab_people(lab)})


def _lab_people(lab: str) -> dict:
    """The lab's own people in eLab, {owner: account here or ''}; who gets the rest; the lab's accounts, to choose from."""
    gone = people.archived()
    return {'people': {name: username for name, username in elab.lab_people(lab).values()},
            'others_by': elab.others_by(),
            'accounts': sorted((u for u, m in people.memberships().items()
                                if u not in gone and any((l.get('lab') or '').casefold() == lab.casefold() for l in m['labs'])),
                               key=str.casefold)}


@api.get('/elab/people')
@signed_in
def elab_people(person):
    return jsonify(_lab_people(_elab_admin_lab(person)))


@api.put('/elab/people')
@signed_in
def elab_set_people(person):
    """
    Chooses the lab's own people in eLab ({owner in eLab: their account here, or ''}): what they own there is
    credited to them, the rest to the administrator, each keeping its owner. Credited again at once.
    """
    lab = _elab_admin_lab(person)
    chosen = _body().get('people')
    if not isinstance(chosen, dict):
        raise ValueError('Give the lab\'s people in eLab')
    known = set(_lab_people(lab)['accounts'])
    wrong = sorted({str(u) for u in chosen.values() if u and str(u) not in known})
    if wrong:
        raise ValueError(f'Not an account in {lab}: {", ".join(wrong)}')
    elab.set_lab_people(lab, person.username, chosen)
    with connect() as conn:         # the kinds anything was brought over of, for the lab
        kinds = [k for k in elab.TABLES if conn.execute(
            f'SELECT 1 FROM elab_links l JOIN {elab.TABLES[k]} t ON t.id = l.record_id WHERE l.record_kind = ? '
            'AND l.elab_name IS NOT NULL AND t.lab = ? LIMIT 1', (k, lab)).fetchone()]
    credited = sum(elab.owners_as_makers(lab, kind, refresh=True) for kind in kinds) if elab.connection(lab) else 0
    return jsonify({**_lab_people(lab), 'credited': credited})


@api.post('/elab/import/material')
@signed_in
def elab_import_material(person):
    """Brings these Plant Material samples over from eLab as plant material, each linked to its sample."""
    lab = _elab_admin_lab(person)
    wanted = {int(i) for i in (_body().get('ids') or []) if str(i).isdigit()}
    chosen = [s for s in elab.candidates(lab, 'material') if s['id'] in wanted]
    if not chosen:
        raise ValueError('Choose the samples to bring over')
    tissues = ('leaf', 'flower', 'petal', 'root', 'stem', 'seedling', 'seed', 'fruit', 'callus', 'whole plant')
    elab.owners_as_makers(lab, 'material')
    healed, chosen = _here_already(lab, 'material', chosen)
    items = []
    for s in chosen:
        said = f"{s['description']} {s['note']}".lower()
        by = re.search(r'collected by ([^,.;]+)', s['note'], re.I)
        items.append({'name': s['name'], 'description': s['description'],
                      'tissue': next((t for t in tissues if t in said), ''),
                      'collected_by': by.group(1).strip() if by else '',
                      'notes': s['note'], 'elab_layer_id': str(s['layer'] or ''), 'elab_layer_path': s['path'],
                      'elab_position': str(s['position'] or '')})
    made, linked = [], 0
    with elab.paused():         # made and linked a few at a time, before any round can send them as new
        linked += elab.adopt(lab, 'material', healed)
        for start in range(0, len(items), BATCH):
            some = records.create_material(person, items[start:start + BATCH], {}, lab,
                                           owners=[s['owner'] for s in chosen[start:start + BATCH]])
            linked += elab.adopt(lab, 'material', [(rid, s['id'], s['name']) for rid, s in zip(some, chosen[start:start + BATCH])])
            made += some
    return jsonify({'made': len(made), 'linked': linked}), 201


BATCH = 25      # brought over from eLab and linked at once: few enough that a stop between leaves little unlinked


def _here_already(lab: str, kind: str, chosen: list):
    """
    Of the samples chosen to bring over, those already here unlinked (an earlier bringing over stopped before
    linking them): [(record id, sample id, name)], to link, made by the sample's owner; and the rest, to make.
    """
    waiting = elab.unlinked(lab, kind)
    healed, rest = [], []
    for s in chosen:
        record_id = waiting.pop(elab.place_of(s), None)
        if record_id:
            healed.append((record_id, s['id'], s['name']))
            with connect() as conn:
                elab.set_maker(conn, kind, record_id, s['owner'])
        else:
            rest.append(s)
    return healed, rest


def _choice(value, allowed) -> str:
    """One of these, as written here, for a value from eLab (the first, of several); else none."""
    first = str(value or '').split(',')[0].strip().casefold()
    return next((a for a in allowed if a and a.casefold() == first), '')


@api.post('/elab/import/glycerol')
@signed_in
def elab_import_glycerol(person):
    """
    Brings these Glycerol Stock samples over from eLab as glycerol stocks, each linked to its sample: its
    fields as eLab has them, its place in eLab's storage, and linked to the plasmid of its name in the
    Plasmid Editor, when there is exactly one this person may open.
    """
    lab = _elab_admin_lab(person)
    wanted = {int(i) for i in (_body().get('ids') or []) if str(i).isdigit()}
    chosen = [s for s in elab.candidates(lab, 'glycerol') if s['id'] in wanted]
    if not chosen:
        raise ValueError('Choose the samples to bring over')
    elab.owners_as_makers(lab, 'glycerol')
    healed, chosen = _here_already(lab, 'glycerol', chosen)
    data = []
    for s in chosen:
        meta = s['meta']
        harm = next((v for k, v in meta.items() if k.startswith('Remarks on harmful effects')), '')
        system = str(meta.get('Host system') or '').split(',')[0].strip()
        named = [p for p in sources.plasmids(person, s['name'], limit=50) if p['name'].strip().casefold() == s['name'].casefold()]
        data.append({
            'lab': lab, 'plasmid_name': s['name'], 'plasmid_id': named[0]['id'] if len(named) == 1 else '',
            'host': meta.get('Name of host strain', ''), 'selection': meta.get('Bacterial Markers', ''),
            'permit': meta.get('Permit', ''), 'biosafety': _choice(meta.get('Biosafety level'), records.BIOSAFETY),
            'host_system': 'other' if 'other' in system.casefold() else _choice(system, records.HOST_SYSTEMS),
            'plant_markers': meta.get('Plant Markers', ''), 'yeast_markers': meta.get('Yeast Markers', ''),
            'inserts': _choice(meta.get('Insert(s)?'), records.YES_NO), 'gene_ids': meta.get('geneID(s)', ''),
            'donor': meta.get('Donororganism(s)', ''), 'harmful': _choice(meta.get('Harmful gene product?'), records.HARMFUL),
            'harmful_notes': harm, 'made_on': s['created'] or None,
            'notes': '\n'.join(filter(None, [meta.get('Remarks', ''), s['description'], s['note']])),
            'elab_layer_id': str(s['layer'] or ''), 'elab_layer_path': s['path'], 'elab_position': str(s['position'] or '')})
    made, linked = [], 0
    with elab.paused():         # made and linked a few at a time, before any round can send them as new
        linked += elab.adopt(lab, 'glycerol', healed)
        for start in range(0, len(data), BATCH):
            some = [records.create(person, 'glycerol', d, owner=s['owner'])
                    for d, s in zip(data[start:start + BATCH], chosen[start:start + BATCH])]
            linked += elab.adopt(lab, 'glycerol', [(rid, s['id'], s['name']) for rid, s in zip(some, chosen[start:start + BATCH])])
            made += some
    return jsonify({'made': len(made), 'linked': linked,
                    'plasmids': sum(1 for d in data if d['plasmid_id'])}), 201


@api.post('/elab/adopt')
@signed_in
def elab_adopt(person):
    """Links seed lots just made in the Seed Bank from eLab's seed samples to those samples: [{code, sample_id, name}]."""
    lab = _elab_admin_lab(person)
    pairs = [p for p in (_body().get('pairs') or []) if isinstance(p, dict)]
    ids = elab.seed_lot_ids([str(p.get('code') or '') for p in pairs])
    linked = elab.adopt(lab, 'seed', [(ids[p['code']], int(p['sample_id']), str(p.get('name') or ''))
                                      for p in pairs if p.get('code') in ids and str(p.get('sample_id')).isdigit()])
    return jsonify({'linked': linked})


@api.post('/<collection>/<ident>/elab-again')
@signed_in
def send_to_elab_again(person, collection, ident):
    """One whose sample was archived in eLab, sent again: to it if restored there, else as a new sample."""
    kind = _kind(collection)
    with connect() as conn:
        row = records.changeable(conn, person, kind, ident)
    return jsonify(elab.send_again(kind, row['lab'], row['id']))


def _seed_lot(person, code: str) -> dict:
    """A seed lot of the Seed Bank (read only), of one of this person's labs (an administrator: any)."""
    lot = elab.seed_lot(code)
    if lot is None:
        raise records.NotFound('No such seed lot')
    if not person.is_admin and lot['lab'].casefold() not in {n.casefold() for n in records.labs_of(person)}:
        raise records.Forbidden("Only the lot's lab sees it in eLab")
    return lot


@api.get('/elab/seed-lots')
@signed_in
def seed_lots_elab(person):
    """How far the lab's Seed Bank lots are copied to eLab, for the Seed Bank's lists; copies: whether it copies them."""
    lab = records.lab_of(person, request.args.get('lab'))
    found = elab.status(lab, only='seed')
    found['copies'] = 'seed' in found.get('kinds', [])
    return jsonify(found)


@api.post('/elab/seed-lots/sync')
@signed_in
def sync_seed_lots(person):
    """The lab's seed lots sent now, not at the next round: anyone of the lab may ask (it only wakes the round)."""
    lab = records.lab_of(person, _body().get('lab'), strict=True)
    c = elab.connection(lab)
    if c is None or 'seed' not in c.kinds:
        raise ValueError('The lab does not copy its seed lots to eLab')
    elab.nudge()
    return jsonify({'ok': True})


@api.get('/elab/seed-lots/<code>')
@signed_in
def seed_lot_elab(person, code):
    """Where a Seed Bank lot is in eLab, for its page there: null when its lab does not copy seed lots."""
    lot = _seed_lot(person, code)
    return jsonify({'elab': elab.record_state('seed', lot['lab'], lot['id'])})


@api.post('/elab/seed-lots/<code>/send')
@signed_in
def send_seed_lot(person, code):
    """A Seed Bank lot sent now (archived in eLab: sent again, to its sample if restored there, else as a new one)."""
    lot = _seed_lot(person, code)
    state = elab.record_state('seed', lot['lab'], lot['id'])
    if state is None:
        raise ValueError("The lot's lab does not copy its seed lots to eLab")
    if state['state'] == 'archived in eLab':
        return jsonify(elab.send_again('seed', lot['lab'], lot['id']))
    elab.nudge()
    return jsonify({'sent': True})


@api.post('/elab/sync')
@signed_in
def elab_sync(person):
    _elab_lab(person)
    elab.nudge()
    return jsonify({'ok': True})


@api.post('/elab/pull')
@signed_in
def elab_pull(person):
    """What was changed in eLab, taken here: for the lab admin, when asked (eLab is right)."""
    lab = _elab_admin_lab(person)
    return jsonify(elab.update_from_elab(lab, person.username))


# --- the order list ---------------------------------------------------------------

@api.get('/orders')
@signed_in
def list_orders(person):
    return jsonify({'orders': orders.list_orders(person, request.args.get('status', ''), request.args.get('q', '')),
                    'handles': orders.handles(person), 'waiting': orders.waiting(person)})


@api.get('/orders/waiting')
@signed_in
def orders_waiting(person):
    return jsonify({'waiting': orders.waiting(person)})


@api.get('/orders.csv')
@signed_in
def orders_csv(person):
    response = Response(orders.as_csv(person, request.args.get('status', ''), request.args.get('q', '')),
                        mimetype='text/csv')
    response.headers['Content-Disposition'] = 'attachment; filename="orders.csv"'
    return response


@api.post('/orders')
@signed_in
def create_order(person):
    made = orders.create(person, _body())
    return jsonify(made), 200 if made['already'] else 201


@api.post('/orders/many')
@signed_in
def create_orders(person):
    return jsonify(orders.create_many(person, _body())), 201


@api.get('/orders/<order_id>')
@signed_in
def get_order(person, order_id):
    return jsonify({'order': orders.detail(person, order_id)})


@api.put('/orders/<order_id>')
@signed_in
def update_order(person, order_id):
    return jsonify({'order': orders.update(person, order_id, _body())})


@api.get('/<collection>')
@signed_in
def list_stock(person, collection):
    kind = _kind(collection)
    rows = records.list_records(person, kind, request.args.get('q', ''), request.args.get('plasmid', ''))
    with connect() as conn:
        ordered = orders.open_codes(conn)
    for r in rows:
        r['on_order'] = r['code'] in ordered
    return jsonify({collection: rows})


@api.post('/<collection>')
@signed_in
def create_stock(person, collection):
    kind = _kind(collection)
    record_id, ordered = records.create_noting(person, kind, _body())
    return jsonify({'record': records.detail(person, kind, record_id), 'ordered': ordered}), 201


@api.post('/material/many')
@signed_in
def create_material(person):
    """Several tubes of plant material at once: a box of them, named in a row or pasted as a list."""
    body = _body()
    ids = records.create_material(person, body.get('items') or [], body.get('shared') or {}, body.get('lab'))
    return jsonify({'material': [records.detail(person, 'material', i) for i in ids]}), 201


@api.post('/primers/many')
@signed_in
def create_primers(person):
    """Several primers at once, as the editor's primer design gives them."""
    made = []
    for p in (_body().get('primers') or [])[:50]:
        made.append(records.detail(person, 'primer', records.create(person, 'primer', p)))
    return jsonify({'primers': made}), 201


@api.get('/<collection>/<ident>')
@signed_in
def get_stock(person, collection, ident):
    record = records.detail(person, _kind(collection), ident)
    record['mentions'] = sources.notebook_mentions(person, record['code'])
    # Where it is in eLab, with a link to its sample there: for the lab's own.
    record['elab'] = elab.record_state(record['kind'], record['lab'], record['id']) if record['mine'] else None
    return jsonify({'record': record})


@api.put('/<collection>/<ident>')
@signed_in
def update_stock(person, collection, ident):
    kind = _kind(collection)
    ordered = records.update(person, kind, ident, _body())
    return jsonify({'record': records.detail(person, kind, ident), 'ordered': ordered})


@api.delete('/<collection>/<ident>')
@signed_in
def delete_stock(person, collection, ident):
    records.delete(person, _kind(collection), ident)
    return jsonify({'ok': True})


@api.post('/<collection>/<ident>/attachments')
@signed_in
def add_attachments(person, collection, ident):
    files = [(f.filename or 'file', f.read(attachments.MAX_BYTES + 1)) for f in request.files.getlist('file')]
    # A chemical's safety data sheet is sent captioned SDS.
    caption = records.SDS if request.form.get('caption') == records.SDS else ''
    return jsonify({'attachments': attachments.add(person, _kind(collection), ident, files, caption)}), 201


@api.get('/attachments/<att_id>')
@signed_in
def get_attachment(person, att_id):
    found = attachments.fetch(person, att_id)
    if request.args.get('view') is not None:
        viewed = _viewed(found)
        if viewed is not None:
            return viewed
    shown = (found['inline'] or found['preview']) and request.args.get('download') is None
    response = Response(found['data'], mimetype=attachments.sent_as(found['mime']))
    response.headers['Content-Disposition'] = (f"{'inline' if shown else 'attachment'}; "
                                               f"filename*=UTF-8''{quote(found['filename'])}")
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = ("default-src 'none'" if found['preview'] and shown
                                                    else "default-src 'none'; sandbox")
    response.headers['Cache-Control'] = 'private, max-age=86400'
    return response


def _viewed(found):
    """A file shown in the browser: an office file as a PDF, a text file as plain text; None to send it as it is."""
    name = quote(found['filename'])
    text = viewer.as_text(found['kind'], found['data'])
    if text is not None:
        response = Response(text, mimetype='text/plain')
        response.headers['Content-Security-Policy'] = "default-src 'none'; sandbox"
    elif viewer.converted(found['kind']):
        try:
            pdf = viewer.as_pdf(found['sha256'], found['filename'], found['mime'], found['data'])
        except viewer.ViewerError as exc:
            return Response(f"{found['filename']} cannot be shown here: {exc}. Download it to open it in its program.",
                            status=502, mimetype='text/plain')
        response = Response(pdf, mimetype='application/pdf')
        response.headers['Content-Security-Policy'] = "default-src 'none'"
        name += '.pdf'
    else:
        return None
    response.headers['Content-Disposition'] = f"inline; filename*=UTF-8''{name}"
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'private, max-age=86400'
    return response


@api.delete('/attachments/<att_id>')
@signed_in
def remove_attachment(person, att_id):
    attachments.remove(person, att_id)
    return jsonify({'ok': True})


@api.get('/plasmids')
@signed_in
def find_plasmids(person):
    return jsonify({'plasmids': sources.plasmids(person, request.args.get('q', ''))})
