// Progressive enhancement only: every page is rendered by Python and works without this file.
// Adds: start-up sequence, IST clock, smooth in-place updates, Play animation, toasts,
// keyboard control, map coordinate readout, count-up figures and advisory approvals.
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const store = {
    get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage blocked */ } },
  };
  let playing = null;

  // ------------------------------------------------------------ start-up sequence
  function boot() {
    const el = $("#boot");
    if (!el) return;
    const forced = new URLSearchParams(location.search).has("intro");
    let seen = false;
    try { seen = sessionStorage.getItem("tapmaan.booted") === "1"; } catch { /* ignore */ }
    if (seen && !forced) return;
    el.hidden = false;
    document.body.style.overflow = "hidden";
    const items = $$("li", el), bar = $(".progress i", el), enter = $("[data-enter]", el);
    let i = 0;
    const step = () => {
      if (i < items.length) {
        items[i].classList.add("on");
        i += 1;
        bar.style.width = (i / items.length) * 100 + "%";
        setTimeout(step, 330);
      } else {
        enter.classList.add("on");
        enter.focus();
      }
    };
    setTimeout(step, 450);
    const close = () => {
      try { sessionStorage.setItem("tapmaan.booted", "1"); } catch { /* ignore */ }
      el.classList.add("gone");
      document.body.style.overflow = "";
      setTimeout(() => el.remove(), 800);
      countUp(document);
    };
    enter.addEventListener("click", close);
    $("[data-skip]", el).addEventListener("click", close);
    addEventListener("keydown", function esc(ev) {
      if (ev.key === "Escape" || (ev.key === "Enter" && enter.classList.contains("on"))) { close(); removeEventListener("keydown", esc); }
    });
    embers($("#embers", el));
  }

  // rising heat embers behind the start-up card
  function embers(canvas) {
    const ctx = canvas.getContext("2d");
    const colours = ["#c0661d", "#a8431f", "#d9a441", "#8e2a1e"];
    let w, h, parts = [];
    const size = () => { w = canvas.width = innerWidth; h = canvas.height = innerHeight; };
    size();
    addEventListener("resize", size);
    for (let k = 0; k < 90; k++) parts.push(spawn(true));
    function spawn(anywhere) {
      return { x: Math.random() * w, y: anywhere ? Math.random() * h : h + 10, r: 1 + Math.random() * 2.6,
               v: .25 + Math.random() * .7, drift: Math.random() * Math.PI * 2, c: colours[(Math.random() * colours.length) | 0],
               a: .25 + Math.random() * .45 };
    }
    (function frame() {
      if (!canvas.isConnected) return;
      ctx.clearRect(0, 0, w, h);
      parts.forEach((p, i) => {
        p.y -= p.v;
        p.drift += .02;
        p.x += Math.sin(p.drift) * .35;
        ctx.globalAlpha = p.a * Math.min(1, p.y / h + .2);
        ctx.fillStyle = p.c;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
        if (p.y < -10) parts[i] = spawn(false);
      });
      requestAnimationFrame(frame);
    })();
  }

  // ------------------------------------------------------------ clock
  function clock() {
    const el = $("[data-clock]");
    if (!el) return;
    const f = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
    const tick = () => { el.textContent = f.format(new Date()) + " IST"; };
    tick();
    setInterval(tick, 1000);
  }

  // ------------------------------------------------------------ count-up figures
  function countUp(root) {
    $$(".kpi .v, .stat .v", root).forEach((el) => {
      const m = el.textContent.trim().match(/^([+-]?)(\d+(?:\.\d+)?)(.*)$/);
      if (!m || el.dataset.counted) return;
      el.dataset.counted = "1";
      const target = parseFloat(m[2]), dec = (m[2].split(".")[1] || "").length, t0 = performance.now();
      const run = (now) => {
        const k = Math.min(1, (now - t0) / 900), eased = 1 - Math.pow(1 - k, 3);
        el.textContent = m[1] + (target * eased).toFixed(dec) + m[3];
        if (k < 1) requestAnimationFrame(run);
      };
      requestAnimationFrame(run);
    });
  }

  // ------------------------------------------------------------ in-place updates
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
      if (playing) $$(".map-wrap.scanning", live).forEach((w) => w.classList.remove("scanning"));
      const pill = $("[data-pill-text]", live), target = $("[data-pill]");
      if (pill && target) target.lastChild.textContent = pill.dataset.pillText;
      bind(live);
      if (playing) toasts(live);
    } catch {
      location.href = href;
    } finally {
      live.classList.remove("busy");
    }
  }

  function toasts(root) {
    const holder = $("#toasts"), src = $("[data-transitions]", root);
    if (!holder || !src) return;
    JSON.parse(src.dataset.transitions || "[]").slice(0, 3).forEach((t, i) => {
      setTimeout(() => {
        const el = document.createElement("div");
        el.className = "toast" + (t.up ? "" : " down");
        el.textContent = `${t.up ? "▲" : "▼"} ${t.city}: ${t.from.toLowerCase()} → ${t.to.toLowerCase()}`;
        holder.appendChild(el);
        setTimeout(() => el.remove(), 3200);
        while (holder.children.length > 4) holder.firstChild.remove();
      }, i * 160);
    });
  }

  function formHref(form) {
    const params = new URLSearchParams(new FormData(form));
    for (const [k, v] of [...params]) if (!v) params.delete(k);
    return (form.getAttribute("action") || location.pathname) + "?" + params.toString();
  }

  function stop() {
    if (playing) clearInterval(playing);
    playing = null;
    $$("[data-play]").forEach((b) => (b.textContent = "▶ Play"));
  }

  function stepDate(delta) {
    const r = $("#live form[data-live-form] input[type=range]");
    if (!r) return false;
    const dates = JSON.parse(r.dataset.dates), next = +r.value + delta;
    if (next < 0 || next >= dates.length) return false;
    r.value = next;
    r.dispatchEvent(new Event("input"));
    r.form.querySelector("input[name=date]").value = dates[next];
    swap(formHref(r.form));
    return true;
  }

  function togglePlay() {
    const r = $("#live form[data-live-form] input[type=range]");
    if (!r) return;
    if (playing) { stop(); return; }
    if (+r.value >= JSON.parse(r.dataset.dates).length - 1) { r.value = 0; }
    playing = setInterval(() => { if (!stepDate(1)) stop(); }, 1000);
    $$("[data-play]").forEach((b) => (b.textContent = "❚❚ Pause"));
  }

  function bind(root = document) {
    $$("#live a[data-nav]", root).forEach((a) => a.addEventListener("click", (ev) => {
      if (ev.metaKey || ev.ctrlKey) return;
      ev.preventDefault();
      stop();
      swap(a.href);
    }));
    $$("[data-autosubmit]", root).forEach((el) => el.addEventListener("change", () => {
      const form = el.form;
      if (form.closest("#live")) swap(formHref(form)); else form.submit();
    }));
    $$("form[data-live-form] input[type=range]", root).forEach((range) => {
      const form = range.form, dates = JSON.parse(range.dataset.dates), label = $(".date-label", form);
      range.addEventListener("input", () => {
        const d = new Date(dates[+range.value] + "T00:00:00");
        label.textContent = d.toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short", year: "numeric" });
      });
      range.addEventListener("change", () => {
        stop();
        form.querySelector("input[name=date]").value = dates[+range.value];
        if (form.closest("#live")) swap(formHref(form)); else form.submit();
      });
      const play = $("[data-play]", form);
      if (play) {
        if (playing) play.textContent = "❚❚ Pause";
        play.addEventListener("click", togglePlay);
      }
    });
    $$("tr[data-href]", root).forEach((tr) => tr.addEventListener("click", () => { location.href = tr.dataset.href; }));
    $$("#map .stn", root).forEach((a) => {
      a.addEventListener("mousemove", (ev) => tip(a.dataset.tip, ev.clientX, ev.clientY));
      a.addEventListener("mouseleave", hideTip);
    });
    readout(root);
    approvals(root);
  }

  // ------------------------------------------------------------ map coordinate readout
  function readout(root) {
    const svg = $("#map", root), out = svg && $(".readout", svg.parentElement);
    if (!svg || !out) return;
    const lon0 = +svg.dataset.lon0, lat1 = +svg.dataset.lat1, kx = +svg.dataset.kx, k = +svg.dataset.k;
    const pt = svg.createSVGPoint();
    svg.addEventListener("mousemove", (ev) => {
      pt.x = ev.clientX; pt.y = ev.clientY;
      const p = pt.matrixTransform(svg.getScreenCTM().inverse());
      out.hidden = false;
      out.textContent = `${(lat1 - p.y / k).toFixed(2)}°N  ${(lon0 + p.x / kx).toFixed(2)}°E`;
    });
    svg.addEventListener("mouseleave", () => { out.hidden = true; });
  }

  function tip(text, x, y) {
    const t = $("#tooltip");
    const [head, ...rest] = text.split(" · ");
    t.innerHTML = "<b></b><div></div>";
    t.firstChild.textContent = head;
    t.lastChild.textContent = rest.join(" · ");
    t.hidden = false;
    t.style.left = Math.min(x + 14, innerWidth - t.offsetWidth - 8) + "px";
    t.style.top = Math.min(y + 14, innerHeight - t.offsetHeight - 8) + "px";
  }
  function hideTip() { $("#tooltip").hidden = true; }

  // ------------------------------------------------------------ human-in-the-loop approvals
  function approvals(root) {
    const decisions = store.get("tapmaan.approvals", {});
    $$("[data-adv]", root).forEach((card) => {
      const id = card.dataset.adv, status = $("[data-status]", card);
      const paint = () => {
        const s = decisions[id] || card.dataset.default;
        status.textContent = s;
        status.className = "status " + s;
        card.classList.toggle("decided", s === "APPROVED" || s === "REJECTED");
      };
      paint();
      const set = (s) => { decisions[id] = s; store.set("tapmaan.approvals", decisions); paint(); };
      $("[data-approve]", card)?.addEventListener("click", () => set("APPROVED"));
      $("[data-reject]", card)?.addEventListener("click", () => set("REJECTED"));
    });
    $$("[data-queue]", root).forEach((el) => {
      if (el.textContent.trim() !== "DRAFT") { el.className = "status AUTO"; el.textContent = "AUTO"; return; }
      const prefix = el.dataset.queue + "-";
      const decided = Object.entries(decisions).filter(([k]) => k.startsWith(prefix));
      const approved = decided.filter(([, v]) => v === "APPROVED").length;
      if (approved >= 4) { el.textContent = "APPROVED"; el.className = "status APPROVED"; }
      else if (decided.length) { el.textContent = `${approved}/4 APPROVED`; el.className = "status DRAFT"; }
      else el.className = "status DRAFT";
    });
  }

  // ------------------------------------------------------------ keyboard
  addEventListener("keydown", (ev) => {
    if (ev.target.closest("input, textarea, select") || $("#boot:not([hidden]):not(.gone)")) return;
    if (!$("#live")) return;
    if (ev.key === "ArrowRight") { stop(); stepDate(1); ev.preventDefault(); }
    else if (ev.key === "ArrowLeft") { stop(); stepDate(-1); ev.preventDefault(); }
    else if (ev.key === " ") { togglePlay(); ev.preventDefault(); }
    else if (/^[0-5]$/.test(ev.key)) {
      const link = $$("#live .map-tools .seg")[0]?.children[+ev.key];
      if (link) { stop(); swap(link.href); }
    }
  });

  addEventListener("popstate", () => { if ($("#live")) swap(location.href, false); });
  boot();
  clock();
  bind();
  if (!$("#boot") || $("#boot").hidden) countUp(document);
})();
