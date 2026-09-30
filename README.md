# BTC Flow Tracer Community

A small, open-source Bitcoin address graph. Enter a mainnet address, see up to
**3 outgoing connections**, and click an unexpanded address to see up to **2 more**.
Those limits are enforced by the backend, including repeated requests.

This is a deliberately basic v1. It contains no rule engine, risk datasets,
wallet clustering, AI, casework, reporting, exports, accounts, or paid integrations.
There are no API keys to configure. Only the graph is included.

## Run locally

Use Python **3.10 or newer** with OpenSSL support and Git.

```sh
git clone https://github.com/ianikket/btc-flow-tracer-community.git
cd btc-flow-tracer-community
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

On Windows, use `py -m venv .venv`, then `.venv\Scripts\Activate.ps1` in PowerShell.

Open **http://127.0.0.1:5051**. Click **Try a sample** for a fully offline,
synthetic graph, or enter a Bitcoin mainnet address for a live trace.
Click a connected address to expand it. Hover a node for its full label, or an
edge for its transaction ID and output index. Keyboard users can Tab to a node
and press Enter or Space. Large graphs scroll inside the canvas.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `HOST` | `127.0.0.1` | Local bind address |
| `PORT` | `5051` | Local HTTP port |

For example: `PORT=5052 python app.py`. In PowerShell, run `$env:PORT="5052"`
before `python app.py`.

`.env.example` documents these non-secret settings. The app **does not load
`.env` files**; set variables in your shell. No credentials, provider tokens,
commercial services, or configurable remote URLs are needed.

## What the graph means

- A connection points from the selected input address to an output address in
  a transaction. The displayed amount is that output's full value. A transaction
  can have many inputs, so this does **not** attribute that value to one sender
  or prove ownership. This is address-level exploration, not UTXO tracing.
- Only the latest page of up to 25 **confirmed** transactions is considered.
  Connections follow the provider's transaction order, then output order.
  A connection is a transaction output: three outputs can belong to one
  transaction or one receiving address. Self-address outputs are omitted.
- The initial address gets up to 3 connections once. Each later address gets
  up to 2 connections once. There is no pagination, auto-recursion, depth slider,
  or way to override these limits in an API request.
- A graph stops at 60 unique addresses or 90 connections. Each graph expires
  15 minutes after creation. Restarting the app clears all graphs.
- Live requests use [Blockstream's public Esplora API](https://github.com/Blockstream/esplora/blob/master/API.md).
  Queried addresses and the server's IP are visible to that provider. Errors
  are shown explicitly; live failures never substitute sample data.

## Test and sample data

```sh
python -m unittest discover -s tests -v
```

Tests run without network access or credentials. They cover 3/2 limits, attempts
to bypass limits, expiry, graph caps, provider failures, malformed input,
cycles, and the absence of removed feature routes.

[`samples/transactions.json`](samples/transactions.json) is invented data with
`demo-*` labels and fabricated transaction IDs. It is not a blockchain dataset.
See [sample walkthrough](samples/README.md) and the
[Technical Design Document](docs/TECHNICAL_DESIGN.md), including architecture
and sequence diagrams.

## Operating scope

This v1 is a local, single-process app. There is no authentication, persistent
storage, per-user quota, or public-hosting rate limiter. Flask's development
server binds to localhost by default. Do not expose this server directly to
the internet; shared hosting would need separate deployment hardening.

All browser code is served locally, with no CDN dependencies, analytics,
browser storage, or outbound browser integrations. Graph state lives only in
server memory. Do not add real investigation records, keys, wallet files,
private services, or production data to this repository.

## License

[MIT](LICENSE). Dependencies retain their respective licenses. This license
covers this community repository, not any separate commercial product or dataset.
