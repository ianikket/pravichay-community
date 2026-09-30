"""Bounded, short-lived graphs. No database, saved cases, or disk cache."""

import json
import secrets
import threading
import time
from pathlib import Path

from .explorer import outgoing_connections

INITIAL_LIMIT = 3
EXPANSION_LIMIT = 2
MAX_NODES = 60
MAX_EDGES = 90
MAX_GRAPHS = 50
GRAPH_TTL_SECONDS = 900
SAMPLE_PATH = Path(__file__).resolve().parent.parent / "samples" / "transactions.json"


class TraceError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class TraceStore:
    def __init__(self, fetch):
        self.fetch = fetch
        self.graphs = {}
        self.lock = threading.Lock()

    def _prune(self):
        now = time.monotonic()
        self.graphs = {key: graph for key, graph in self.graphs.items()
                       if now - graph["created"] < GRAPH_TTL_SECONDS}

    def _connections(self, address, limit, sample):
        if sample:
            with SAMPLE_PATH.open(encoding="utf-8") as handle:
                transactions = json.load(handle)["transactions"].get(address, [])
        else:
            transactions = self.fetch(address)
        return outgoing_connections(address, transactions, limit, sample=sample)

    def _apply(self, graph, address, limit):
        if address in graph["expanded"]:
            raise TraceError("This address has already been expanded.", 409)
        if address not in graph["nodes"]:
            raise TraceError("Choose an address already visible in this graph.")
        if len(graph["nodes"]) >= MAX_NODES or len(graph["edges"]) >= MAX_EDGES:
            raise TraceError("This graph has reached the community size limit.", 409)
        connections, more = self._connections(address, limit, graph["sample"])
        for edge in connections:
            if (len(graph["edges"]) >= MAX_EDGES or
                    (edge["target"] not in graph["nodes"] and len(graph["nodes"]) >= MAX_NODES)):
                more = True
                break
            graph["nodes"].setdefault(edge["target"], graph["nodes"][address] + 1)
            graph["edges"].append(edge)
        graph["expanded"].add(address)
        graph["limited"] = more

    def start(self, address, sample=False):
        # Admission is serialized; failed starts consume no graph slots.
        with self.lock:
            self._prune()
            if len(self.graphs) >= MAX_GRAPHS:
                raise TraceError("Too many active graphs. Please try again later.", 503)
            graph = {"root": address, "sample": sample, "created": time.monotonic(),
                     "nodes": {address: 0}, "edges": [], "expanded": set(),
                     "limited": False}
            self._apply(graph, address, INITIAL_LIMIT)
            token = secrets.token_urlsafe(24)
            self.graphs[token] = graph
            return self._response(token, graph)

    def expand(self, token, address):
        with self.lock:
            self._prune()
            graph = self.graphs.get(token)
            if graph is None:
                raise TraceError("This graph expired or the server restarted. Start a new trace.", 404)
            self._apply(graph, address, EXPANSION_LIMIT)
            return self._response(token, graph)

    @staticmethod
    def _response(token, graph):
        at_limit = len(graph["nodes"]) >= MAX_NODES or len(graph["edges"]) >= MAX_EDGES
        return {"trace_id": token, "root": graph["root"],
                "source": "synthetic" if graph["sample"] else "blockstream",
                "nodes": [{"id": address, "depth": depth,
                           "expanded": address in graph["expanded"],
                           "expandable": address not in graph["expanded"] and not at_limit}
                          for address, depth in graph["nodes"].items()],
                "edges": list(graph["edges"]), "limited": graph["limited"],
                "at_limit": at_limit}
