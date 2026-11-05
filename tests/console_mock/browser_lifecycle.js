// Test-only, bounded metadata. Never retain binary output, outbound frames,
// tickets, usernames, credentials, display names or terminal/clipboard text.
(() => {
  const Native = window.WebSocket;
  const trace = [];
  let next = 0;
  const append = (value) => {
    trace.push({ ms: Math.round(performance.now()), ...value });
    if (trace.length > 512) trace.shift();
  };
  window.__r1Trace = trace;
  window.WebSocket = class extends Native {
    constructor(...args) {
      super(...args);
      window.__consoleTestSocket = this;
      const socket = ++next;
      append({ socket, event: "created" });
      this.addEventListener("open", () => append({ socket, event: "open" }));
      this.addEventListener("close", (e) =>
        append({ socket, event: "close", code: e.code }),
      );
      this.addEventListener("message", (e) => {
        if (typeof e.data !== "string") return;
        let data;
        try {
          data = JSON.parse(e.data);
        } catch {
          return;
        }
        if (
          !["state", "connected", "participants", "revoked"].includes(data.type)
        )
          return;
        const item = { socket, event: data.type };
        if (Number.isSafeInteger(data.attachment_generation))
          item.generation = data.attachment_generation;
        if (
          [
            "Not Connected",
            "Connecting",
            "Connected",
            "Reconnecting",
            "Disconnected",
            "Failed",
          ].includes(data.state)
        )
          item.state = data.state;
        if (Number.isSafeInteger(data.unique_user_count))
          item.count = data.unique_user_count;
        append(item);
      });
    }
  };
  document.addEventListener("DOMContentLoaded", () => {
    const state = document.querySelector("#connection-state");
    if (!state) return;
    new MutationObserver(() => {
      if (
        [
          "Not Connected",
          "Connecting",
          "Connected",
          "Reconnecting",
          "Disconnected",
          "Failed",
        ].includes(state.textContent)
      )
        append({ event: "ui", state: state.textContent });
    }).observe(state, { childList: true });
  });
})();
