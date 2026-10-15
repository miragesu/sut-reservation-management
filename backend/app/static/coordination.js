'use strict';
(() => {
  const region = document.querySelector('[data-poll-url]');
  if (!region) return;
  const feedback = document.querySelector('[data-poll-feedback]');
  let pending = false;
  const updateControls = () => {
    const state = region.querySelector('[data-registrations-open]');
    if (state) document.querySelectorAll('form[data-registration] button').forEach(button => {
      button.disabled = state.dataset.registrationsOpen !== 'true';
    });
  };
  updateControls();
  setInterval(async () => {
    if (pending) return;
    pending = true;
    try {
      const response = await fetch(region.dataset.pollUrl, {headers: {'Accept': 'text/html'}});
      if (!response.ok || response.redirected) throw new Error('Refresh failed');
      // Only our autoescaped, authenticated read-only fragment is replaced.
      // Claim/queue/estimate forms remain outside this region with their input intact.
      region.innerHTML = await response.text();
      updateControls();
      feedback.textContent = 'Updated (Asia/Taipei): ' + new Intl.DateTimeFormat('en-GB', {timeZone: 'Asia/Taipei', timeStyle: 'medium'}).format(new Date());
      feedback.classList.remove('text-danger');
    } catch {
      feedback.textContent = 'Data may be stale. Retrying in 30 seconds; sign in again if your session expired.';
      feedback.classList.add('text-danger');
    } finally { pending = false; }
  }, 30000);
})();
