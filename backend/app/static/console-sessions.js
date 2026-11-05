import {
  $,
  text,
  time,
  api,
  feedback,
  row,
  link,
  busy,
} from "./console-common.js";
async function refresh() {
  const data = await api("/sessions/me");
  text($("#console-quota"), `${data.usage}/10 Console sessions`);
  $("#own-sessions").replaceChildren();
  for (const item of data.items)
    row($("#own-sessions"), [
      link(`${item.sut_name} · ${item.lab_name}`, `/suts/${item.sut_id}`),
      item.transport,
      item.mode,
      item.state,
      time(item.connected_at),
    ]);
}
$("#reload-sessions").onclick = (event) => busy(event.currentTarget, refresh);
refresh().catch(feedback);
setInterval(() => refresh().catch(feedback), 30000);
