import {
  $,
  text,
  time,
  api,
  busy,
  feedback,
  row,
  button,
  ask,
} from "./console-common.js";
let page = 1;
async function options() {
  const data = await api("/admin/grant-options");
  for (const [key, id, label] of [
    ["suts", "grant-sut", (s) => `${s.name} · ${s.operational_state}`],
    ["users", "grant-user", (u) => `${u.display_name} · ${u.team}`],
  ]) {
    const node = $("#" + id);
    node.replaceChildren(new Option("Select…", ""));
    data[key].forEach((item) =>
      node.add(new Option(label(item), String(item.id))),
    );
  }
}
async function load() {
  const data = await api(`/admin/grants?page=${page}`);
  $("#grant-list").replaceChildren();
  for (const item of data.items) {
    const active =
      item.state === "active" && new Date(item.expires_at) > new Date();
    const extend = document.createElement("div");
    if (active) {
      const select = document.createElement("select");
      select.className = "form-select";
      select.setAttribute(
        "aria-label",
        `Extend ${item.display_name} grant to original creation plus`,
      );
      for (const hours of [1, 2, 4, 8, 12, 24]) {
        const expiry = new Date(
          new Date(item.created_at).getTime() + hours * 3600000,
        );
        if (expiry > new Date(item.expires_at))
          select.add(
            new Option(
              `Created + ${hours}h · ${time(expiry)}`,
              expiry.toISOString(),
            ),
          );
      }
      if (select.options.length) {
        extend.append(
          select,
          button("Extend", async () => {
            await api(`/grants/${item.id}`, "PATCH", {
              expected_revision: item.revision,
              new_expires_at: select.value,
            });
            await load();
          }),
        );
      } else text(extend, "Original +24h maximum reached");
    }
    const revoke = active
      ? button("Revoke", async () => {
          await ask(
            "Revoke maintenance grant?",
            `${item.display_name} · ${item.sut_name}. Console access will be re-evaluated immediately; unrelated rights and coordination records remain.`,
          );
          await api(`/grants/${item.id}/revoke`, "POST", {
            expected_revision: item.revision,
          });
          await load();
        })
      : "—";
    row($("#grant-list"), [
      `${item.display_name} · ${item.sut_name}`,
      time(item.created_at),
      time(item.expires_at),
      active
        ? "active"
        : item.state === "active"
          ? "expired (awaiting sweep)"
          : item.state,
      item.reason || "—",
      extend,
      revoke,
    ]);
  }
  $("#grants-prev").disabled = page === 1;
  $("#grants-next").disabled = data.items.length < 25;
}
$("#grant-form").onsubmit = (event) => {
  event.preventDefault();
  busy(event.submitter, async () => {
    await api(`/suts/${Number($("#grant-sut").value)}/grants`, "POST", {
      user_id: Number($("#grant-user").value),
      duration_hours: Number($("#grant-duration").value),
      reason: $("#grant-reason").value,
    });
    await load();
    text(
      $("#console-feedback"),
      "Grant created. Inform the RD separately; no notification was sent.",
    );
  });
};
$("#reload-grants").onclick = (event) =>
  busy(event.currentTarget, async () => {
    await options();
    await load();
  });
$("#grants-prev").onclick = () => {
  if (page > 1) {
    page--;
    load().catch(feedback);
  }
};
$("#grants-next").onclick = () => {
  page++;
  load().catch(feedback);
};
Promise.all([options(), load()]).catch(feedback);
