"""Offline regression checks; no real wallets or remote API calls."""

import copy
import unittest
from unittest.mock import Mock, patch

from community import create_app
from community.explorer import ExplorerError, fetch_transactions, outgoing_connections
from community.tracing import GRAPH_TTL_SECONDS, MAX_NODES

# Syntax-only test strings, not observed wallets or ownership claims.
ADDRESS = "1" + "A" * 26
RECEIVER = "1" + "B" * 26


def transaction(receiver=RECEIVER, value=123):
    return {"txid": "a" * 64, "vin": [{"prevout": {"scriptpubkey_address": ADDRESS}}],
            "vout": [{"scriptpubkey_address": receiver, "value": value}]}


class AppTests(unittest.TestCase):
    def setUp(self):
        self.fetch = Mock(return_value=[])
        self.app = create_app({"TESTING": True}, fetch=self.fetch)
        self.client = self.app.test_client()

    def sample(self):
        response = self.client.post("/api/trace", json={"sample": True})
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def expand(self, graph, address="demo-alice", **extra):
        return self.client.post("/api/expand", json={"trace_id": graph["trace_id"], "address": address, **extra})

    def test_home_and_static_files(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"COMMUNITY / V1", response.data)
        for path in ("/static/app.js", "/static/style.css"):
            with self.client.get(path) as asset:
                self.assertEqual(asset.status_code, 200)

    def test_initial_limit_is_three_and_sample_is_offline(self):
        graph = self.sample()
        self.assertEqual(len(graph["edges"]), 3)
        self.assertEqual(len(graph["nodes"]), 4)
        self.assertTrue(graph["limited"])
        self.assertEqual(graph["source"], "synthetic")
        self.fetch.assert_not_called()

    def test_expansion_limit_is_two(self):
        graph = self.sample()
        response = self.expand(graph)
        self.assertEqual(response.status_code, 200)
        expanded = response.get_json()
        self.assertEqual(len(expanded["edges"]), 5)
        self.assertTrue(expanded["limited"])
        self.assertNotIn("demo-hidden-expansion", {node["id"] for node in expanded["nodes"]})

    def test_expansion_cannot_be_repeated_including_root(self):
        graph = self.sample()
        self.assertEqual(self.expand(graph, "demo-root").status_code, 409)
        self.assertEqual(self.expand(graph).status_code, 200)
        self.assertEqual(self.expand(graph).status_code, 409)

    def test_only_discovered_nodes_can_be_expanded(self):
        self.assertEqual(self.expand(self.sample(), "demo-hidden-initial").status_code, 400)

    def test_limits_and_unknown_fields_cannot_be_overridden(self):
        for field in ("limit", "hops", "direction", "export", "provider_url"):
            with self.subTest(field=field):
                self.assertEqual(self.client.post("/api/trace", json={"sample": True, field: 999}).status_code, 400)
        self.assertEqual(self.expand(self.sample(), limit=999).status_code, 400)

    def test_invalid_inputs(self):
        for payload in ({}, [], {"address": None}, {"address": "https://example.com"},
                        {"address": "../secrets"}, {"sample": "true"}, {"sample": 1}):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post("/api/trace", json=payload).status_code, 400)
        self.fetch.assert_not_called()

    def test_json_body_and_size_limits(self):
        self.assertEqual(self.client.post("/api/trace", data="text").status_code, 415)
        self.assertEqual(self.client.post("/api/trace", data="{", content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post("/api/trace", json={"address": "x" * 3000}).status_code, 413)

    def test_live_trace_uses_only_public_provider(self):
        self.fetch.return_value = [transaction()]
        response = self.client.post("/api/trace", json={"address": ADDRESS})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["source"], "blockstream")
        self.fetch.assert_called_once_with(ADDRESS)

    def test_provider_failure_never_falls_back_to_sample(self):
        self.fetch.side_effect = ExplorerError("Public explorer unavailable.")
        response = self.client.post("/api/trace", json={"address": ADDRESS})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("edges", response.get_json())
        self.assertFalse(self.app.extensions["traces"].graphs)

    def test_failed_expansion_can_be_retried(self):
        self.fetch.side_effect = [[transaction()], ExplorerError("Retry later."), []]
        graph = self.client.post("/api/trace", json={"address": ADDRESS}).get_json()
        self.assertEqual(self.expand(graph, RECEIVER).status_code, 502)
        self.assertEqual(self.expand(graph, RECEIVER).status_code, 200)

    def test_graphs_expire(self):
        graph = self.sample()
        self.app.extensions["traces"].graphs[graph["trace_id"]]["created"] -= GRAPH_TTL_SECONDS + 1
        self.assertEqual(self.expand(graph).status_code, 404)

    def test_unknown_trace_does_not_work(self):
        self.assertEqual(self.expand({"trace_id": "unknown"}).status_code, 404)

    def test_graph_capacity_does_not_evict_active_graphs(self):
        with patch("community.tracing.MAX_GRAPHS", 1):
            graph = self.sample()
            self.assertEqual(self.client.post("/api/trace", json={"sample": True}).status_code, 503)
            self.assertEqual(self.expand(graph).status_code, 200)

    def test_node_budget_is_enforced(self):
        graph = self.sample()
        state = self.app.extensions["traces"].graphs[graph["trace_id"]]
        while len(state["nodes"]) < MAX_NODES - 1:
            state["nodes"][f"demo-extra-{len(state['nodes'])}"] = 1
        result = self.expand(graph).get_json()
        self.assertEqual(len(result["nodes"]), MAX_NODES)
        self.assertTrue(result["at_limit"])
        self.assertTrue(all(not node["expandable"] for node in result["nodes"]))
        self.assertEqual(self.expand(graph, "demo-bob").status_code, 409)

    def test_cycles_do_not_duplicate_nodes(self):
        graph = self.sample()
        self.expand(graph)
        result = self.expand(graph, "demo-dana").get_json()
        ids = [node["id"] for node in result["nodes"]]
        self.assertEqual(ids.count("demo-root"), 1)

    def test_removed_features_have_no_routes(self):
        for path in ("/api/patterns", "/api/pattern-rules", "/api/ai-summary", "/api/ai-chat",
                     "/api/ai-cluster-explain", "/api/risk-lists", "/api/risk-lists/sync",
                     "/api/address-summary", "/api/btc-price", "/api/export", "/casework", "/casework/"):
            for method in ("GET", "POST"):
                with self.subTest(path=path, method=method):
                    self.assertEqual(self.client.open(path, method=method).status_code, 404)
        routes = {rule.rule for rule in self.app.url_map.iter_rules()}
        self.assertEqual(routes, {"/", "/api/trace", "/api/expand", "/static/<path:filename>"})

    def test_privacy_headers(self):
        response = self.client.get("/")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
        self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])
        self.assertNotIn("Set-Cookie", response.headers)


class ConnectionTests(unittest.TestCase):
    def test_only_outgoing_outputs_are_shown(self):
        tx = transaction()
        tx["vin"] = []
        self.assertEqual(outgoing_connections(ADDRESS, [tx], 3), ([], False))

    def test_change_and_non_address_outputs_are_omitted(self):
        tx = transaction()
        tx["vout"] += [{"scriptpubkey_address": ADDRESS, "value": 100}, {"value": 20}]
        self.assertEqual(len(outgoing_connections(ADDRESS, [tx], 3)[0]), 1)

    def test_multiple_outputs_have_unique_indices(self):
        tx = transaction()
        tx["vout"].append(copy.deepcopy(tx["vout"][0]))
        result, more = outgoing_connections(ADDRESS, [tx, tx], 3)
        self.assertEqual([edge["vout"] for edge in result], [0, 1])
        self.assertFalse(more)

    def test_malformed_provider_records_are_ignored(self):
        data = [None, {}, {"txid": None}, transaction(value="123"), transaction(value=True),
                transaction(value=-1), transaction(receiver="<script>")]
        self.assertEqual(outgoing_connections(ADDRESS, data, 3), ([], False))

    @patch("community.explorer.requests.get")
    def test_provider_rate_limit_is_handled(self, get):
        get.return_value.__enter__.return_value.status_code = 429
        with self.assertRaisesRegex(ExplorerError, "busy"):
            fetch_transactions(ADDRESS)

    @patch("community.explorer.requests.get")
    def test_provider_json_is_validated(self, get):
        response = get.return_value.__enter__.return_value
        response.status_code = 200
        response.iter_content.return_value = [b'{"unexpected": true}']
        with self.assertRaisesRegex(ExplorerError, "unexpected"):
            fetch_transactions(ADDRESS)

    @patch("community.explorer.requests.get")
    def test_response_size_is_bounded(self, get):
        response = get.return_value.__enter__.return_value
        response.status_code = 200
        response.iter_content.return_value = [b"x" * 101]
        with patch("community.explorer.MAX_RESPONSE_BYTES", 100):
            with self.assertRaisesRegex(ExplorerError, "too large"):
                fetch_transactions(ADDRESS)


if __name__ == "__main__":
    unittest.main()
