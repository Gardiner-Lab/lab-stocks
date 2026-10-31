"""
Lab Stocks: Trellis Tools' glycerol stocks, primers, chemicals and antibodies, and the order list.

Glycerol stocks, numbered per lab and linked to the plasmid they hold (made
when a plasmid is confirmed by sequencing in the Plasmid Editor); primers with
their sequences, Tm and where the tube is; storage, labels with QR codes, and
links from the notebook.
"""

import os

from flask import Flask, redirect, render_template, request

APP_VERSION = '0.14.0'
SOFOS_URL = ('https://uusofos.itis.software/default.aspx#ViewID=BOInformationPortal_ListView'
             '&ObjectClassName=GROS.Module.ExtensionModules.Intranet.BOInformationPortal')
CHEMWATCH_URL = 'https://jr.chemwatch.net/chemwatch.web/'


class PrefixMiddleware:
    """Mount the app under URL_PREFIX (/stocks), as the suite's proxy passes the full path."""

    def __init__(self, wsgi_app, prefix: str):
        self.wsgi_app = wsgi_app
        self.prefix = '/' + prefix.strip('/')

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        if path == self.prefix or path.startswith(self.prefix + '/'):
            environ['SCRIPT_NAME'] = environ.get('SCRIPT_NAME', '') + self.prefix
            environ['PATH_INFO'] = path[len(self.prefix):] or '/'
        return self.wsgi_app(environ, start_response)


def create_app() -> Flask:
    from app import db, elab, people
    from app.api import api

    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024
    db.initialize(os.environ.get('STOCKS_DATABASE_PATH', '/stocks/stocks.db'))
    app.register_blueprint(api, url_prefix='/api')
    # Copies the stocks to eLabJournal's inventory, when ELAB_URL and ELAB_TOKEN are set.
    elab.start()

    def links() -> dict:
        return {
            'suite_home': os.environ.get('SUITE_HOME_URL', '/'),
            'editor': os.environ.get('EDITOR_URL', '/editor').rstrip('/'),
            'notebook': os.environ.get('NOTEBOOK_URL', '/notebook').rstrip('/'),
            'seeds': os.environ.get('SEEDS_URL', '/seeds').rstrip('/'),
            'logout': os.environ.get('SUITE_LOGOUT_URL', '/account/logout'),
            # Where phones reach the suite, for the codes on labels; unset, the
            # address the label page was opened at.
            'public': people.public_url(),
            # Chemical safety: the university's hazardous substances register, and Chemwatch.
            'sofos': os.environ.get('SOFOS_URL', SOFOS_URL),
            'chemwatch': os.environ.get('CHEMWATCH_URL', CHEMWATCH_URL),
        }

    def page(template: str):
        person = people.current()
        if person is None:
            login = os.environ.get('SUITE_LOGIN_URL', '/account/login')
            return redirect(f'{login}?next={request.script_root}/')
        return render_template(template, version=APP_VERSION, person=person, links=links())

    @app.route('/')
    def stocks_page():
        return page('stocks.html')

    @app.route('/labels')
    def labels_page():
        return page('labels.html')

    @app.route('/about')
    def about_page():
        return render_template('about.html', version=APP_VERSION, links=links())

    @app.route('/help')
    def help_page():
        return render_template('help.html', version=APP_VERSION, links=links())

    @app.route('/health')
    def health():
        return {'status': 'healthy', 'version': APP_VERSION}

    prefix = os.environ.get('URL_PREFIX', '').strip('/')
    if prefix:
        app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix)
    return app


app = create_app() if os.environ.get('STOCKS_NO_APP') != '1' else None

if __name__ == '__main__':
    create_app().run(host='0.0.0.0', port=int(os.environ.get('PORT', 5006)), debug=True)
