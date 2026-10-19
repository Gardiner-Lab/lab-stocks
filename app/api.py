"""Lab Stocks' JSON API, under /api."""

from functools import wraps
from urllib.parse import quote

from flask import Blueprint, Response, jsonify, request

from app import attachments, oligo, orders, people, records, sources

api = Blueprint('api', __name__)
PLURAL = {'glycerol': 'glycerol', 'primers': 'primer', 'chemicals': 'chemical', 'antibodies': 'antibody'}


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
                    'antibody_types': records.ANTIBODY_TYPES,
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
    return jsonify({collection: records.list_records(person, kind, request.args.get('q', ''),
                                                     request.args.get('plasmid', ''))})


@api.post('/<collection>')
@signed_in
def create_stock(person, collection):
    kind = _kind(collection)
    record_id, ordered = records.create_noting(person, kind, _body())
    return jsonify({'record': records.detail(person, kind, record_id), 'ordered': ordered}), 201


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
    shown = (found['inline'] or found['preview']) and request.args.get('download') is None
    response = Response(found['data'], mimetype=attachments.sent_as(found['mime']))
    response.headers['Content-Disposition'] = (f"{'inline' if shown else 'attachment'}; "
                                               f"filename*=UTF-8''{quote(found['filename'])}")
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = ("default-src 'none'" if found['preview'] and shown
                                                    else "default-src 'none'; sandbox")
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
