'use strict';
(() => {
  const node = document.getElementById('quick-modal');
  if (!node) return;
  const modal = new bootstrap.Modal(node);
  const el = id => document.getElementById(`quick-${id}`);
  const form = el('form');
  let action, identity, trigger, pending = false, generation = 0;
  const feedback = message => { el('feedback').textContent = message; };
  const updateEligibility = () => {
    const state = el('detail').querySelector('[data-registrations-open]');
    el('submit').disabled = pending || Boolean(state && state.dataset.registrationsOpen !== 'true');
  };
  document.addEventListener('click', async event => {
    const button = event.target.closest('[data-quick-action]');
    if (!button || pending) return;
    trigger = button;
    const request = ++generation;
    action = button.dataset.quickAction;
    identity = button.dataset.quickSut;
    form.reset();
    el('conflict').hidden = true;
    el('detail').replaceChildren();
    el('title').textContent = `${action[0].toUpperCase() + action.slice(1)} · ${button.dataset.sutName}`;
    el('full-detail').href = `/suts/${identity}`;
    el('duration').hidden = !['claim', 'queue'].includes(action);
    el('minutes').required = ['claim', 'queue'].includes(action);
    el('minutes').min = action === 'claim' ? '0.000001' : '1';
    el('minutes').step = action === 'claim' ? 'any' : '1';
    el('times').hidden = action !== 'reserve';
    ['start', 'end'].forEach(name => { el(name).required = action === 'reserve'; });
    el('purpose-group').hidden = !['claim', 'reserve'].includes(action);
    el('purpose').required = action === 'reserve';
    form.hidden = action === 'detail';
    el('submit').disabled = true;
    el('state-status').textContent = '';
    feedback('Loading current state…');
    modal.show();
    try {
      const response = await fetch(`/suts/${identity}/activity`);
      if (!response.ok || response.redirected) throw new Error('Cannot load current state. Close and retry or sign in again.');
      const html = await response.text();
      if (request !== generation) return;
      // Authenticated autoescaped server fragment; forms live outside this region.
      el('detail').innerHTML = html;
      feedback('State is advisory; eligibility is checked again when you submit.');
      updateEligibility();
    } catch (error) { if (request === generation) feedback(error.message); }
  });
  node.addEventListener('hidden.bs.modal', () => { generation++; (trigger && trigger.isConnected ? trigger : document.querySelector('#card-view[aria-pressed="true"], #table-view[aria-pressed="true"]')).focus(); });
  node.addEventListener('shown.bs.modal', () => { (form.hidden ? el('full-detail') : form.querySelector('input:required')).focus(); });
  // Keep a pending submission visible until its authoritative result arrives.
  node.addEventListener('hide.bs.modal', event => { if (pending) event.preventDefault(); });
  setInterval(async () => {
    if (!node.classList.contains('show') || pending) return;
    const request = generation;
    try {
      const response = await fetch(`/suts/${identity}/activity`);
      if (!response.ok || response.redirected) throw new Error();
      const html = await response.text();
      if (request === generation) { el('detail').innerHTML = html; updateEligibility(); el('state-status').textContent = 'State refreshed (Asia/Taipei): ' + new Date().toLocaleTimeString('en-GB', {timeZone:'Asia/Taipei'}); }
    } catch { if (request === generation) el('state-status').textContent = 'State may be stale. Retrying in 30 seconds; your input is retained.'; }
  }, 30000);
  document.querySelectorAll('[data-duration-preset]').forEach(button => button.addEventListener('click', () => { el('minutes').value = button.dataset.durationPreset; }));
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (pending || !form.reportValidity()) return;
    pending = true;
    el('submit').disabled = true;
    feedback('Submitting…');
    const minutes = Number(el('minutes').value);
    let url = `/api/v1/suts/${identity}/${action === 'claim' ? 'claim' : 'queue'}`;
    let data = action === 'claim' ? {duration_minutes: minutes, purpose: el('purpose').value, acknowledge_reservation_conflict: el('ack').checked} : {requested_duration_minutes: minutes};
    if (action === 'reserve') {
      url = '/api/v1/reservations';
      // Inputs explicitly represent Taipei, independent of the browser timezone.
      data = {sut_id: Number(identity), start_time: `${el('start').value}+08:00`, end_time: `${el('end').value}+08:00`, purpose: el('purpose').value};
    }
    try {
      const response = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]').content}, body: JSON.stringify(data)});
      const result = await response.json();
      if (!response.ok) {
        const detail = result.detail;
        if (detail && detail.code === 'reservation_conflict_confirmation_required') {
          el('conflict').hidden = false;
          el('conflicts').textContent = detail.conflicts.map(booking => `${booking.user.display_name} · ${booking.user.team} · ${booking.user.email} · ${new Date(booking.start_time).toLocaleString('en-GB', {timeZone:'Asia/Taipei'})}–${new Date(booking.end_time).toLocaleString('en-GB', {timeZone:'Asia/Taipei'})} (Asia/Taipei)`).join('; ');
          el('ack').checked = false;
          feedback(detail.message);
        } else feedback(typeof detail === 'string' ? detail : JSON.stringify(detail || result));
        el('feedback').focus();
        return;
      }
      pending = false;
      modal.hide();
      document.dispatchEvent(new Event('coordination:changed'));
    } catch { feedback('Request failed. Check current state before retrying; your input is retained.'); }
    finally { pending = false; updateEligibility(); }
  });
})();
