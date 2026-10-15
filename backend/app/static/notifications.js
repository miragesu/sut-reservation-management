'use strict';
(() => {
  const button = document.getElementById('desktop-opt-in');
  if (!button) return;
  const status = document.getElementById('notification-status');
  const count = document.getElementById('unread-count');
  const supported = window.isSecureContext && typeof window.Notification === 'function';
  const key = `sut-notifications-${document.body.dataset.userId}`;
  const delivered = new Set();
  let cursor = null, pending = false, queued = false, enabled = false;
  try { cursor = Number(sessionStorage.getItem(key)) || null; enabled = sessionStorage.getItem(`${key}-enabled`) === 'yes'; } catch { /* Storage is optional. */ }
  const save = () => { try { sessionStorage.setItem(key, String(cursor)); sessionStorage.setItem(`${key}-enabled`, enabled ? 'yes' : 'no'); } catch { /* In-memory deduplication remains active. */ } };
  const describe = () => {
    button.disabled = !supported || Notification.permission === 'denied';
    status.textContent = !supported ? 'Desktop notifications require a supported browser and HTTPS. In-app Inbox remains available.' : Notification.permission === 'denied' ? 'Desktop notifications are blocked. Use Inbox or change browser settings.' : enabled ? 'Desktop notifications enabled while this page is open.' : 'In-app notifications are available in Inbox.';
  };
  describe();
  button.addEventListener('click', async () => {
    if (!supported) return;
    try { enabled = (await Notification.requestPermission()) === 'granted'; save(); describe(); }
    catch { status.textContent = 'Desktop permission unavailable. Use Inbox.'; }
  });
  const refresh = async () => {
    if (pending) { queued = true; return; }
    pending = true;
    try {
      const response = await fetch('/api/v1/notifications?page_size=100');
      if (!response.ok || response.redirected) throw new Error();
      const data = await response.json();
      count.textContent = String(data.unread_count);
      count.setAttribute('aria-label', `${data.unread_count} unread notifications`);
      const preview = document.getElementById('notification-preview');
      const rows = data.items.slice(0, 5).map(item => {
        const row = document.createElement('p');
        const link = document.createElement('a');
        link.href = '/notifications';
        link.textContent = item.message;
        row.append(link, document.createTextNode(' · ' + new Date(item.created_at).toLocaleString('en-GB', {timeZone:'Asia/Taipei'}) + ' (Asia/Taipei) · ' + (item.read_at ? 'Read' : 'Unread')));
        return row;
      });
      if (!rows.length) { const empty = document.createElement('p'); empty.textContent = 'No notifications.'; rows.push(empty); }
      preview.replaceChildren(...rows);
      let desktopFailed = false;
      // First visit establishes a baseline; never replay historical notifications.
      if (cursor !== null && supported && enabled && Notification.permission === 'granted') {
        // Fetch every intervening page so bursts over 100 cannot silently disappear.
        let page = 1, items;
        do {
          const next = await fetch(`/api/v1/notifications?after_id=${cursor}&through_id=${data.latest_id}&page=${page}&page_size=100`);
          if (!next.ok) throw new Error();
          items = (await next.json()).items;
          for (const item of items) {
            if (!item.read_at && item.id > cursor && item.id <= data.latest_id && !delivered.has(item.id)) {
              try { const notice = new Notification('SUT Coordination', {body: 'You have a new coordination notification. Open Inbox for details.', tag: `sut-${item.id}`}); delivered.add(item.id); notice.onclick = () => { window.focus(); location.href = '/notifications'; }; } catch { desktopFailed = true; }
            }
          }
          page++;
        } while (items.length === 100);
      }
      describe();
      if (desktopFailed) status.textContent = 'Desktop delivery unavailable. Use Inbox.';
      cursor = Math.max(cursor || 0, data.latest_id);
      save();
    } catch { status.textContent = 'Notifications may be stale. Retrying in 30 seconds; Inbox remains available.'; }
    finally { pending = false; if (queued) { queued = false; refresh(); } }
  };
  document.addEventListener('coordination:changed', refresh);
  refresh();
  setInterval(refresh, 30000);
})();
