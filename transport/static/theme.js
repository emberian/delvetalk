'use strict';
// Display preference only; the page reads fine without this script.
try {
  const root = document.documentElement, key = 'delvetalk.theme';
  const saved = localStorage.getItem(key);
  if (saved === 'light' || saved === 'dark') root.dataset.theme = saved;
  document.addEventListener('DOMContentLoaded', () => {
    const b = document.getElementById('theme-toggle');
    if (!b) return;
    b.hidden = false;
    b.addEventListener('click', () => {
      const dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
      root.dataset.theme = dark ? 'light' : 'dark';
      try { localStorage.setItem(key, root.dataset.theme); } catch (e) { /* storage unavailable */ }
    });
  });
} catch (e) { /* storage unavailable; system palette applies */ }
