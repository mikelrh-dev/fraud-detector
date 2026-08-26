// Progressive enhancement hub — vanilla JS, zero dependencies.
// Contract: without JS, .js class is never added and ALL content stays visible.
document.documentElement.classList.add("js");

/* ------------------------------------------------------------------
 * Reveal-on-scroll
 * ------------------------------------------------------------------ */
var revealObserver = new IntersectionObserver(
  function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) {
        entry.target.classList.add("visible");
        revealObserver.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.12 }
);
document.querySelectorAll(".reveal").forEach(function (el) {
  revealObserver.observe(el);
});

/* ------------------------------------------------------------------
 * Reading progress bar (transform-only animation)
 * ------------------------------------------------------------------ */
var progressBar = document.querySelector(".progress");
if (progressBar) {
  var ticking = false;
  var updateProgress = function () {
    var doc = document.documentElement;
    var max = doc.scrollHeight - doc.clientHeight;
    var ratio = max > 0 ? Math.min(1, window.scrollY / max) : 0;
    progressBar.style.transform = "scaleX(" + ratio + ")";
    ticking = false;
  };
  window.addEventListener(
    "scroll",
    function () {
      if (!ticking) {
        ticking = true;
        requestAnimationFrame(updateProgress);
      }
    },
    { passive: true }
  );
  updateProgress();
}

/* ------------------------------------------------------------------
 * Estimated reading time (injected into chapter kicker)
 * ------------------------------------------------------------------ */
(function () {
  var kicker =
    document.querySelector(".chapter-num") || document.querySelector(".hero-kicker");
  var main = document.querySelector("main");
  if (!kicker || !main) return;
  var words = (main.innerText || "").trim().split(/\s+/).length;
  var minutes = Math.max(1, Math.round(words / 190));
  var badge = document.createElement("span");
  badge.className = "read-time";
  badge.setAttribute("aria-hidden", "true");
  badge.textContent = " · " + minutes + " min";
  kicker.appendChild(badge);
})();

/* ------------------------------------------------------------------
 * Mobile hamburger navigation
 * ------------------------------------------------------------------ */
var burger = document.querySelector(".nav-burger");
if (burger) {
  burger.addEventListener("click", function () {
    var open = document.body.classList.toggle("nav-open");
    burger.setAttribute("aria-expanded", open ? "true" : "false");
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && document.body.classList.contains("nav-open")) {
      document.body.classList.remove("nav-open");
      burger.setAttribute("aria-expanded", "false");
    }
  });
}

/* ------------------------------------------------------------------
 * Keyboard chapter navigation (ArrowLeft / ArrowRight)
 * Skips when focus is inside form controls.
 * Pager links are identified explicitly (the "next" link carries
 * .pager-next) so ArrowRight never falls back to the previous
 * chapter on the last page, and ArrowLeft only fires when a true
 * PREV link exists.
 * ------------------------------------------------------------------ */
document.addEventListener("keydown", function (e) {
  if (e.altKey || e.ctrlKey || e.metaKey) return;
  var tag = document.activeElement ? document.activeElement.tagName : "";
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
  var prev = document.querySelector(".pager a:not(.pager-next)");
  var next = document.querySelector(".pager a.pager-next");
  if (e.key === "ArrowLeft" && prev) {
    window.location.href = prev.getAttribute("href");
  } else if (e.key === "ArrowRight" && next) {
    window.location.href = next.getAttribute("href");
  }
});

/* ------------------------------------------------------------------
 * Interactive architecture diagram (ch-01)
 * Nodes carry data-tip + optional data-target; hover shows tooltip,
 * click navigates to the matching chapter.
 * ------------------------------------------------------------------ */
(function () {
  var svg = document.querySelector("#architecture-diagram");
  if (!svg || svg.dataset.enhanced) return;
  svg.dataset.enhanced = "1";

  // Animated flow on every solid connector line (dashed DLQ line keeps its own pattern)
  svg.querySelectorAll("line").forEach(function (l) {
    if (!l.getAttribute("stroke-dasharray")) l.classList.add("flow-line");
  });

  var tip = document.createElement("div");
  tip.className = "diagram-tip";
  tip.setAttribute("role", "tooltip");
  tip.hidden = true;
  document.body.appendChild(tip);

  function moveTip(e) {
    var pad = 14;
    var x = e.clientX + pad;
    var y = e.clientY + pad;
    var w = tip.offsetWidth;
    var h = tip.offsetHeight;
    if (x + w > window.innerWidth - 8) x = e.clientX - w - pad;
    if (y + h > window.innerHeight - 8) y = e.clientY - h - pad;
    tip.style.left = x + "px";
    tip.style.top = y + "px";
  }

  svg.querySelectorAll(".diagram-node").forEach(function (node) {
    node.classList.add("enhanced");
    node.setAttribute("tabindex", "0");
    node.setAttribute("role", "button");
    if (!node.getAttribute("data-target")) {
      node.setAttribute("aria-label", node.getAttribute("data-tip") || "");
    }
    node.addEventListener("mouseenter", function (e) {
      tip.textContent = node.getAttribute("data-tip") || "";
      tip.hidden = false;
      moveTip(e);
    });
    node.addEventListener("mousemove", moveTip);
    node.addEventListener("mouseleave", function () {
      tip.hidden = true;
    });
    node.addEventListener("focus", function () {
      var box = node.getBoundingClientRect();
      tip.textContent = node.getAttribute("data-tip") || "";
      tip.hidden = false;
      tip.style.left = Math.min(box.left, window.innerWidth - tip.offsetWidth - 8) + "px";
      tip.style.top = (box.bottom + 10) + "px";
    });
    node.addEventListener("blur", function () {
      tip.hidden = true;
    });
    node.addEventListener("click", function () {
      var target = node.getAttribute("data-target");
      if (target) window.location.href = target;
    });
    node.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " ") return;
      e.preventDefault();
      var target = node.getAttribute("data-target");
      if (target) window.location.href = target;
    });
  });
})();

/* ------------------------------------------------------------------
 * Threshold policy playground (ch-04)
 * Uses REAL precomputed bins (SCORE_BINS) + REAL tier config.
 * ------------------------------------------------------------------ */
(function () {
  var root = document.getElementById("threshold-playground");
  if (!root || typeof SCORE_BINS === "undefined" || root.dataset.enhanced) return;
  root.dataset.enhanced = "1";

  // Real production config (src/core/config.py threshold_tiers)
  var TIERS = [
    { max: 1000, threshold: 70, key: "low" },
    { max: 10000, threshold: 50, key: "medium" },
    { max: 50000, threshold: 45, key: "high" },
    { max: Infinity, threshold: 40, key: "critical" },
  ];
  var L = {
    en: {
      amount: "Amount", tier: "Tier", threshold: "Fraud threshold",
      band: "Review band from", tiers: { low: "low", medium: "medium", high: "high", critical: "critical" },
      legit: "legitimate", fraud: "fraud", hint: "Drag the slider — watch the decision policy react.",
    },
    es: {
      amount: "Monto", tier: "Tier", threshold: "Umbral de fraude",
      band: "Banda de revisión desde", tiers: { low: "bajo", medium: "medio", high: "alto", critical: "crítico" },
      legit: "legítimas", fraud: "fraude", hint: "Mueve el slider — mira reaccionar la política de decisión.",
    },
  }[document.documentElement.lang === "es" ? "es" : "en"];

  var slider = root.querySelector(".pg-slider");
  var outAmount = root.querySelector(".pg-amount");
  var outTier = root.querySelector(".pg-tier");
  var outThreshold = root.querySelector(".pg-threshold");
  var outBand = root.querySelector(".pg-band");
  var chart = root.querySelector(".pg-chart");
  if (!slider || !chart) return;

  var NS = "http://www.w3.org/2000/svg";
  var W = 720, H = 220, PAD_L = 8, PAD_B = 22;
  var plotW = W - PAD_L - 8, plotH = H - PAD_B - 8;
  var maxCount = Math.max.apply(null, SCORE_BINS.legit.concat(SCORE_BINS.fraud));
  var n = SCORE_BINS.legit.length;
  var binW = plotW / n;

  function barX(i) { return PAD_L + i * binW; }

  // Draw histogram once (blue behind red, shared y scale)
  var gBars = document.createElementNS(NS, "g");
  for (var pass = 0; pass < 2; pass++) {
    var arr = pass === 0 ? SCORE_BINS.legit : SCORE_BINS.fraud;
    var fill = pass === 0 ? "#3b82f6" : "#ef4444";
    var op = pass === 0 ? 0.55 : 0.6;
    for (var i = 0; i < n; i++) {
      if (!arr[i]) continue;
      var h = (arr[i] / maxCount) * plotH;
      var r = document.createElementNS(NS, "rect");
      r.setAttribute("x", (barX(i) + 0.5).toFixed(2));
      r.setAttribute("y", (H - PAD_B - h).toFixed(2));
      r.setAttribute("width", Math.max(1, binW - 1).toFixed(2));
      r.setAttribute("height", h.toFixed(2));
      r.setAttribute("fill", fill);
      r.setAttribute("opacity", op);
      gBars.appendChild(r);
    }
  }
  chart.appendChild(gBars);

  // Review band (yellow shade) + threshold line (moves with slider)
  var bandRect = document.createElementNS(NS, "rect");
  bandRect.setAttribute("y", 8);
  bandRect.setAttribute("height", plotH);
  bandRect.setAttribute("fill", "#eab308");
  bandRect.setAttribute("opacity", 0.14);
  chart.appendChild(bandRect);

  var line = document.createElementNS(NS, "line");
  line.setAttribute("y1", 8);
  line.setAttribute("y2", H - PAD_B);
  line.setAttribute("stroke", "#f1f5f9");
  line.setAttribute("stroke-width", 1.5);
  line.setAttribute("stroke-dasharray", "5 4");
  chart.appendChild(line);

  var scoreAxis = document.createElementNS(NS, "text");
  scoreAxis.setAttribute("x", W - 8);
  scoreAxis.setAttribute("y", H - 6);
  scoreAxis.setAttribute("text-anchor", "end");
  scoreAxis.setAttribute("font-size", 10);
  scoreAxis.setAttribute("fill", "#94a3b8");
  scoreAxis.setAttribute("font-family", "monospace");
  scoreAxis.textContent = "ml_score 0–100";
  chart.appendChild(scoreAxis);

  function fmt(n2) { return n2.toLocaleString(document.documentElement.lang === "es" ? "es-ES" : "en-US"); }

  function update() {
    var amount = Number(slider.value);
    var tier = null;
    for (var i = 0; i < TIERS.length; i++) {
      if (amount <= TIERS[i].max) { tier = TIERS[i]; break; }
    }
    var thr = tier.threshold;
    var bandFrom = thr * 0.75;
    outAmount.textContent = "$" + fmt(amount);
    outTier.textContent = L.tiers[tier.key];
    outThreshold.textContent = "≥ " + thr;
    outBand.textContent = "≥ " + bandFrom.toFixed(1);

    var thrX = PAD_L + (thr / 100) * plotW;
    var bandX = PAD_L + (bandFrom / 100) * plotW;
    line.setAttribute("x1", thrX.toFixed(2));
    line.setAttribute("x2", thrX.toFixed(2));
    bandRect.setAttribute("x", bandX.toFixed(2));
    bandRect.setAttribute("width", Math.max(0, thrX - bandX).toFixed(2));
  }

  slider.addEventListener("input", update);
  update();
})();
