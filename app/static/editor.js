(function () {
  function insertTable() {
    var rows = parseInt(prompt("Jumlah baris?", "2"), 10);
    var cols = parseInt(prompt("Jumlah kolom?", "2"), 10);
    if (!rows || !cols || rows < 1 || cols < 1) return;
    var html = '<table style="border-collapse:collapse;width:100%;margin:1em 0;">';
    for (var r = 0; r < rows; r++) {
      html += "<tr>";
      for (var c = 0; c < cols; c++) html += '<td style="border:1px solid #000;padding:4px 8px;">&nbsp;</td>';
      html += "</tr>";
    }
    html += "</table><p><br></p>";
    document.execCommand("insertHTML", false, html);
  }

  function insertBox() {
    document.execCommand(
      "insertHTML",
      false,
      '<div style="border:1px solid #000;padding:8px;margin:1em 0;">Kotak baru -- isi teks di sini</div><p><br></p>'
    );
  }

  window.initEditorToolbar = function (toolbarSelector, editableSelector) {
    var toolbar = document.querySelector(toolbarSelector);
    var editable = document.querySelector(editableSelector);
    if (!toolbar || !editable) return;

    toolbar.addEventListener("click", function (ev) {
      var btn = ev.target.closest("button[data-cmd], button[data-action]");
      if (!btn) return;
      ev.preventDefault();
      editable.focus();
      if (btn.dataset.cmd) {
        document.execCommand(btn.dataset.cmd, false, btn.dataset.value || null);
      } else if (btn.dataset.action === "table") {
        insertTable();
      } else if (btn.dataset.action === "box") {
        insertBox();
      }
    });
  };
})();
