'use strict';
(() => {
  const scroll = document.querySelector('.calendar-scroll');
  if (!scroll) return;
  const events = [...scroll.querySelectorAll('.calendar-event')];
  const grid = scroll.querySelector('.calendar-grid');
  if (grid.classList.contains('calendar-week')) {
    const columns = [...grid.querySelectorAll('.calendar-day-track')].map(day => {
      const lanes = Math.max(1, ...[...day.querySelectorAll('.calendar-event')].map(event => Number(event.dataset.lanes)));
      return `minmax(${Math.max(200, lanes * 170)}px, 1fr)`;
    });
    // Busy days get enough width to keep simultaneous SUT names readable.
    grid.style.gridTemplateColumns = `80px ${columns.join(' ')}`;
  }
  events.forEach(event => {
    const top = Number(event.dataset.top);
    const height = Number(event.dataset.height);
    const lanes = Number(event.dataset.lanes);
    const lane = Number(event.dataset.lane);
    // Set numeric geometry via CSSOM; no inline styles or untrusted markup are evaluated.
    event.style.top = `${top / 60 * 112}px`;
    event.style.height = `${height / 60 * 112}px`;
    event.style.left = `calc(${lane / lanes * 100}% + 3px)`;
    event.style.width = `calc(${100 / lanes}% - 6px)`;
  });
  const first = events.length ? Math.min(...events.map(event => Number(event.dataset.top))) / 60 : 8;
  scroll.scrollTop = Math.max(0, first - 1) * 112;
  const line = document.createElement('div');
  line.className = 'calendar-now-line';
  line.setAttribute('aria-hidden', 'true');
  const label = document.createElement('span');
  label.className = 'calendar-now-label';
  const hours = scroll.querySelector('.calendar-hours');
  const clock = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'
  });
  const updateNow = () => {
    const parts = Object.fromEntries(clock.formatToParts(new Date()).map(part => [part.type, part.value]));
    const today = `${parts.year}-${parts.month}-${parts.day}`;
    const tracks = [...grid.querySelectorAll('.calendar-day-track')];
    const headings = [...grid.querySelectorAll('.calendar-day-heading')];
    const track = tracks.find(day => day.dataset.day === today);
    tracks.forEach((day, index) => {
      day.classList.toggle('is-today', day === track);
      headings[index].classList.toggle('is-today', day === track);
    });
    if (!track) { line.remove(); label.remove(); return; }
    const top = (Number(parts.hour) * 60 + Number(parts.minute) + Number(parts.second) / 60) / 60 * 112;
    line.style.top = `${top}px`;
    label.style.top = `${top}px`;
    label.textContent = `${parts.hour}:${parts.minute}`;
    label.setAttribute('aria-label', `Current time ${label.textContent}`);
    track.append(line);
    hours.append(label);
  };
  updateNow();
  setInterval(updateNow, 60000);
})();
