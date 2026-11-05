// Console data stays in this tab's RAM. Never log requests, credentials or terminal bytes.
export const $ = (selector, root = document) => root.querySelector(selector);
export const text = (node, value) => {
  node.textContent = value ?? "";
};
export const time = (value) =>
  value
    ? new Date(value).toLocaleString("en-GB", {
        timeZone: "Asia/Taipei",
        hour12: false,
      }) + " Taipei"
    : "—";
export class ApiError extends Error {
  constructor(status, detail) {
    super(
      typeof detail === "string" ? detail : detail?.message || "Request failed",
    );
    this.status = status;
    this.detail = detail;
    this.code = detail?.code;
  }
}
const messages = {
  browser_network_unavailable:
    "Browser connection lost. Retrying this attachment with bounded backoff; input is not replayed.",
  client_disabled:
    "This Console Client is disabled. Choose an enabled Client in Edit Connection or contact an administrator.",
  client_lab_mismatch:
    "UART requires a Console Client in the same Lab as this SUT.",
  client_name_or_ip_conflict:
    "Client name must be unique within its Lab; Client IPv4 must be globally unique, including disabled records.",
  uart_pair_conflict:
    "That Client / tmux pair is already assigned to another active SUT.",
  output_backpressure:
    "Terminal rendering could not keep up within the bounded buffer. Use a new manual Connect.",
  console_access_denied:
    "Console access is unavailable under the current policy. Connection settings remain independently editable.",
  console_http_not_opted_in:
    "HTTP Console has not been explicitly enabled by the operator.",
  credential_auth_failed:
    "SSH authentication failed. For UART, contact the Console Client administrator.",
  tmux_not_found:
    "The configured existing tmux session is missing or inaccessible. Edit Connection; it will not be created automatically.",
  host_key_changed:
    "The SSH host key changed. Review its fingerprint independently before reconnecting.",
  host_key_unknown: "SSH host key approval is required before authentication.",
  ssh_timeout:
    "SSH establishment timed out after 10 seconds. Retry or review the connection.",
  ssh_unavailable:
    "The SSH endpoint is unavailable. Retry or review the connection.",
  quota_exceeded:
    "All 10 Console session slots are occupied. Disconnect in an existing tab or wait for cleanup.",
  broker_unavailable:
    "Console service is unavailable. Contact the administrator.",
  broker_restarted: "Console service restarted. Use an explicit new Connect.",
  session_revoked:
    "This connection was revoked. Review permissions and settings before a new Connect.",
  readonly_attachment:
    "This tmux attachment remains read-only. Use Reconnect after your write permission is approved.",
  client_stale:
    "The Client changed while you were editing. Reload and review before saving again.",
  mapping_stale:
    "The connection changed while you were editing. Reload and review before saving again.",
  confirmation_stale:
    "Affected connections changed. Review a fresh preview before saving.",
  client_has_retained_bindings:
    "Unbind retained SUT UART mappings before moving this Client to another Lab.",
  grant_stale_or_expired:
    "The grant changed or expired. Reload the list; a fresh grant requires explicit approval.",
  read_only: "Read-only connection: input, paste and Send Key are disabled.",
  target_denied:
    "This target is invalid or sensitive. BMC requires a permitted RFC1918 IPv4 and port 22.",
};
export const friendly = (error) => {
  const message =
    messages[typeof error === "string" ? error : error.code] ||
    (error instanceof ApiError
      ? error.message
      : "The operation failed. Retry or review the connection.");
  return (
    message +
    (error?.detail?.conflicting_sut_id
      ? ` Conflicting SUT #${error.detail.conflicting_sut_id}.`
      : "") +
    (error?.detail?.sut_ids
      ? " Bound SUT IDs: " + error.detail.sut_ids.join(", ")
      : "")
  );
};
export async function api(path, method = "GET", data) {
  const response = await fetch("/api/v1/console" + path, {
    method,
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...(data !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(method !== "GET"
        ? { "X-CSRF-Token": $('meta[name="csrf-token"]').content }
        : {}),
    },
    ...(data !== undefined ? { body: JSON.stringify(data) } : {}),
  });
  const result = await response.json();
  if (!response.ok) throw new ApiError(response.status, result.detail);
  return result;
}
export async function allPages(path) {
  const result = [];
  for (let page = 1; page <= 100; page++) {
    const value = await api(
      `${path}${path.includes("?") ? "&" : "?"}page=${page}&page_size=100`,
    );
    result.push(...value.items);
    if (value.items.length < 100) return result;
  }
  throw new Error("List too large");
}
export function feedback(error, node = $("#console-feedback")) {
  if (node) {
    text(node, friendly(error));
    node.hidden = false;
    node.setAttribute("role", "alert");
  }
}
export async function busy(button, action) {
  button.disabled = true;
  try {
    await action();
  } catch (error) {
    if (error !== CANCEL) feedback(error);
  } finally {
    button.disabled = false;
  }
}
export const CANCEL = Symbol("user cancelled");
export function ask(
  title,
  explanation,
  { acknowledge, preview, timeoutMs } = {},
) {
  const dialog = $("#console-dialog");
  if (dialog.open) return Promise.reject(CANCEL);
  text($("#dialog-title"), title);
  text($("#dialog-text"), explanation);
  const sample = $("#dialog-preview");
  text(sample, preview || "");
  sample.hidden = !preview;
  const ack = $("#dialog-ack");
  ack.checked = false;
  ack.parentElement.hidden = !acknowledge;
  text($("#dialog-ack-label"), acknowledge || "");
  const accept = $("#dialog-accept");
  accept.disabled = !!acknowledge;
  ack.onchange = () => {
    accept.disabled = !!acknowledge && !ack.checked;
  };
  dialog.returnValue = "";
  return new Promise((resolve, reject) => {
    const form = dialog.querySelector("form");
    let settled = false;
    let timer;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      const ok = value === "accept" && (!acknowledge || ack.checked);
      text(sample, "");
      form.onsubmit = null;
      dialog.oncancel = null;
      ok
        ? resolve(true)
        : reject(
            value === "expired"
              ? new ApiError(
                  409,
                  "Confirmation expired. Review and submit a fresh operation.",
                )
              : CANCEL,
          );
    };
    // Resolve on the user's submit/cancel action, not a deferred close event:
    // a rapid next paste must not inherit a previous modal's pending state.
    form.onsubmit = (event) => {
      event.preventDefault();
      const value = event.submitter?.value || "cancel";
      if (value === "accept" && acknowledge && !ack.checked) return;
      dialog.close(value);
      finish(value);
    };
    dialog.oncancel = (event) => {
      event.preventDefault();
      dialog.close("cancel");
      finish("cancel");
    };
    dialog.showModal();
    if (timeoutMs !== undefined)
      timer = setTimeout(() => {
        dialog.close("expired");
        finish("expired");
      }, timeoutMs);
  });
}
export async function impact(preview) {
  if (preview.requires_confirmation) {
    const a = preview.affected;
    await ask(
      "Confirm affected sessions",
      `${a.sut_count} SUT(s), ${a.rd_count} RD user(s), ${a.session_count} session(s) will be disconnected. Save this exact change?`,
    );
  }
  return preview.confirmation_id;
}
export async function saveWithPreview(
  path,
  method,
  data,
  previewPath = path + "/preview",
) {
  const preview = await api(previewPath, "POST", data);
  const confirmation = await impact(preview);
  return api(path, method, {
    ...data,
    ...(confirmation ? { confirmation_id: confirmation } : {}),
  });
}
export async function trust(challenge, identity) {
  const a = challenge.affected;
  await ask(
    "Verify SSH Host Key",
    `${identity}\nAlgorithm: ${challenge.algorithm}\nFingerprint: ${challenge.fingerprint}\nPrevious: ${challenge.old_fingerprint || "Unknown"}\nAffected: ${a?.sut_count || 0} SUT(s), ${a?.rd_count || 0} RD(s), ${a?.session_count || 0} session(s).\nObtain the fingerprint from a trusted independent source. A changed Console Client key affects all its UART Web sessions.`,
    {
      timeoutMs: Math.max(
        0,
        Math.min(120000, new Date(challenge.expires_at).getTime() - Date.now()),
      ),
      acknowledge:
        "I compared this fingerprint with an independent trusted source and approve the affected-session scope.",
    },
  );
  return api("/trust/accept", "POST", {
    challenge_id: challenge.challenge_id,
    expected_trust_revision: challenge.expected_trust_revision,
    fingerprint: challenge.fingerprint,
    out_of_band_verified: true,
    ...(challenge.confirmation_id
      ? { confirmation_id: challenge.confirmation_id }
      : {}),
  });
}
export function row(table, values) {
  const tr = document.createElement("tr");
  for (const value of values) {
    const td = document.createElement("td");
    if (value instanceof Node) td.append(value);
    else text(td, value);
    tr.append(td);
  }
  table.append(tr);
  return tr;
}
export function button(label, action) {
  const el = document.createElement("button");
  el.type = "button";
  el.className = "btn btn-outline-primary btn-sm";
  text(el, label);
  el.addEventListener("click", () => busy(el, action));
  return el;
}
export function link(label, href) {
  const el = document.createElement("a");
  text(el, label);
  el.href = href;
  return el;
}
