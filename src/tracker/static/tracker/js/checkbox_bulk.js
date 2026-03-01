document.addEventListener("htmx:afterSettle", wireBulkCheck);
document.addEventListener("DOMContentLoaded", wireBulkCheck);

function wireBulkCheck() {
  const master = document.getElementById("check-all");
  if (!master) return;
  master.onchange = (e) =>
    document.querySelectorAll(".row-check").forEach((cb) => (cb.checked = e.target.checked));
}
