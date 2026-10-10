// stview client-side behaviour
(function () {
  function renderIcons() {
    if (window.feather) feather.replace({ 'stroke-width': 2 });
  }

  // Theme toggle (persisted in localStorage)
  const toggle = document.getElementById('themeToggle');
  if (toggle) {
    toggle.addEventListener('click', function () {
      const root = document.documentElement;
      const next = root.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-bs-theme', next);
      localStorage.setItem('stview-theme', next);
    });
  }

  // Click a data cell to expand/collapse long values
  document.addEventListener('click', function (e) {
    const td = e.target.closest('.table-data td');
    if (td && !e.target.closest('a,button')) td.classList.toggle('expanded');
  });

  // Copy-to-clipboard buttons: <button data-copy="text">
  document.addEventListener('click', function (e) {
    const btn = e.target.closest('[data-copy]');
    if (!btn) return;
    navigator.clipboard.writeText(btn.getAttribute('data-copy')).then(function () {
      const original = btn.innerHTML;
      btn.innerHTML = '<i data-feather="check"></i>';
      renderIcons();
      setTimeout(function () { btn.innerHTML = original; renderIcons(); }, 1200);
    });
  });

  // Simple client-side filter: <input data-filter="#tableId">
  document.querySelectorAll('[data-filter]').forEach(function (input) {
    const target = document.querySelector(input.getAttribute('data-filter'));
    if (!target) return;
    input.addEventListener('input', function () {
      const q = input.value.trim().toLowerCase();
      target.querySelectorAll('tbody tr').forEach(function (tr) {
        tr.style.display = !q || tr.textContent.toLowerCase().includes(q) ? '' : 'none';
      });
    });
  });

  // Ctrl/Cmd+Enter submits the SQL form
  const sqlForm = document.getElementById('sqlForm');
  if (sqlForm) {
    sqlForm.querySelector('textarea').addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); sqlForm.requestSubmit(); }
    });
    document.querySelectorAll('[data-sql]').forEach(function (el) {
      el.addEventListener('click', function (e) {
        e.preventDefault();
        sqlForm.querySelector('textarea').value = el.getAttribute('data-sql');
        sqlForm.requestSubmit();
      });
    });
  }

  // Drag & drop for the publish form
  const dz = document.getElementById('dropzone');
  if (dz) {
    const input = dz.querySelector('input[type=file]');
    const label = dz.querySelector('.dz-label');
    const update = function () {
      if (input.files.length) label.textContent = input.files[0].name + ' (' + Math.round(input.files[0].size / 1024) + ' KiB)';
    };
    dz.addEventListener('click', function (e) { if (e.target !== input) input.click(); });
    input.addEventListener('change', update);
    ['dragenter', 'dragover'].forEach(function (ev) { dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.add('dragover'); }); });
    ['dragleave', 'drop'].forEach(function (ev) { dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.remove('dragover'); }); });
    dz.addEventListener('drop', function (e) { input.files = e.dataTransfer.files; update(); });
  }

  // Delete confirmation: enable button only when text matches
  document.querySelectorAll('[data-confirm-input]').forEach(function (input) {
    const expected = input.getAttribute('data-confirm-input');
    const btn = input.form.querySelector('button[type=submit]');
    const sync = function () { btn.disabled = input.value !== expected; };
    input.addEventListener('input', sync); sync();
  });

  renderIcons();
})();
