"use strict";

const tokenInput = document.getElementById("token");
const loadButton = document.getElementById("load");
const refreshButton = document.getElementById("refresh");
const previousButton = document.getElementById("previous");
const nextButton = document.getElementById("next");
const message = document.getElementById("message");
const container = document.getElementById("requests");
const pageLabel = document.getElementById("page");
const pageSize = 20;
let token = "";
let page = 0;
let busy = false;
let hasNext = false;

function status(text, error = false) {
  message.textContent = text;
  message.classList.toggle("error", error);
}

function controls() {
  loadButton.disabled = busy;
  refreshButton.disabled = busy || !token;
  previousButton.disabled = busy || !token || page === 0;
  nextButton.disabled = busy || !token || !hasNext;
  pageLabel.textContent = `Page ${page + 1}`;
}

function line(parent, label, value) {
  const row = document.createElement("p");
  const title = document.createElement("strong");
  title.textContent = `${label}: `;
  row.append(title, document.createTextNode(String(value)));
  parent.append(row);
}

function render(record) {
  const card = document.createElement("article");
  const title = document.createElement("h3");
  title.textContent = record.status;
  title.className = "status";
  card.append(title);
  const command = document.createElement("pre");
  command.textContent = record.command;
  card.append(command);
  line(card, "Working directory", record.cwd);
  line(card, "Source", record.source);
  line(card, "Assessment", `${record.assessment.decision} · ${record.assessment.category} · score ${record.assessment.risk_score}`);
  line(card, "Reasons", record.assessment.reasons.join("; "));
  line(card, "Created", new Date(record.created * 1000).toLocaleString());
  line(card, "Expires", new Date(record.expires * 1000).toLocaleString());
  line(card, "Request ID", record.id);
  if (record.status === "PENDING") {
    for (const [label, decision] of [["Approve", "APPROVE"], ["Reject", "REJECT"]]) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.addEventListener("click", () => decide(record, decision));
      card.append(button);
    }
  }
  container.append(card);
}

async function load() {
  if (!token || busy) return;
  busy = true;
  controls();
  status("Loading requests…");
  try {
    const response = await fetch(`/api/requests?limit=${pageSize}&offset=${page * pageSize}`, {
      headers: { Authorization: `Bearer ${token}` }, cache: "no-store"
    });
    if (!response.ok) throw new Error(response.status === 401 ? "Access denied. Check your token." : "Could not load requests. Try again.");
    const result = await response.json();
    container.replaceChildren();
    for (const record of result.requests) render(record);
    hasNext = result.requests.length === pageSize;
    status(result.requests.length ? `Showing ${result.requests.length} requests.` : "No requests on this page.");
  } catch (error) {
    container.replaceChildren();
    status(error.message, true);
    hasNext = false;
  } finally {
    busy = false;
    controls();
  }
}

async function decide(record, decision) {
  if (busy || !token || record.status !== "PENDING") return;
  if (!window.confirm(`${decision === "APPROVE" ? "Approve" : "Reject"} this exact request? No command will be executed.`)) return;
  busy = true;
  controls();
  container.querySelectorAll("button").forEach(button => { button.disabled = true; });
  status("Saving decision…");
  try {
    const response = await fetch(`/api/requests/${encodeURIComponent(record.id)}/decide`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ command: record.command, cwd: record.cwd, source: record.source, decision }),
      cache: "no-store"
    });
    if (!response.ok) throw new Error(response.status === 401 ? "Access denied. Check your token." : "Decision failed or request expired. Refresh to see its current status.");
    busy = false;
    await load();
  } catch (error) {
    status(error.message, true);
    busy = false;
    controls();
    container.querySelectorAll("button").forEach(button => { button.disabled = false; });
  }
}

loadButton.addEventListener("click", () => {
  token = tokenInput.value;
  tokenInput.value = "";
  page = 0;
  hasNext = false;
  container.replaceChildren();
  if (!token) { status("Enter a token first.", true); controls(); return; }
  load();
});
refreshButton.addEventListener("click", load);
previousButton.addEventListener("click", () => { page -= 1; load(); });
nextButton.addEventListener("click", () => { page += 1; load(); });
