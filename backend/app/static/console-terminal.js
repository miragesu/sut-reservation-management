import {
  $,
  text,
  time,
  api,
  busy,
  feedback,
  friendly,
  ApiError,
  ask,
  CANCEL,
  trust,
} from "./console-common.js";
import { sha256 } from "./vendor/console/hash.js";
const root = $("#console-page"),
  sut = Number(root.dataset.sutId),
  tab = crypto.randomUUID
    ? crypto.randomUUID()
    : Array.from(crypto.getRandomValues(new Uint8Array(16)), (v) =>
        v.toString(16).padStart(2, "0"),
      ).join("");
const terminal = new window.Terminal({
  scrollback: 10000,
  fontSize: 14,
  disableStdin: true,
  convertEol: false,
  allowProposedApi: true,
  linkHandler: { activate: () => {}, hover: () => {}, leave: () => {} },
});
const fit = new window.FitAddon.FitAddon(),
  search = new window.SearchAddon.SearchAddon({ highlightLimit: 1000 });
terminal.loadAddon(fit);
terminal.loadAddon(search);
terminal.open($("#terminal"));
// Consume hostile remote clipboard/hyperlink instructions; no web-links/image/download addons.
terminal.parser.registerOscHandler(52, () => true);
terminal.parser.registerOscHandler(8, () => true);
let pendingOutput = 0;
let fullscreenExitAt = -Infinity;
let state = "Not Connected",
  mode = "uart",
  access = "read",
  mapping = null,
  socket = null,
  logical = null,
  generation = 0,
  seq = 0,
  run = 0,
  flow = null,
  everConnected = false,
  focusOnConnect = false,
  manual = true,
  retryCount = 0,
  pasting = false,
  resizeTimer;
const encoder = new TextEncoder();
function writable() {
  return (
    state === "Connected" &&
    access === "write" &&
    socket?.readyState === WebSocket.OPEN
  );
}
function setState(value, reason) {
  state = value;
  text($("#connection-state"), value);
  $("#console-retry").hidden = value !== "Failed";
  if (!["Connected", "Reconnecting"].includes(value)) {
    text($("#participants"), "");
    $("#shared-warning").hidden = true;
  }
  const writing = writable();
  terminal.options.disableStdin = !writing;
  $("#send-key-button").disabled = !writing;
  $("#send-key").disabled = !writing;
  text(
    $("#effective-mode"),
    state === "Connected"
      ? access === "write"
        ? "Read / Write"
        : "Read-only"
      : "Input disabled",
  );
  const pending = ["Connecting", "Reconnecting"].includes(state);
  $("#console-connect").disabled = pending || state === "Connected";
  $("#console-reconnect").disabled = pending;
  $("#console-disconnect").disabled = !pending && state !== "Connected";
  if (reason) feedback(reason);
  if (!pending && state !== "Connected") eraseAuth();
}
function eraseAuth() {
  flow = null;
  $("#bmc-auth").hidden = true;
  $("#bmc-username").value = "";
  $("#bmc-password").value = "";
}
function encode(bytes) {
  let result = "";
  for (const byte of bytes) result += String.fromCharCode(byte);
  return btoa(result);
}
function send(data) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return false;
  if (socket.bufferedAmount > 65536) {
    feedback("rate_limited");
    return false;
  }
  socket.send(JSON.stringify(data));
  return true;
}
function boundary() {
  if (everConnected) {
    $("#reconnect-boundary").hidden = false;
    terminal.writeln(
      "\r\n──────── Reconnect: prior input is never replayed ────────\r\n",
    );
  }
}
async function quota() {
  const data = await api("/sessions/me");
  text($("#quota-summary"), `${data.usage}/10 Console sessions`);
}
async function refresh() {
  mapping = await api(`/suts/${sut}/connections`);
  const current = mapping[mode];
  text(
    $("#endpoint-summary"),
    mode === "uart"
      ? current.client
        ? `${current.client.name} · ${current.client.ipv4}:${current.client.ssh_port} · tmux ${current.tmux_session || "Not Configured"}${current.client.enabled ? "" : " · Client Disabled"}`
        : "Not Configured — use Edit Connection"
      : current.ipv4
        ? `${current.ipv4}:22`
        : "Not Configured — use Edit Connection",
  );
  const grants = await api(`/suts/${sut}/my-grant`);
  const active = grants.items.find(
    (g) => g.state === "active" && new Date(g.expires_at) > new Date(),
  );
  text(
    $("#own-grant"),
    active ? `Your maintenance grant expires ${time(active.expires_at)}.` : "",
  );
  await quota();
}
async function reviewKey(always = false) {
  const current = mapping[mode];
  if (mode === "uart" && (!current.client || !current.tmux_session))
    throw new ApiError(409, {
      code: "not_configured",
      message: "Not Configured — edit UART connection.",
    });
  if (mode === "bmc" && !current.ipv4)
    throw new ApiError(409, {
      code: "not_configured",
      message: "Not Configured — edit BMC connection.",
    });
  if (!always && mode === "uart" && !current.client.enabled)
    throw new ApiError(409, { code: "client_disabled" });
  const challenge = await api(
    "/trust/challenges",
    "POST",
    mode === "uart" ? { client_id: current.client_id } : { sut_id: sut },
  );
  if (
    always ||
    !challenge.old_fingerprint ||
    challenge.fingerprint !== challenge.old_fingerprint
  )
    await trust(
      challenge,
      mode === "uart"
        ? `${current.client.name} · ${current.client.ipv4}:${current.client.ssh_port}`
        : `${current.ipv4}:22`,
    );
}
function disconnect() {
  manual = true;
  run++;
  pasting = false;
  const old = socket;
  socket = null;
  if (old?.readyState === WebSocket.OPEN)
    old.send(JSON.stringify({ type: "disconnect" }));
  old?.close(1000, "explicit_disconnect");
  eraseAuth();
  setState("Disconnected");
  quota().catch(() => {});
}
async function connect({ reconnect = false, automatic = false } = {}) {
  if (!automatic && reconnect && state === "Connected")
    await ask(
      "Reconnect this Console?",
      "Only this tab’s SSH attachment will close. The in-memory buffer remains; terminal input will not be replayed.",
    );
  const mine = ++run;
  manual = false;
  focusOnConnect = !automatic;
  text($("#console-feedback"), "");
  eraseAuth();
  setState(reconnect ? "Reconnecting" : "Connecting");
  try {
    if (!automatic) {
      retryCount = 0;
      await refresh();
      if (mapping.access.mode === "deny")
        throw new ApiError(403, { code: "console_access_denied" });
      if (!mapping.terminal_available)
        throw new ApiError(503, { code: "broker_unavailable" });
      await reviewKey();
    }
    if (mine !== run) return;
    let reservation;
    if (reconnect && logical) {
      try {
        reservation = await api(`/sessions/${logical}/attach`, "POST", {
          attachment_generation: generation,
          tab_id: tab,
          confirm_connected: true,
        });
      } catch (error) {
        if (automatic || error.code !== "console_attachment_stale") throw error;
      }
    }
    if (!reservation)
      reservation = await api("/sessions", "POST", {
        sut_id: sut,
        transport: mode,
        expected_revision: mapping[mode].revision,
        tab_id: tab,
      });
    if (mine !== run) return;
    const prior = socket;
    socket = null;
    prior?.close(1000, "attachment_replaced");
    logical = reservation.session_id;
    generation = reservation.attachment_generation;
    access = reservation.mode;
    seq = 0;
    boundary();
    const ws = new WebSocket(
      `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/ws/console/v1/sessions/${logical}`,
      "sut-console.v1",
    );
    socket = ws;
    ws.binaryType = "arraybuffer";
    ws.onopen = () => {
      if (mine !== run) {
        ws.close();
        return;
      }
      fitTerminal();
      send({
        v: 1,
        type: "hello",
        ticket: reservation.ticket,
        tab_id: tab,
        attachment_generation: generation,
        cols: Math.min(500, Math.max(2, terminal.cols)),
        rows: Math.min(200, Math.max(1, terminal.rows)),
      });
      delete reservation.ticket;
    };
    ws.onmessage = (event) => {
      if (mine !== run || socket !== ws) return;
      if (event.data instanceof ArrayBuffer) {
        const bytes = new Uint8Array(event.data);
        if (pendingOutput + bytes.length > 1048576) {
          disconnect();
          setState("Failed", "output_backpressure");
          return;
        }
        pendingOutput += bytes.length;
        terminal.write(bytes, () => {
          pendingOutput -= bytes.length;
        });
        return;
      }
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        disconnect();
        return;
      }
      if (message.type === "state") {
        if (message.attachment_generation !== generation) {
          generation = message.attachment_generation;
          seq = 0;
          pasting = false;
          boundary();
        }
        access = message.effective_mode;
        setState(message.state, message.reason_code);
        if (message.state === "Failed") manual = true;
      } else if (message.type === "connected") {
        generation = message.attachment_generation;
        access = message.mode;
        setState("Connected");
        const first = focusOnConnect;
        focusOnConnect = false;
        everConnected = true;
        retryCount = 0;
        if (
          first &&
          access === "write" &&
          document.visibilityState === "visible"
        )
          terminal.focus();
        quota().catch(() => {});
      } else if (message.type === "auth_required") {
        flow = message.flow_id;
        $("#bmc-username").value = "";
        $("#bmc-password").value = "";
        $("#bmc-auth").hidden = false;
        text(
          $("#bmc-attempts"),
          `${message.remaining_attempts} authentication attempt(s) remaining${message.reason_code ? " · " + friendly(message.reason_code) : ""}`,
        );
        if (document.visibilityState === "visible") $("#bmc-username").focus();
      } else if (message.type === "participants") {
        text(
          $("#participants"),
          `${message.unique_user_count} distinct Web RD user(s): ${message.users.map((u) => `${u.display_name} (${u.mode === "write" ? "Read / Write" : "Read-only"})`).join(", ")}`,
        );
        $("#shared-warning").hidden = !message.shared_console;
      } else if (message.type === "revoked") {
        manual = true;
        eraseAuth();
        setState("Disconnected", message.reason_code);
      } else if (message.type === "reconnect_required")
        feedback(message.reason_code);
      else if (message.type === "input_rejected") feedback(message.reason_code);
    };
    ws.onclose = async (event) => {
      if (mine !== run || socket !== ws) return;
      socket = null;
      eraseAuth();
      pasting = false;
      quota().catch(() => {});
      if (!manual && event.code === 1006 && everConnected && retryCount < 3) {
        retryCount++;
        setState("Reconnecting", "browser_network_unavailable");
        const attempt = retryCount;
        await new Promise((resolve) =>
          setTimeout(resolve, [1000, 2000, 4000][attempt - 1]),
        );
        if (mine === run && !manual)
          connect({ reconnect: true, automatic: true }).catch(feedback);
      } else if (state !== "Failed" && state !== "Disconnected")
        setState(
          event.code === 1000 ? "Disconnected" : "Failed",
          event.code === 1000 ? null : "ssh_unavailable",
        );
    };
  } catch (error) {
    if (mine !== run) return;
    if (automatic && !(error instanceof ApiError) && retryCount < 3) {
      retryCount++;
      setState("Reconnecting", "browser_network_unavailable");
      await new Promise((resolve) =>
        setTimeout(resolve, [1000, 2000, 4000][retryCount - 1]),
      );
      if (mine === run && !manual)
        await connect({ reconnect: true, automatic: true });
      return;
    }
    manual = true;
    eraseAuth();
    setState("Failed");
    if (error !== CANCEL) feedback(error);
  }
}
function fitTerminal() {
  try {
    fit.fit();
    if (terminal.cols > 500 || terminal.rows > 200)
      terminal.resize(
        Math.min(500, terminal.cols),
        Math.min(200, terminal.rows),
      );
  } catch {
    /* Hidden/fullscreen transition: next observer will fit. */
  }
}
terminal.onResize(({ cols, rows }) => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    if (state === "Connected")
      send({
        type: "resize",
        cols: Math.min(500, Math.max(2, cols)),
        rows: Math.min(200, Math.max(1, rows)),
      });
  }, 110);
});
new ResizeObserver(fitTerminal).observe($("#terminal"));
document.addEventListener("fullscreenchange", () => {
  if (!document.fullscreenElement) fullscreenExitAt = performance.now();
  fitTerminal();
});
document.addEventListener(
  "keydown",
  (event) => {
    if (
      event.key === "Escape" &&
      (document.fullscreenElement || performance.now() - fullscreenExitAt < 300)
    ) {
      event.preventDefault();
      event.stopImmediatePropagation();
      fullscreenExitAt = performance.now();
      document.exitFullscreen().catch(feedback);
    }
  },
  true,
);
function input(bytes) {
  if (!writable() || pasting) return;
  if (bytes.length > 8192) {
    feedback(
      new ApiError(422, "Input exceeds the per-frame limit. Use paste."),
    );
    return;
  }
  send({
    type: "input",
    attachment_generation: generation,
    seq: ++seq,
    data: encode(bytes),
  });
}
terminal.onData((data) => input(encoder.encode(data)));
terminal.onBinary((data) =>
  input(Uint8Array.from(data, (c) => c.charCodeAt(0))),
);
$("#send-key-button").onclick = () => {
  if (writable() && !pasting)
    send({
      type: "send_key",
      attachment_generation: generation,
      seq: ++seq,
      key: $("#send-key").value,
    });
};
function openSearch() {
  $("#search-bar").hidden = false;
  $("#search-term").focus();
}
terminal.attachCustomKeyEventHandler((event) => {
  // Let the browser dispatch native paste; xterm otherwise maps Ctrl+V to SYN.
  // The capture paste handler below still applies all policy/preview bounds.
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "v")
    return false;
  if (
    event.type === "keydown" &&
    event.ctrlKey &&
    event.key.toLowerCase() === "f"
  ) {
    event.preventDefault();
    openSearch();
    return false;
  }
  if (
    event.type === "keydown" &&
    event.key === "Escape" &&
    document.fullscreenElement
  ) {
    if (document.fullscreenElement) document.exitFullscreen().catch(feedback);
    event.preventDefault();
    return false;
  }
  return true;
});
const find = (previous) => {
  const query = $("#search-term").value;
  const options = {
    caseSensitive: false,
    regex: false,
    decorations: {
      matchBackground: "#ffe080",
      matchBorder: "#775500",
      matchOverviewRuler: "#ffe080",
      activeMatchBackground: "#ff9b40",
      activeMatchBorder: "#fff",
      activeMatchOverviewRuler: "#ff9b40",
    },
  };
  text(
    $("#search-result"),
    query &&
      (previous
        ? search.findPrevious(query, options)
        : search.findNext(query, options))
      ? "Match highlighted"
      : "No match",
  );
};
$("#terminal-search").onclick = openSearch;
$("#search-next").onclick = () => find(false);
$("#search-prev").onclick = () => find(true);
$("#search-term").onkeydown = (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    find(event.shiftKey);
  }
  if (event.key === "Escape") {
    $("#search-bar").hidden = true;
    search.clearDecorations();
    terminal.focus();
  }
};
$("#search-close").onclick = () => {
  $("#search-bar").hidden = true;
  search.clearDecorations();
  terminal.focus();
};
for (const [selector, delta] of [
  ["#font-minus", -1],
  ["#font-plus", 1],
])
  $(selector).onclick = () => {
    terminal.options.fontSize = Math.max(
      10,
      Math.min(24, terminal.options.fontSize + delta),
    );
    text($("#font-size"), `${terminal.options.fontSize}px`);
    fitTerminal();
  };
$("#terminal-fullscreen").onclick = async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else if ($("#terminal-stage").requestFullscreen)
      await $("#terminal-stage").requestFullscreen();
    else throw new Error();
  } catch {
    feedback(
      new ApiError(
        422,
        "Fullscreen is unavailable in this browser; resize the window instead.",
      ),
    );
  }
};
async function paste(value) {
  if (!writable()) {
    feedback("read_only");
    return;
  }
  if (pasting) {
    feedback(
      new ApiError(
        409,
        "A paste is already in progress. Wait or cancel it first.",
      ),
    );
    return;
  }
  const bytes = encoder.encode(value);
  if (!bytes.length) return;
  if (bytes.length > 65536 || bytes.includes(0)) {
    feedback(
      new ApiError(
        422,
        "Paste rejected: maximum 64 KiB and no NUL characters.",
      ),
    );
    return;
  }
  const lines = value.split(/\r\n|\r|\n/).length;
  const controls = /[\p{Cc}\p{Cf}]/u.test(value.replace(/[\t\r\n]/g, ""));
  if (controls) {
    feedback(
      new ApiError(
        422,
        "Paste rejected: hidden control characters. Type approved terminal controls directly.",
      ),
    );
    return;
  }
  const mine = run,
    gen = generation;
  let approved = false;
  pasting = true;
  try {
    if (lines > 1) {
      await ask(
        "Confirm multiline paste",
        `${lines} lines (${bytes.length} bytes) will be sent. Review before sending.${value.length > 12000 ? " Preview shows the first 12,000 characters only." : ""}`,
        { preview: value.slice(0, 12000) },
      );
      approved = true;
    }
    if (mine !== run || gen !== generation || !writable()) return;
    terminal.scrollToBottom();
    const id = Array.from(crypto.getRandomValues(new Uint8Array(12)), (v) =>
      v.toString(16).padStart(2, "0"),
    ).join("");
    const hash = Array.from(sha256(bytes), (v) =>
      v.toString(16).padStart(2, "0"),
    ).join("");
    if (
      !send({
        type: "paste_begin",
        attachment_generation: gen,
        paste_id: id,
        byte_count: bytes.length,
        sha256: hash,
        multiline_approved: approved,
      })
    )
      return;
    for (let offset = 0; offset < bytes.length; offset += 8192) {
      if (mine !== run || gen !== generation || !writable()) return;
      if (
        !send({
          type: "paste_chunk",
          attachment_generation: gen,
          paste_id: id,
          seq: ++seq,
          data: encode(bytes.subarray(offset, offset + 8192)),
          final: offset + 8192 >= bytes.length,
        })
      )
        return;
      if (offset + 8192 < bytes.length)
        await new Promise((resolve) => setTimeout(resolve, 110));
    }
  } catch (error) {
    if (error !== CANCEL) feedback(error);
  } finally {
    pasting = false;
    value = "";
    bytes.fill(0);
  }
}
$("#terminal").addEventListener(
  "paste",
  (event) => {
    event.preventDefault();
    event.stopImmediatePropagation();
    paste(event.clipboardData?.getData("text/plain") || "");
  },
  true,
);
$("#terminal").addEventListener(
  "contextmenu",
  async (event) => {
    event.preventDefault();
    if (!writable()) {
      feedback("read_only");
      return;
    }
    try {
      if (!navigator.clipboard?.readText) throw new Error();
      await paste(await navigator.clipboard.readText());
    } catch {
      text(
        $("#clipboard-help"),
        "Clipboard access is unavailable or denied. Focus the terminal and press Ctrl+V.",
      );
    }
  },
  true,
);
$("#bmc-auth").onsubmit = (event) => {
  event.preventDefault();
  const username = $("#bmc-username").value,
    password = $("#bmc-password").value,
    currentFlow = flow;
  $("#bmc-username").value = "";
  $("#bmc-password").value = "";
  $("#bmc-auth").hidden = true;
  flow = null;
  if (currentFlow && socket?.readyState === WebSocket.OPEN) {
    focusOnConnect = true;
    send({ type: "authenticate", flow_id: currentFlow, username, password });
  }
};
$("#console-retry").onclick = () =>
  connect().catch((error) => {
    if (error !== CANCEL) feedback(error);
  });
$("#console-connect").onclick = () =>
  connect().catch((error) => {
    if (error !== CANCEL) feedback(error);
  });
$("#console-reconnect").onclick = () =>
  connect({ reconnect: true }).catch((error) => {
    if (error !== CANCEL) feedback(error);
  });
$("#console-disconnect").onclick = disconnect;
$("#console-mode").onchange = async () => {
  disconnect();
  mode = $("#console-mode").value;
  logical = null;
  generation = seq = 0;
  setState("Not Connected");
  try {
    await refresh();
  } catch (error) {
    feedback(error);
  }
};
$("#console-trust").onclick = (event) =>
  busy(event.currentTarget, async () => {
    await refresh();
    await reviewKey(true);
    text(
      $("#console-feedback"),
      "Host Key trust updated. Use a new manual Connect.",
    );
  });
window.addEventListener("beforeunload", (event) => {
  if (["Connected", "Reconnecting"].includes(state)) {
    event.preventDefault();
    event.returnValue = "";
  }
});
window.addEventListener("pagehide", disconnect);
$("#transport-warning").hidden = location.protocol !== "http:";
refresh().then(fitTerminal).catch(feedback);
setInterval(() => {
  quota().catch(() => {});
}, 30000);
