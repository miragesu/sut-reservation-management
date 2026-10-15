'use strict';
(() => {
  const mine = document.getElementById('my-reservations');
  const state = document.getElementById('reservation-start-state');
  if (!mine && !state) return;
  let pending = false, leaving = false, edited = false;
  document.addEventListener('submit', () => { leaving = true; });
  document.addEventListener('input', () => { edited = true; });
  setInterval(async () => {
    if (pending || leaving) return;
    pending = true;
    try {
      if (mine) {
        const response = await fetch(location.href, {headers: {'Accept':'text/html'}});
        if (!response.ok || response.redirected) return;
        const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
        ['active-suts','my-reservations'].forEach(id => {
          const fresh = doc.getElementById(id), old = document.getElementById(id);
          if (fresh && old) old.replaceWith(fresh);
        });
      } else {
        const response = await fetch(`/api/v1/reservations/${state.dataset.bookingId}`);
        if (!response.ok || response.redirected) return;
        const data = await response.json();
        if (data.display_status !== state.dataset.currentState) {
          if (!edited) { location.reload(); return; }
          state.textContent = `${data.display_status}. Your entered estimate is retained; refresh to see updated actions.`;
          const submit = document.querySelector('form[action$="/claim"] button');
          if (submit) submit.disabled = data.display_status !== 'Ready to start';
        }
      }
    } catch { /* A transient read failure never mutates a reservation. */ }
    finally { pending = false; }
  }, 30000);
})();
