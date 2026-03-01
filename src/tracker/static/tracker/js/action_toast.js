(function () {
  "use strict";

  /* -------------------------------------------------------- */
  /*  Inject CSS once                                         */
  /* -------------------------------------------------------- */
  function ensureCSS() {
    if (document.getElementById("toast-css")) return; // already there

    const style = document.createElement("style");
    style.id = "toast-css";
    style.textContent = `
      /* Slide-down while keeping horizontal center */
      @keyframes toast-in {
        from { opacity: 0; transform: translate(-50%, -50px); }
        to   { opacity: 1; transform: translate(-50%, 0); }
      }
      @keyframes toast-out {
        from { opacity: 1; }
        to   { opacity: 0; }
      }

      .toast-container {
        position: fixed;
        top: 5%;                         /* ⬆ a bit higher (was 10%) */
        left: 50%;
        transform: translate(-50%, 0);   /* stay centered X, no Y shift */
        z-index: 10000;

        min-width: 24rem;
        max-width: 90vw;
        padding: 1rem 1.5rem;

        background: rgba(17,24,39,0.95); /* gray-900/95 */
        color: #fff;
        font-size: 1.1rem;
        font-weight: 600;
        text-align: center;
        border-radius: 0.75rem;
        box-shadow: 0 10px 25px rgba(0,0,0,0.35);

        animation:
          toast-in   0.25s ease-out,
          toast-out  0.30s ease-in 3.7s forwards;
      }
    `;
    document.head.appendChild(style);
  }

  /* -------------------------------------------------------- */
  /*  Show toast                                              */
  /* -------------------------------------------------------- */
  function showToast(msg, duration = 4000) {
    ensureCSS();
    const div = document.createElement("div");
    div.className = "toast-container";
    div.textContent = msg;
    document.body.appendChild(div);
    setTimeout(() => div.remove(), duration);
  }

  /* -------------------------------------------------------- */
  /*  Hook up to HX-Trigger                                   */
  /* -------------------------------------------------------- */
  htmx.on("action-toast", (e) => {
    const { title, id } = e.detail;          // payload from Django view
    showToast(`${title} (id ${id})`);
  });
})();
