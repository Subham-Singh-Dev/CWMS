(function () {
  function rowFor(name) {
    return document.querySelector('#id_' + name)?.closest('.form-row, .field-box, div[id*="' + name + '"]');
  }

  function syncRows() {
    var type = document.getElementById('id_employment_type');
    var pf = document.getElementById('id_pf_applicable');
    var esic = document.getElementById('id_esic_applicable');
    var names = ['pf_applicable', 'esic_applicable', 'pf_rate', 'esic_rate'];
    var show = type && type.value === 'PERMANENT';

    names.forEach(function (n) {
      var row = rowFor(n);
      if (row) row.style.display = show ? '' : 'none';
    });

    if (!show) {
      if (pf) pf.checked = false;
      if (esic) esic.checked = false;
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    var type = document.getElementById('id_employment_type');
    syncRows();
    if (type) type.addEventListener('change', syncRows);
  });
})();
