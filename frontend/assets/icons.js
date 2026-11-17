/* InsaneVoice — icon system.
   One style: 24px grid, 1.7px stroke, round caps & joins, currentColor.
   Filled shapes only where the glyph is solid by nature (play, stop). */

const P = {
  grid: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/>',
  type: '<path d="M4 6.5h16"/><path d="M4 12h10"/><path d="M4 17.5h13"/><path d="M18.5 10.5v5"/><path d="M16.5 13h4"/>',
  rows: '<rect x="3.5" y="4.5" width="17" height="4" rx="1.2"/><rect x="3.5" y="11" width="17" height="4" rx="1.2"/><path d="M3.5 19.5h17"/>',
  radar: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none"/>',
  record: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="3.5" fill="currentColor" stroke="none"/>',
  stack: '<path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h10"/>',
  wand: '<path d="M5 19 15.5 8.5"/><path d="M14 4.5l.9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9z" fill="currentColor" stroke="none"/><path d="M19 13.5l.6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6z" fill="currentColor" stroke="none"/>',
  swap: '<path d="M16.5 4.5 20 8l-3.5 3.5"/><path d="M20 8H7.5"/><path d="M7.5 12.5 4 16l3.5 3.5"/><path d="M4 16h12.5"/>',
  list: '<path d="M8.5 6h11"/><path d="M8.5 12h11"/><path d="M8.5 18h11"/><circle cx="4.5" cy="6" r="1" fill="currentColor" stroke="none"/><circle cx="4.5" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="4.5" cy="18" r="1" fill="currentColor" stroke="none"/>',
  isolate: '<path d="M4 12h2.5"/><path d="M17.5 12H20"/><circle cx="12" cy="12" r="4.2"/><path d="M12 3.5v2"/><path d="M12 18.5v2"/>',
  doc: '<path d="M6.5 3.5h8L19 8v12.5h-12.5z"/><path d="M14 3.5V8.5h5"/><path d="M9 12h6"/><path d="M9 15.5h6"/>',
  video: '<rect x="3.5" y="6" width="12.5" height="12" rx="2"/><path d="M16 10.5 20.5 8v8L16 13.5"/>',
  bolt: '<path d="M13 3 5.5 13.5H11L10 21l7.5-10.5H12z"/>',
  nodes: '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M7.8 7.8 10.8 16"/><path d="M16.2 7.8 13.2 16"/>',
  clock: '<path d="12 3.5a8.5 8.5 0 1 1-8.5 8.5"/><path d="M3.5 12V7.5"/><path d="M3.5 12H8"/><path d="M12 7.5V12l3 2.5"/>',
  sliders: '<path d="M4 7.5h10"/><circle cx="17" cy="7.5" r="2.2"/><path d="M20 12H10"/><circle cx="7" cy="12" r="2.2"/><path d="M4 16.5h10"/><circle cx="17" cy="16.5" r="2.2"/>',
  help: '<circle cx="12" cy="12" r="8.5"/><path d="M9.5 9.2a2.5 2.5 0 1 1 3.6 2.3c-.8.4-1.1 1-1.1 1.8v.4"/><circle cx="12" cy="16.8" r="1" fill="currentColor" stroke="none"/>',
  play: '<path d="M8 5.5v13l10.5-6.5z" fill="currentColor" stroke="none"/>',
  stop: '<rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor" stroke="none"/>',
  download: '<path d="M12 4v10.5"/><path d="M7.5 10.5 12 15l4.5-4.5"/><path d="M5 19.5h14"/>',
  upload: '<path d="M12 15V4.5"/><path d="M7.5 9 12 4.5 16.5 9"/><path d="M5 19.5h14"/>',
  trash: '<path d="M4.5 6.5h15"/><path d="M9.5 6.5V5a1.5 1.5 0 0 1 1.5-1.5h2A1.5 1.5 0 0 1 14.5 5v1.5"/><path d="M18.5 6.5 17.5 19a2 2 0 0 1-2 1.8h-7A2 2 0 0 1 6.5 19L5.5 6.5"/><path d="M10 10.5v6"/><path d="M14 10.5v6"/>',
  mic: '<rect x="9" y="3.5" width="6" height="11" rx="3"/><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0"/><path d="M12 18v2.5"/>',
  plus: '<path d="M12 5v14"/><path d="M5 12h14"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
  close: '<path d="M6 6l12 12"/><path d="M18 6 6 18"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  arrow: '<path d="M4.5 12h14"/><path d="m13 6.5 5.5 5.5L13 17.5"/>',
  spark: '<path d="M12 3.5l1.8 5.2L19 10.5l-5.2 1.8L12 17.5l-1.8-5.2L5 10.5l5.2-1.8z"/>',
  globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17"/><path d="M12 3.5c2.7 2.7 2.7 14.3 0 17-2.7-2.7-2.7-14.3 0-17z"/>',
  waveform: '<path d="M4 10.5v3"/><path d="M8 7.5v9"/><path d="M12 4.5v15"/><path d="M16 7.5v9"/><path d="M20 10.5v3"/>',
  alert: '<path d="M12 4 21 19.5H3z"/><path d="M12 10v4"/><circle cx="12" cy="16.8" r="1" fill="currentColor" stroke="none"/>',
  info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5"/><circle cx="12" cy="7.8" r="1" fill="currentColor" stroke="none"/>',
};

export function icon(name, size = 18, cls = "") {
  const body = P[name] || P.info;
  return `<svg class="icon ${cls}" width="${size}" height="${size}" viewBox="0 0 24 24"
    fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"
    stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
}

export function iconBtnSvg(name, title = "", cls = "btn sm icon") {
  return `<button class="${cls}" title="${title}" aria-label="${title}">${icon(name, 16)}</button>`;
}
