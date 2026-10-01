// Progressive enhancement only: every page already works without this file.
// - swaps the live part of a page without a full reload (pages are still rendered by Python)
// - date slider + "Play" animation through the 2024 heatwave
// - human-in-the-loop approvals stored in this browser
// - richer map tooltips and clickable table rows
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  let playing = null;

  async function swap(href, push = true) {
    const live = $("#live");
    if (!live) { location.href = href; return; }
    const u = new URL(href, location.href);
    u.searchParams.set("partial", "1");
    live.classList.add("busy");
    try {
      const r = await fetch(u);
      if (!r.ok) throw new Error(r.status);
      live.innerHTML = await r.text();
      u.searchParams.delete("partial");
      if (push) history.pushState({}, "", u.pathname + u.search);
      bind(live);
    } catch {
      location.href = href;
    } finally {
      live.classList.remove("busy");
    }
  }

  function formHref(form) {
    const params = new URLSearchParams(new FormData(form));
    for (const [k, v] of [...params]) if (!v) params.delete(k);
    return (form.getAttribute("action") || location.pathname) + "?" + params.toString();
  }

  function bind(root = document) {
    // segmented links inside the live region
    $$("#live a[data-nav]", root).forEach((a) => a.addEventListener("click", (ev) => {
      if (ev.metaKey || ev.ctrlKey) return;
      ev.preventDefault();
      stop();
      swap(a.href);
    }));
    // auto-submitting selects / date inputs
    $$("[data-autosubmit]", root).forEach((el) => el.addEventListener("change", () => {
      const form = el.form;
      if (form.closest("#live")) swap(formHref(form)); else form.submit();
    }));
    // date slider
    $$("form[data-live-form] input[type=range]", root).forEach((range) => {
      const form = range.form;
      const dates = JSON.parse(range.dataset.dates);
      const label = $(".date-label", form);
      const hidden = form.querySelector("input[name=date]");
      const go = () => {
        hidden.value = dates[+range.value];
        if (form.closest("#live")) swap(formHref(form)); else form.submit();
      };
      range.addEventListener("input", () => {
        const d = new Date(dates[+range.value] + "T00:00:00");
        label.textContent = d.toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short", year: "numeric" });
      });
      range.addEventListener("change", () => { stop(); go(); });
      const play = $("[data-play]", form);
      if (play) {
        if (playing) play.textContent = "❚❚ Pause";
        play.addEventListener("click", () => {
          if (playing) { stop(); return; }
          if (+range.value >= dates.length - 1) range.value = 0;
          playing = setInterval(async () => {
            const r = $("#live form[data-live-form] input[type=range]");
            if (!r || +r.value >= dates.length - 1) { stop(); return; }
            r.value = +r.value + 1;
            r.dispatchEvent(new Event("input"));
            r.form.querySelector("input[name=date]").value = dates[+r.value];
            await swap(formHref(r.form));
          }, 900);
          play.textContent = "❚❚ Pause";
        });
      }
    });
    // clickable table rows
    $$("tr[data-href]", root).forEach((tr) => tr.addEventListener("click", () => { location.href = tr.dataset.href; }));
    // map tooltips
    $$("#map .stn", root).forEach((a) => {
      a.addEventListener("mousemove", (ev) => tip(a.dataset.tip, ev.clientX, ev.clientY));
      a.addEventListener("mouseleave", hideTip);
    });
    approvals(root);
  }

  function stop() {
    if (playing) clearInterval(playing);
    playing = null;
    $$("[data-play]").forEach((b) => (b.textContent = "▶ Play"));
  }

  function tip(text, x, y) {
    const t = $("#tooltip");
    const [head, ...rest] = text.split(" · ");
    t.innerHTML = `<b></b><div class="small muted"></div>`;
    t.firstChild.textContent = head;
    t.lastChild.textContent = rest.join(" · ");
    t.hidden = false;
    t.style.left = Math.min(x + 14, innerWidth - t.offsetWidth - 8) + "px";
    t.style.top = Math.min(y + 14, innerHeight - t.offsetHeight - 8) + "px";
  }
  function hideTip() { $("#tooltip").hidden = true; }

  // ---- human-in-the-loop approvals (per browser) ----
  const KEY = "tapmaan.approvals";
  const load = () => { try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch { return {}; } };
  const save = (v) => { try { localStorage.setItem(KEY, JSON.stringify(v)); } catch { /* storage blocked */ } };

  function approvals(root) {
    const store = load();
    $$("[data-adv]", root).forEach((card) => {
      const id = card.dataset.adv;
      const status = $("[data-status]", card);
      const paint = () => {
        const s = store[id] || card.dataset.default;
        status.textContent = s;
        status.className = "status " + s;
        card.classList.toggle("decided", s === "APPROVED" || s === "REJECTED");
      };
      paint();
      const set = (s) => { store[id] = s; save(store); paint(); };
      $("[data-approve]", card)?.addEventListener("click", () => set("APPROVED"));
      $("[data-reject]", card)?.addEventListener("click", () => set("REJECTED"));
    });
    // warnings table: summarise decisions per station
    $$("[data-queue]", root).forEach((el) => {
      if (el.textContent.trim() !== "DRAFT") { el.classList.add("AUTO-APPROVED"); el.textContent = "AUTO"; return; }
      const prefix = el.dataset.queue + "-";
      const decided = Object.entries(store).filter(([k]) => k.startsWith(prefix));
      const approved = decided.filter(([, v]) => v === "APPROVED").length;
      if (approved >= 4) { el.textContent = "APPROVED"; el.className = "status APPROVED"; }
      else if (decided.length) { el.textContent = `${approved}/4 APPROVED`; el.className = "status DRAFT"; }
      else el.className = "status DRAFT";
    });
  }

  addEventListener("popstate", () => { if ($("#live")) swap(location.href, false); });
  bind();
})();
