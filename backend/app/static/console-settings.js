import {
  $,
  text,
  time,
  api,
  allPages,
  busy,
  feedback,
  saveWithPreview,
  trust,
  row,
} from "./console-common.js";
const root = $("#connection-settings");
const id = Number(root.dataset.sutId),
  lab = Number(root.dataset.labId);
let current = null,
  page = 1;
function mappingLabel(value, transport) {
  if (transport === "uart")
    return value.client_id
      ? `Client #${value.client_id} · tmux ${value.tmux_session}`
      : "Not Configured";
  return value.ipv4 ? `${value.ipv4}:22` : "Not Configured";
}
async function history() {
  const value = await api(`/suts/${id}/history?page=${page}`);
  $("#mapping-history").replaceChildren();
  value.items.forEach((item) =>
    row($("#mapping-history"), [
      time(item.created_at),
      item.actor_display_name || `RD #${item.actor_id ?? "system"}`,
      item.transport,
      JSON.stringify(item.old),
      JSON.stringify(item.new),
      item.reason || "—",
    ]),
  );
  $("#history-prev").disabled = page === 1;
  $("#history-next").disabled = value.items.length < 25;
}
async function load() {
  const [mapping, clients] = await Promise.all([
    api(`/suts/${id}/connections`),
    allPages("/clients"),
  ]);
  current = mapping;
  const select = $("#client-id");
  select.replaceChildren(new Option("Select an enabled Client", ""));
  clients
    .filter((c) => c.lab_id === lab)
    .forEach((c) =>
      select.add(
        new Option(`${c.name} · ${c.ipv4}:${c.ssh_port}`, String(c.id)),
      ),
    );
  const retained = mapping.uart.client;
  if (retained && !retained.enabled) {
    const option = new Option(
      `${retained.name} · Client Disabled (retained)`,
      String(retained.id),
    );
    option.disabled = true;
    select.add(option);
  }
  select.value = mapping.uart.client_id || "";
  $("#tmux-session").value = mapping.uart.tmux_session || "";
  $("#bmc-ipv4").value = mapping.bmc.ipv4 || "";
  text(
    $("#uart-summary"),
    retained
      ? `${retained.name} · ${retained.ipv4}:${retained.ssh_port} · ${retained.enabled ? "Enabled" : "Client Disabled"} · ${retained.notes || ""} · revision ${mapping.uart.revision}`
      : "Not Configured",
  );
  text(
    $("#bmc-summary"),
    mapping.bmc.ipv4
      ? `${mapping.bmc.ipv4}:22 · revision ${mapping.bmc.revision}`
      : "Not Configured",
  );
  $("#trust-uart").disabled = !retained;
  $("#trust-bmc").disabled = !mapping.bmc.ipv4;
  await history();
}
async function save(mode, clear = false) {
  if (!current) return;
  const data = {
    expected_revision: current[mode].revision,
    reason: $("#" + mode + "-reason").value,
    ...(clear
      ? { clear: true }
      : mode === "uart"
        ? {
            client_id: Number($("#client-id").value),
            tmux_session: $("#tmux-session").value,
          }
        : { ipv4: $("#bmc-ipv4").value }),
  };
  await saveWithPreview(`/suts/${id}/${mode}`, "PUT", data);
  await load();
  text(
    $("#console-feedback"),
    "Connection saved. Affected sessions require a new manual Connect.",
  );
}
for (const mode of ["uart", "bmc"]) {
  $("#" + mode + "-settings").addEventListener("submit", (event) => {
    event.preventDefault();
    busy(event.submitter, () => save(mode));
  });
  $("#clear-" + mode).onclick = (event) =>
    busy(event.currentTarget, () => save(mode, true));
  $("#trust-" + mode).onclick = (event) =>
    busy(event.currentTarget, async () => {
      const target =
        mode === "uart"
          ? { client_id: current.uart.client_id }
          : { sut_id: id };
      const challenge = await api("/trust/challenges", "POST", target);
      await trust(
        challenge,
        mode === "uart"
          ? `${current.uart.client.name} · ${current.uart.client.ipv4}:${current.uart.client.ssh_port}`
          : `${current.bmc.ipv4}:22`,
      );
      await load();
      text(
        $("#console-feedback"),
        "Host Key trust updated; affected sessions require manual Connect.",
      );
    });
}
$("#reload-connections").onclick = (event) => busy(event.currentTarget, load);
$("#history-prev").onclick = () => {
  if (page > 1) {
    page--;
    history().catch(feedback);
  }
};
$("#history-next").onclick = () => {
  page++;
  history().catch(feedback);
};
load().catch(feedback);
