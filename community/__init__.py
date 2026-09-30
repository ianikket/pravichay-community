"""The entire community HTTP surface: home, start trace, expand trace."""

from pathlib import Path

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from .explorer import ExplorerError, fetch_transactions, plausible_address
from .tracing import TraceError, TraceStore


def create_app(test_config=None, fetch=None):
    root = Path(__file__).resolve().parent.parent
    app = Flask(__name__, template_folder=str(root / "templates"),
                static_folder=str(root / "static"))
    app.config.update(MAX_CONTENT_LENGTH=2048)
    if test_config:
        app.config.update(test_config)
    store = TraceStore(fetch or fetch_transactions)
    app.extensions["traces"] = store

    def body(allowed):
        data = request.get_json()
        if not isinstance(data, dict) or set(data) - allowed:
            raise TraceError("Unexpected request fields.")
        return data

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.post("/api/trace")
    def trace():
        data = body({"address", "sample"})
        sample = data.get("sample", False)
        if type(sample) is not bool:
            raise TraceError("sample must be true or false.")
        address = data.get("address", "")
        if not isinstance(address, str):
            raise TraceError("Enter a Bitcoin mainnet address.")
        address = address.strip()
        if sample:
            address = "demo-root"
        elif not plausible_address(address):
            raise TraceError("Enter a Bitcoin mainnet address (1, 3, or bc1).")
        return jsonify(store.start(address, sample))

    @app.post("/api/expand")
    def expand():
        data = body({"trace_id", "address"})
        token, address = data.get("trace_id"), data.get("address")
        if not isinstance(token, str) or len(token) > 64 or not isinstance(address, str) or len(address) > 90:
            raise TraceError("A trace ID and visible address are required.")
        return jsonify(store.expand(token, address))

    @app.errorhandler(TraceError)
    def trace_error(exc):
        return jsonify(error=str(exc)), exc.status

    @app.errorhandler(ExplorerError)
    def explorer_error(exc):
        return jsonify(error=str(exc)), 502

    @app.errorhandler(HTTPException)
    def http_error(exc):
        return jsonify(error=exc.name), exc.code

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self'; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        return response

    return app
