/*
  Saisie du code à 6 chiffres : UN SEUL vrai champ (compatible collage et autoremplissage),
  présenté comme 6 cases. Le code n'est jamais stocké côté navigateur ni écrit dans les journaux.
  Anneau de validité : aide visuelle seulement, la validation reste faite par le serveur.
*/
(function () {
  'use strict';

  var LONGUEUR = 6;

  function initialiserOtp(conteneur) {
    var champ = conteneur.querySelector('.otp-input');
    var cases = Array.prototype.slice.call(conteneur.querySelectorAll('.otp-cases > span:not(.otp-tiret)'));
    var formulaire = champ && champ.form;
    if (!champ || cases.length !== LONGUEUR || !formulaire) return;

    var envoiPlanifie = false;

    function nettoyer(valeur) { return valeur.replace(/\D/g, '').slice(0, LONGUEUR); }

    function dessiner() {
      var valeur = champ.value;
      var actif = Math.min(valeur.length, LONGUEUR - 1);
      var focus = document.activeElement === champ;
      cases.forEach(function (c, i) {
        c.textContent = valeur.charAt(i);
        c.classList.toggle('is-plein', i < valeur.length);
        c.classList.toggle('is-actif', focus && i === actif && !envoiPlanifie);
      });
    }

    function placerCurseurALaFin() {
      var fin = champ.value.length;
      try { champ.setSelectionRange(fin, fin); } catch (e) { /* type non supporté */ }
    }

    function envoyerApresVague() {
      if (envoiPlanifie) return;
      envoiPlanifie = true;
      champ.readOnly = true;
      window.setTimeout(function () {
        cases.forEach(function (c, i) {
          window.setTimeout(function () { c.classList.add('is-validation'); }, i * 40);
        });
        window.setTimeout(function () {
          if (typeof formulaire.requestSubmit === 'function') formulaire.requestSubmit();
          else formulaire.submit();
        }, cases.length * 40 + 60);
      }, 150);
    }

    function surSaisie() {
      if (envoiPlanifie) return;
      conteneur.classList.remove('otp--erreur');
      var propre = nettoyer(champ.value);
      if (propre !== champ.value) champ.value = propre;
      placerCurseurALaFin();
      dessiner();
      if (propre.length === LONGUEUR) envoyerApresVague();
    }

    champ.addEventListener('input', surSaisie);
    champ.addEventListener('focus', function () { placerCurseurALaFin(); dessiner(); });
    champ.addEventListener('blur', dessiner);
    champ.addEventListener('click', placerCurseurALaFin);
    champ.addEventListener('select', placerCurseurALaFin);
    champ.addEventListener('paste', function (evenement) {
      var presse = evenement.clipboardData && evenement.clipboardData.getData('text');
      if (presse == null) return; // l'événement « input » fera le nettoyage
      evenement.preventDefault();
      champ.value = nettoyer(presse);
      surSaisie();
    });
    // Clic sur une case : on remet le focus sur le vrai champ (qui recouvre déjà les cases).
    conteneur.addEventListener('pointerdown', function () { window.setTimeout(function () { champ.focus(); }, 0); });

    conteneur.classList.add('otp--js');
    if (conteneur.hasAttribute('data-erreur')) {
      conteneur.classList.add('otp--erreur');
      champ.value = '';
    }
    dessiner();
    champ.focus();
    // Un autoremplissage SMS/gestionnaire peut remplir le champ avant l'exécution du script.
    if (champ.value) surSaisie();
  }

  /* ---- Anneau de validité (tranches TOTP de 30 s) ---- */
  function initialiserAnneau(anneau) {
    var arc = anneau.querySelector('[data-anneau-arc]');
    var texte = anneau.querySelector('[data-anneau-secondes]');
    if (!arc || !texte) return;
    var PERIODE = 30;
    var circonference = 2 * Math.PI * 17;
    arc.setAttribute('stroke-dasharray', circonference.toFixed(2));
    var derniere = -1;

    function maj() {
      var maintenant = Date.now() / 1000;
      var ecoule = maintenant % PERIODE;
      var restant = Math.ceil(PERIODE - ecoule);
      var tranche = Math.floor(maintenant / PERIODE);
      arc.setAttribute('stroke-dashoffset', (circonference * (ecoule / PERIODE)).toFixed(2));
      texte.textContent = String(restant);
      if (derniere !== -1 && tranche !== derniere) {
        anneau.classList.remove('is-pulse');
        void anneau.offsetWidth; // relance l'animation de pulsation
        anneau.classList.add('is-pulse');
      }
      derniere = tranche;
    }
    maj();
    window.setInterval(maj, 1000);
  }

  document.querySelectorAll('[data-otp]').forEach(initialiserOtp);
  document.querySelectorAll('[data-anneau]').forEach(initialiserAnneau);
}());
