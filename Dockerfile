FROM python:3.12-slim

WORKDIR /app

# The same user id as the other tools, as the suite's volumes expect.
RUN useradd -m -u 1000 appuser && mkdir -p /stocks && chown -R appuser:appuser /app /stocks

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn==23.0.0

COPY app/ ./app/

USER appuser

EXPOSE 5006

ENV PYTHONUNBUFFERED=1 \
    STOCKS_DATABASE_PATH=/stocks/stocks.db \
    MOCLO_DATABASE_PATH=/moclo/moclo.db \
    EDITOR_DATABASE_PATH=/editor/plasmid_editor.db \
    NOTEBOOK_DATABASE_PATH=/notebook/notebook.db \
    SEEDS_DATABASE_PATH=/seeds/seeds.db \
    SUITE_DATABASE_PATH=/suite/suite.db \
    URL_PREFIX=/stocks \
    PORT=5006

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5006/stocks/health')" || exit 1

# One worker with threads keeps SQLite writes simple and ordered.
CMD ["gunicorn", "--bind", "0.0.0.0:5006", "--workers", "1", "--threads", "4", "--timeout", "120", "app.main:app"]
