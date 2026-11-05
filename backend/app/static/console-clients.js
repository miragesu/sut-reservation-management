import {
  $,
  text,
  api,
  allPages,
  busy,
  feedback,
  saveWithPreview,
  trust,
  row,
  button,
} from "./console-common.js";
let selected = null,
  pending = false,
  activePayload = null;
const fields = {
  name: "client-name",
  lab_id: "client-lab",
  ipv4: "client-ip",
  ssh_port: "client-port",
  ssh_username: "client-user",
  auth_method: "client-method",
  notes: "client-notes",
};
function setPending(value) {
  pending = value;
  $("#client-fields").disabled = value;
}
function erase() {
  for (const id of ["client-password", "client-key", "client-passphrase"])
    $("#" + id).value = "";
}
function method() {
  const key = $("#client-method").value === "private_key";
  for (const id of ["client-key", "client-passphrase"]) {
    $("#" + id).hidden = !key;
    $(`label[for="${id}"]`).hidden = !key;
  }
  $("#client-password").hidden = key;
  $('label[for="client-password"]').hidden = key;
  erase();
}
function edit(item) {
  if (pending) return;
  selected = item;
  erase();
  $("#client-form").reset();
  if (item)
    for (const [key, id] of Object.entries(fields))
      $("#" + id).value = item[key] ?? "";
  text(
    $("#client-heading"),
    item
      ? `Edit ${item.name} · version ${item.metadata_version}`
      : "New Client",
  );
  $("#client-toggle").hidden = !item;
  if (item)
    text(
      $("#client-toggle"),
      item.enabled ? "Disable Client" : "Enable Client",
    );
  method();
}
async function load() {
  const items = await allPages("/clients?include_disabled=true");
  $("#client-list").replaceChildren();
  for (const item of items)
    row($("#client-list"), [
      `${item.name} · ${Array.from($("#client-lab").options).find((option) => Number(option.value) === item.lab_id)?.textContent || "Lab #" + item.lab_id}`,
      `${item.ipv4}:${item.ssh_port}`,
      `${item.enabled ? "Enabled" : "Disabled"} · ${item.auth_method} · ${item.credential_configured ? "Configured" : "No credential"}`,
      item.notes || "—",
      button("Edit", () => edit(item)),
    ]);
  return items;
}
$("#client-method").onchange = method;
$("#new-client").onclick = () => edit(null);
$("#reload-clients").onclick = (event) =>
  busy(event.currentTarget, async () => {
    if (pending) return;
    setPending(true);
    try {
      const items = await load();
      setPending(false);
      edit(items.find((c) => c.id === selected?.id) || null);
    } finally {
      setPending(false);
    }
  });
$("#client-form").onsubmit = (event) => {
  event.preventDefault();
  busy(event.submitter, async () => {
    if (pending) return;
    setPending(true);
    const data = Object.fromEntries(
      Object.entries(fields).map(([key, id]) => [key, $("#" + id).value]),
    );
    activePayload = data;
    data.lab_id = Number(data.lab_id);
    data.ssh_port = Number(data.ssh_port);
    const secret = $(
      data.auth_method === "private_key" ? "#client-key" : "#client-password",
    ).value;
    if (secret) data.secret = secret;
    if ($("#client-passphrase").value)
      data.passphrase = $("#client-passphrase").value;
    erase();
    try {
      const changed = selected
        ? Object.keys(fields).filter((k) => data[k] !== selected[k])
        : Object.keys(fields);
      const connectionChanged =
        !selected ||
        data.secret !== undefined ||
        changed.some((k) =>
          ["ipv4", "ssh_port", "ssh_username", "auth_method"].includes(k),
        );
      let saved;
      if (!connectionChanged) {
        const patch = { expected_version: selected.metadata_version };
        for (const k of changed) patch[k] = data[k];
        saved = await saveWithPreview(
          `/clients/${selected.id}`,
          "PATCH",
          patch,
        );
      } else {
        if (selected) {
          data.client_id = selected.id;
          data.expected_version = selected.metadata_version;
        }
        let validation = await api("/client-validations", "POST", data);
        if (!validation.validated) {
          await trust(
            validation.challenge,
            `${data.name} · ${data.ipv4}:${data.ssh_port}`,
          );
          data.trust_challenge_id = validation.challenge.challenge_id;
          validation = await api("/client-validations", "POST", data);
        }
        if (!validation.validated)
          throw new Error("Trust changed again; review and resubmit.");
        saved = selected
          ? await saveWithPreview(`/clients/${selected.id}`, "PATCH", {
              expected_version: selected.metadata_version,
              validation_id: validation.validation_id,
            })
          : await api("/clients", "POST", {
              validation_id: validation.validation_id,
            });
      }
      setPending(false);
      edit(saved);
      await load();
      text(
        $("#console-feedback"),
        "Client saved after required validation. Stored secrets remain non-viewable.",
      );
    } finally {
      setPending(false);
      delete data.secret;
      delete data.passphrase;
      activePayload = null;
      erase();
    }
  });
};
$("#client-toggle").onclick = (event) =>
  busy(event.currentTarget, async () => {
    if (!selected) return;
    const saved = await saveWithPreview(`/clients/${selected.id}`, "PATCH", {
      expected_version: selected.metadata_version,
      enabled: !selected.enabled,
    });
    edit(saved);
    await load();
    text(
      $("#console-feedback"),
      `Client ${saved.enabled ? "enabled" : "disabled"}.`,
    );
  });
edit(null);
load().catch(feedback);
window.addEventListener("pagehide", () => {
  erase();
  if (activePayload) {
    delete activePayload.secret;
    delete activePayload.passphrase;
    activePayload = null;
  }
});
