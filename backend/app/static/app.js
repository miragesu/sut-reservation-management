'use strict';
(() => {
  const form = document.getElementById('filters');
  if (!form) return;
  const content = document.getElementById('dashboard-content');
  const feedback = document.getElementById('refresh-status');
  let view = 'card';
  let pending = false;
  let generation = 0;
  const applyView = () => {
    content.querySelectorAll('.card-layout').forEach(node => { node.hidden = view !== 'card'; });
    content.querySelectorAll('.table-layout').forEach(node => { node.hidden = view !== 'table'; });
    ['card', 'table'].forEach(name => document.getElementById(`${name}-view`).setAttribute('aria-pressed', String(view === name)));
  };
  ['card', 'table'].forEach(name => document.getElementById(`${name}-view`).addEventListener('click', () => { view = name; applyView(); }));
  const params = () => {
    const result = new URLSearchParams(new FormData(form));
    [...result.entries()].forEach(([key, value]) => { if (!value) result.delete(key); });
    return result;
  };
  const initial = new URLSearchParams(location.search);
  initial.forEach((value, key) => { if (form.elements.namedItem(key)) form.elements.namedItem(key).value = value; });
  const refresh = async () => {
    if (pending) return;
    pending = true;
    const requested = generation;
    try {
      const response = await fetch(`/dashboard/fragment?${params()}`, {headers: {'Accept': 'text/html'}});
      if (!response.ok || response.redirected) throw new Error('Refresh failed');
      const html = await response.text();
      if (requested !== generation) return;
      // HTML is our authenticated, autoescaped Jinja fragment; never build markup from user data in JS.
      content.innerHTML = html;
      applyView();
      feedback.textContent = `Updated ${new Intl.DateTimeFormat('en-GB', {timeZone: 'Asia/Taipei', dateStyle: 'short', timeStyle: 'medium'}).format(new Date())} (Asia/Taipei) · Refreshes every 30 seconds`;
      feedback.classList.remove('text-danger');
    } catch {
      feedback.textContent = 'Data may be stale. Refresh failed; retrying every 30 seconds. Sign in again if your session expired.';
      feedback.classList.add('text-danger');
    } finally {
      pending = false;
      if (requested !== generation) refresh();
    }
  };
  form.addEventListener('submit', event => { event.preventDefault(); generation++; history.replaceState(null, '', `/?${params()}`); refresh(); });
  // Cancel stale responses if the user has unsaved filter edits.
  form.addEventListener('input', () => { generation++; });
  setInterval(refresh, 30000);
  if (initial.size) refresh();
})();
