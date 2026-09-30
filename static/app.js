"use strict";

const form = document.querySelector("#trace-form");
const addressInput = document.querySelector("#address");
const sampleButton = document.querySelector("#sample-button");
const traceButton = document.querySelector("#trace-button");
const statusLine = document.querySelector("#status");
const svg = document.querySelector("#graph");
let graph = null;
let busy = false;

function svgElement(tag, attributes = {}, text) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
  if (text !== undefined) element.textContent = text;
  return element;
}

function shortAddress(value) {
  return value.length > 23 ? `${value.slice(0, 10)}…${value.slice(-8)}` : value;
}

function btc(sats) {
  return `${(sats / 100000000).toFixed(8).replace(/\.?0+$/, "")} BTC`;
}

function render() {
  svg.replaceChildren();
  svg.hidden = false;
  svg.removeAttribute("hidden");
  document.querySelector("#empty-state").hidden = true;
  document.querySelector("#source-label").textContent = graph.source === "synthetic" ? "SYNTHETIC SAMPLE / OFFLINE" : "BITCOIN MAINNET / BLOCKSTREAM";
  document.querySelector("#graph-count").textContent = `${graph.nodes.length} addresses · ${graph.edges.length} connections`;
  const columns = new Map();
  for (const node of graph.nodes) {
    if (!columns.has(node.depth)) columns.set(node.depth, []);
    columns.get(node.depth).push(node);
  }
  const height = Math.max(400, Math.max(...[...columns.values()].map(nodes => nodes.length)) * 112 + 80);
  const width = Math.max(1000, columns.size * 310 + 80);
  svg.setAttribute("width", width);
  svg.setAttribute("height", height);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  const defs = svgElement("defs");
  const marker = svgElement("marker", { id: "arrow", viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse" });
  marker.append(svgElement("path", { d: "M 0 0 L 10 5 L 0 10 z", class: "arrowhead" }));
  defs.append(marker);
  svg.append(defs);
  const positions = new Map();
  for (const [depth, nodes] of columns) {
    nodes.forEach((node, i) => positions.set(node.id, { x: 40 + depth * 310, y: height / 2 + (i - (nodes.length - 1) / 2) * 112 }));
  }
  const parallels = new Map();
  for (const edge of graph.edges) {
    const from = positions.get(edge.source);
    const to = positions.get(edge.target);
    const pair = `${edge.source}:${edge.target}`;
    const offset = (parallels.get(pair) || 0) * 18;
    parallels.set(pair, (parallels.get(pair) || 0) + 1);
    const forward = to.x > from.x;
    const x1 = from.x + (forward ? 210 : 105);
    const x2 = to.x + (forward ? 0 : 105);
    const y1 = from.y + (forward ? offset : -30);
    const y2 = to.y + (forward ? offset : -30);
    const control = Math.min(y1, y2) - 70 - offset;
    const d = forward ? `M ${x1} ${y1} C ${x1 + 45} ${y1}, ${x2 - 45} ${y2}, ${x2 - 4} ${y2}` : `M ${x1} ${y1} C ${x1} ${control}, ${x2} ${control}, ${x2} ${y2 - 4}`;
    const path = svgElement("path", { d, class: "edge", "marker-end": "url(#arrow)" });
    path.append(svgElement("title", {}, `Transaction: ${edge.txid}\nOutput ${edge.vout}: ${edge.value_sats} satoshis\n${edge.source} → ${edge.target}`));
    svg.append(path);
    svg.append(svgElement("text", { x: (x1 + x2) / 2, y: forward ? (y1 + y2) / 2 - 8 : control + 12, class: "edge-label", "text-anchor": "middle" }, btc(edge.value_sats)));
  }
  for (const node of graph.nodes) {
    const { x, y } = positions.get(node.id);
    const action = node.expandable ? "Expand up to 2 connections" : node.expanded ? "Expanded" : "Graph limit reached";
    const group = svgElement("g", { class: `node${node.id === graph.root ? " root" : ""}${node.expandable ? " expandable" : ""}`, transform: `translate(${x}, ${y - 30})`, role: node.expandable ? "button" : "img", tabindex: node.expandable ? "0" : "-1", "aria-label": `${node.id}. ${action}` });
    group.append(svgElement("title", {}, node.id));
    group.append(svgElement("rect", { width: 210, height: 60, rx: 9 }));
    group.append(svgElement("text", { x: 14, y: 25 }, shortAddress(node.id)));
    group.append(svgElement("text", { x: 14, y: 44, class: "node-action" }, node.expandable ? "+ Expand · max 2" : action));
    if (node.expandable) {
      group.addEventListener("click", () => expand(node.id));
      group.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          expand(node.id);
        }
      });
    }
    svg.append(group);
  }
}

async function requestGraph(path, payload) {
  if (busy) return;
  busy = true;
  traceButton.disabled = sampleButton.disabled = true;
  svg.setAttribute("aria-busy", "true");
  statusLine.classList.remove("error");
  statusLine.textContent = payload.sample || graph?.source === "synthetic" && path === "/api/expand" ? "Loading sample connections…" : "Reading recent confirmed transactions…";
  try {
    const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not load this trace.");
    const previousEdges = path === "/api/expand" ? graph.edges.length : 0;
    graph = data;
    render();
    if (graph.at_limit) statusLine.textContent = "Community graph limit reached. Start another trace to explore a different address.";
    else if (graph.edges.length === previousEdges) statusLine.textContent = "No outgoing connections found in the recent confirmed transaction sample.";
    else statusLine.textContent = `Select an unexpanded address to follow up to 2 connections.${graph.limited ? " Additional outputs were omitted by the limit." : ""}`;
  } catch (error) {
    statusLine.classList.add("error");
    statusLine.textContent = error.message || "Could not reach the app. Please try again.";
  } finally {
    busy = false;
    traceButton.disabled = sampleButton.disabled = false;
    svg.setAttribute("aria-busy", "false");
  }
}

function expand(address) {
  if (graph) requestGraph("/api/expand", { trace_id: graph.trace_id, address });
}

form.addEventListener("submit", event => {
  event.preventDefault();
  requestGraph("/api/trace", { address: addressInput.value.trim() });
});
sampleButton.addEventListener("click", () => requestGraph("/api/trace", { sample: true }));
