"""One public, read-only Bitcoin data source; no credentials or enrichment."""

import json
import re

import requests

API_BASE = "https://blockstream.info/api"
ADDRESS_PATTERN = re.compile(r"(?:[13][a-km-zA-HJ-NP-Z1-9]{25,34}|bc1[ac-hj-np-z02-9]{11,71})\Z")
TXID_PATTERN = re.compile(r"[a-f0-9]{64}\Z")
MAX_RESPONSE_BYTES = 4_000_000


class ExplorerError(Exception):
    """A public data source could not provide a usable response."""


def plausible_address(address):
    """Syntax check only; Esplora validates the address checksum."""
    return isinstance(address, str) and bool(ADDRESS_PATTERN.fullmatch(address))


def fetch_transactions(address):
    """Read one page (up to 25) of confirmed transactions, newest first."""
    try:
        with requests.get(f"{API_BASE}/address/{address}/txs/chain",
                          timeout=(4, 10), stream=True,
                          allow_redirects=False) as response:
            if response.status_code == 429:
                raise ExplorerError("The public explorer is busy. Please try again later.")
            if response.status_code == 400:
                raise ExplorerError("The public explorer rejected this Bitcoin address.")
            if response.status_code != 200:
                raise ExplorerError("The public explorer is unavailable. Please try again later.")
            chunks = bytearray()
            for chunk in response.iter_content(chunk_size=65536):
                chunks.extend(chunk)
                if len(chunks) > MAX_RESPONSE_BYTES:
                    raise ExplorerError("The public explorer response is too large.")
            data = json.loads(chunks)
            if not isinstance(data, list):
                raise ExplorerError("The public explorer returned an unexpected response.")
            return data[:25]
    except (requests.RequestException, ValueError) as exc:
        raise ExplorerError("Could not read the public explorer. Please try again later.") from exc


def outgoing_connections(address, transactions, limit, sample=False):
    """Select bounded output relationships, without attributing input ownership."""
    connections = []
    seen = set()
    for tx in transactions[:25]:
        if not isinstance(tx, dict):
            continue
        txid = tx.get("txid", "")
        inputs, outputs = tx.get("vin"), tx.get("vout")
        if not isinstance(txid, str) or not TXID_PATTERN.fullmatch(txid):
            continue
        if not isinstance(inputs, list) or not isinstance(outputs, list):
            continue
        if not any(isinstance(vin, dict) and isinstance(vin.get("prevout"), dict)
                   and vin["prevout"].get("scriptpubkey_address") == address for vin in inputs):
            continue
        for index, output in enumerate(outputs):
            if not isinstance(output, dict):
                continue
            receiver, value = output.get("scriptpubkey_address"), output.get("value")
            valid_receiver = (isinstance(receiver, str) and receiver.startswith("demo-")
                              if sample else plausible_address(receiver))
            if not valid_receiver or receiver == address or type(value) is not int or value <= 0:
                continue
            key = (txid, index)
            if key in seen:
                continue
            seen.add(key)
            connections.append({"source": address, "target": receiver,
                                "txid": txid, "vout": index, "value_sats": value})
            if len(connections) > limit:
                return connections[:limit], True
    return connections, False
