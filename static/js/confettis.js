/* ==========================================================================
   Confettis : environ 380 confettis aux couleurs de la société, pendant ~4,5 s,
   sur le canvas plein écran #confetti, puis nettoyage. Rien si l'utilisateur
   a demandé à réduire les animations (prefers-reduced-motion).
   ========================================================================== */
(function () {
  "use strict";

  var DUREE = 4500;
  var COULEURS_FIXES = ["#2F6FB0", "#B8A21E", "#8E5BB5", "#F4C430", "#FFFFFF"];
  var enCours = false;

  function mouvementReduit() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  window.lancerConfettis = function (couleursSociete) {
    if (mouvementReduit() || enCours) { return false; }
    var canvas = document.getElementById("confetti");
    if (!canvas || !canvas.getContext) { return false; }
    enCours = true;
    canvas.hidden = false;
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    var ctx = canvas.getContext("2d");
    var couleurs = (couleursSociete || []).concat(COULEURS_FIXES);
    var particules = [];
    var i;

    // Deux canons depuis les bords bas…
    for (i = 0; i < 260; i++) {
      var gauche = i % 2 === 0;
      particules.push({
        x: gauche ? 0 : canvas.width, y: canvas.height * 0.7,
        vx: (gauche ? 1 : -1) * (4 + Math.random() * 9), vy: -(9 + Math.random() * 12),
        l: 6 + Math.random() * 6, h: 8 + Math.random() * 8,
        c: couleurs[i % couleurs.length], r: Math.random() * 6, vr: (Math.random() - 0.5) * 0.3
      });
    }
    // … et une pluie depuis le haut.
    for (i = 0; i < 120; i++) {
      particules.push({
        x: Math.random() * canvas.width, y: -20 - Math.random() * 300,
        vx: (Math.random() - 0.5) * 2, vy: 2 + Math.random() * 3,
        l: 6 + Math.random() * 5, h: 8 + Math.random() * 7,
        c: couleurs[i % couleurs.length], r: Math.random() * 6, vr: (Math.random() - 0.5) * 0.3
      });
    }

    var debut = performance.now();
    function image(t) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      particules.forEach(function (p) {
        p.vy += 0.25; p.vx *= 0.99; p.x += p.vx; p.y += p.vy; p.r += p.vr;
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.r);
        ctx.fillStyle = p.c;
        ctx.fillRect(-p.l / 2, -p.h / 2, p.l, p.h * Math.abs(Math.cos(p.r * 2)));
        ctx.restore();
      });
      if (t - debut < DUREE) {
        window.requestAnimationFrame(image);
      } else {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        canvas.hidden = true;
        enCours = false;
      }
    }
    window.requestAnimationFrame(image);
    return true;
  };
})();
