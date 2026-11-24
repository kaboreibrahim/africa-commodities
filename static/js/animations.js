/* ==========================================================================
   Animations de l'interface (sans bibliothèque, compatible CSP : aucun style inline
   dans le HTML, uniquement des classes et la propriété style posée en JavaScript).
   - Cascade : cartes, indicateurs et lignes de tableau apparaissent l'un après l'autre.
   - Compteurs : les montants (« 1 000 000 F », « 45 % », « 12 ») défilent jusqu'à leur valeur.
   - Jauges : les barres <progress> se remplissent depuis zéro.
   Les anneaux et barres Chart.js s'animent dans graphiques.js.
   Tout est désactivé si l'utilisateur a demandé à réduire les animations.
   Rejoué au chargement de la page et sur chaque contenu remplacé par HTMX.
   ========================================================================== */
(function () {
  "use strict";

  var CASCADE = ".param, .kpi, .carte, .cadre-tableau tbody tr, .onglets, .page-entete";
  var COMPTEURS = ".kpi__v, .param__v, .legende__valeur, .legende__pct, [data-compteur]";
  var PAS_CASCADE = 60;          // ms entre deux éléments
  var MAX_CASCADE = 18;          // au-delà, les éléments apparaissent ensemble
  var DUREE_COMPTEUR = 1100;     // ms
  var DUREE_JAUGE = 1100;        // ms

  function mouvementReduit() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function adoucir(t) { return 1 - Math.pow(1 - t, 4); } // easeOutQuart

  /* ---------- Cascade ---------- */
  var observateur = null;

  function reveler(el) {
    el.classList.add("anim-visible");
    window.setTimeout(function () {
      el.classList.remove("anim-pret", "anim-visible");
      el.style.transitionDelay = "";
    }, 900 + (parseInt(el.style.transitionDelay, 10) || 0));
  }

  function cascade(racine) {
    var elements = Array.prototype.slice.call(racine.querySelectorAll(CASCADE));
    if (racine.matches && racine.matches(CASCADE)) { elements.unshift(racine); }
    elements = elements.filter(function (el) { return !el.dataset.animCascade; });
    if (!elements.length) { return; }

    if (!observateur && "IntersectionObserver" in window) {
      observateur = new IntersectionObserver(function (entrees) {
        entrees.forEach(function (e) {
          if (e.isIntersecting) { observateur.unobserve(e.target); reveler(e.target); }
        });
      }, { rootMargin: "0px 0px -40px 0px", threshold: 0.05 });
    }

    elements.forEach(function (el, i) {
      el.dataset.animCascade = "1";
      el.classList.add("anim-pret");
      el.style.transitionDelay = Math.min(i, MAX_CASCADE) * PAS_CASCADE + "ms";
    });
    // Force le navigateur à appliquer l'état de départ avant la transition.
    void document.body.offsetHeight;
    elements.forEach(function (el) {
      if (observateur) { observateur.observe(el); } else { reveler(el); }
    });
  }

  /* ---------- Compteurs ---------- */
  // Premier nombre du texte, au format français : « 1 000 000 », « 12,5 », « -3 ».
  var MOTIF = /-?\d{1,3}(?:[\s  ]\d{3})+(?:,\d+)?|-?\d+(?:,\d+)?/;

  function lireNombre(txt) {
    var m = MOTIF.exec(txt);
    if (!m) { return null; }
    var brut = m[0];
    var valeur = parseFloat(brut.replace(/[\s  ]/g, "").replace(",", "."));
    if (!isFinite(valeur)) { return null; }
    var decimales = (brut.split(",")[1] || "").length;
    return { valeur: valeur, debut: m.index, fin: m.index + brut.length, decimales: decimales };
  }

  function compter(el) {
    if (el.dataset.animCompteur || el.children.length) { return; } // texte simple uniquement
    var texte = el.textContent;
    var n = lireNombre(texte);
    if (!n || n.valeur === 0) { return; }
    el.dataset.animCompteur = "1";

    var avant = texte.slice(0, n.debut), apres = texte.slice(n.fin);
    var format = new Intl.NumberFormat("fr-FR", {
      minimumFractionDigits: n.decimales, maximumFractionDigits: n.decimales
    });
    var depart = null;

    function image(t) {
      if (depart === null) { depart = t; }
      var p = Math.min((t - depart) / DUREE_COMPTEUR, 1);
      el.textContent = avant + format.format(n.valeur * adoucir(p)) + apres;
      if (p < 1) { window.requestAnimationFrame(image); } else { el.textContent = texte; }
    }
    el.textContent = avant + format.format(0) + apres;
    window.requestAnimationFrame(image);
  }

  /* ---------- Jauges <progress> ---------- */
  function remplir(barre) {
    if (barre.dataset.animJauge) { return; }
    var cible = parseFloat(barre.getAttribute("value"));
    if (!isFinite(cible) || cible <= 0) { return; }
    barre.dataset.animJauge = "1";
    var depart = null;
    function image(t) {
      if (depart === null) { depart = t; }
      var p = Math.min((t - depart) / DUREE_JAUGE, 1);
      barre.value = cible * adoucir(p);
      if (p < 1) { window.requestAnimationFrame(image); } else { barre.value = cible; }
    }
    barre.value = 0;
    window.requestAnimationFrame(image);
  }

  /* ---------- Lancement ---------- */
  function animer(racine) {
    if (mouvementReduit() || !racine || !racine.querySelectorAll) { return; }
    cascade(racine);
    Array.prototype.forEach.call(racine.querySelectorAll(COMPTEURS), compter);
    if (racine.matches && racine.matches(COMPTEURS)) { compter(racine); }
    Array.prototype.forEach.call(racine.querySelectorAll("progress"), remplir);
  }

  document.addEventListener("DOMContentLoaded", function () {
    animer(document.getElementById("contenu") || document.body);
  });
  // Contenu remplacé par HTMX : seuls les nouveaux éléments sont animés.
  document.addEventListener("htmx:afterSettle", function (e) {
    animer(e.detail && e.detail.elt ? e.detail.elt : document.body);
  });
})();
