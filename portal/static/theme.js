'use strict';

// Run before the stylesheet under the same-origin CSP. This stores only a
// display preference; CSS follows live system changes when no override is set.
try {
  const preference = localStorage.getItem('delvetalk.theme');
  if (preference === 'light' || preference === 'dark') document.documentElement.dataset.theme = preference;
} catch { /* Storage may be unavailable; the system palette still works. */ }
