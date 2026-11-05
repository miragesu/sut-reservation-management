import { $, api, text, friendly } from "./console-common.js";
const node = $("#console-detail-summary");
async function refresh() {
  try {
    const data = await api(`/suts/${Number(node.dataset.sutId)}/connections`);
    text(
      node,
      `UART: ${data.uart.client_id && data.uart.tmux_session ? (data.uart.client.enabled ? "Configured" : "Client Disabled") : "Not Configured"} · BMC SSH: ${data.bmc.ipv4 ? "Configured (port 22)" : "Not Configured"}. Use Edit Connection / History to update each transport.`,
    );
  } catch (error) {
    text(node, friendly(error));
  }
}
refresh();
setInterval(refresh, 30000);
