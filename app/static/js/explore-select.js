// A11Y-2: relocated from an inline <script> in app/web/templates/
// explore.html (same behaviour, moved so app/main.py's CSP `script-src`
// no longer needs 'unsafe-inline' for this page -- see that file's own
// comment on `_CONTENT_SECURITY_POLICY`).
//
// Progressive enhancement only: /explore's compare-selection form already
// works with plain GET + checkboxes and no JavaScript at all (docs/UI.md
// "Weak connection: lightweight content" -- the core journey must not
// depend on a script loading). This just caps the selection at 3 and
// gives a live count; without it, /compare/view itself still rejects
// anything outside 2-3 pathways with a clear message.
(function () {
  var MAX = 3;
  var boxes = document.querySelectorAll(".compare-checkbox");
  var countEl = document.getElementById("selection-count");
  function update() {
    var checked = document.querySelectorAll(".compare-checkbox:checked");
    countEl.textContent = checked.length + " of " + MAX + " selected (pick 2 or 3).";
    boxes.forEach(function (box) {
      box.disabled = checked.length >= MAX && !box.checked;
    });
  }
  boxes.forEach(function (box) {
    box.addEventListener("change", update);
  });
})();
