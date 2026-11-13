// Exercise the dashboard's user flow without launching a browser or a shell.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

class Element {
  constructor() {
    this.children = [];
    this.listeners = {};
    this.classList = { toggle() {} };
    this.textContent = "";
    this.disabled = false;
  }

  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(event, callback) { this.listeners[event] = callback; }
  click() { return this.listeners.click(); }
  querySelectorAll(tag) {
    return this.children.flatMap(child => [
      ...(child.tag === tag ? [child] : []),
      ...child.querySelectorAll(tag),
    ]);
  }
}

function setup(fetch) {
  const ids = ["token", "load", "refresh", "previous", "next", "message", "requests", "page"];
  const elements = Object.fromEntries(ids.map(id => [id, new Element()]));
  const calls = [];
  const source = fs.readFileSync(path.join(__dirname, "../app/dashboard/app.js"), "utf8");
  vm.runInNewContext(source, {
    document: {
      getElementById: id => elements[id],
      createElement: tag => Object.assign(new Element(), { tag }),
      createTextNode: text => Object.assign(new Element(), { textContent: text }),
    },
    window: { confirm: () => true },
    fetch: async (...args) => { calls.push(args); return fetch(...args); },
  });
  return { elements, calls };
}

const response = (body, ok = true, status = 200) => ({ ok, status, json: async () => body });
const request = (status, id) => ({
  id, status, command: "<script>unsafe</script>", cwd: "/tmp/lab", source: "agent",
  assessment: { decision: "REVIEW", category: "WRITE", risk_score: 50, reasons: ["Needs review"] },
  created: 1000, expires: 1300,
});

test("loads text-only requests and sends the exact approved identity", async () => {
  let state = "PENDING";
  const { elements, calls } = setup((url, options) => {
    if (options.method === "POST") {
      state = "APPROVED";
      return response(request(state, "id-one"));
    }
    return response({ requests: [request(state, "id-one")] });
  });
  elements.token.value = "test-token";
  await elements.load.click();
  assert.equal(elements.token.value, "");
  assert.equal(elements.requests.children[0].children[1].textContent, "<script>unsafe</script>");
  assert.equal(elements.requests.querySelectorAll("button").length, 2);
  await elements.requests.querySelectorAll("button")[0].click();
  assert.equal(calls[1][0], "/api/requests/id-one/decide");
  assert.equal(calls[1][1].headers.Authorization, "Bearer test-token");
  assert.deepEqual(JSON.parse(calls[1][1].body), {
    command: "<script>unsafe</script>", cwd: "/tmp/lab", source: "agent", decision: "APPROVE",
  });
  assert.equal(elements.requests.children[0].children[0].textContent, "APPROVED");
  assert.equal(elements.requests.querySelectorAll("button").length, 0);
});

test("shows expired requests without decision controls and reports access errors", async () => {
  let allowed = true;
  const { elements } = setup(() => allowed
    ? response({ requests: [request("EXPIRED", "id-two")] })
    : response({}, false, 401));
  elements.token.value = "test-token";
  await elements.load.click();
  assert.equal(elements.requests.querySelectorAll("button").length, 0);
  allowed = false;
  await elements.refresh.click();
  assert.match(elements.message.textContent, /Access denied/);
  assert.equal(elements.requests.children.length, 0);
});

test("stale approval refreshes to expired and removes obsolete buttons", async () => {
  let state = "PENDING";
  const { elements, calls } = setup((url, options) => {
    if (options.method === "POST") {
      state = "EXPIRED";
      return response({}, false, 409);
    }
    return response({ requests: [request(state, "id-three")] });
  });
  elements.token.value = "test-token";
  await elements.load.click();
  await elements.requests.querySelectorAll("button")[0].click();
  assert.equal(calls.length, 3);
  assert.equal(elements.requests.children[0].children[0].textContent, "EXPIRED");
  assert.equal(elements.requests.querySelectorAll("button").length, 0);
  assert.match(elements.message.textContent, /Decision not applied/);
});
