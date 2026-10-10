/*
  Pages d'authentification : comportements communs (fichier statique, compatible CSP stricte).
  Ce script ne lit, ne stocke et n'écrit jamais les mots de passe ni les codes de vérification.
*/
(function () {
  'use strict';

  /* ---- Afficher / masquer un mot de passe ---- */
  function initialiserBasculeMdp() {
    document.querySelectorAll('[data-afficher-mdp]').forEach(function (bouton) {
      var champ = document.getElementById(bouton.getAttribute('data-afficher-mdp'));
      if (!champ) return;
      bouton.addEventListener('click', function () {
        var visible = champ.type === 'password';
        champ.type = visible ? 'text' : 'password';
        bouton.setAttribute('aria-pressed', visible ? 'true' : 'false');
        bouton.setAttribute('aria-label', visible ? 'Masquer le mot de passe' : 'Afficher le mot de passe');
      });
    });
  }

  /* ---- Avertissement « Verr. Maj activé » ---- */
  function initialiserMajuscules() {
    var alerte = document.querySelector('[data-majuscules]');
    var champ = document.getElementById('id_password');
    if (!alerte || !champ) return;
    function verifier(evenement) {
      if (typeof evenement.getModifierState !== 'function') return;
      alerte.hidden = !evenement.getModifierState('CapsLock');
    }
    champ.addEventListener('keydown', verifier);
    champ.addEventListener('keyup', verifier);
    champ.addEventListener('blur', function () { alerte.hidden = true; });
  }

  /* ---- État de chargement des boutons d'envoi (anti double envoi) ---- */
  function initialiserChargement() {
    document.querySelectorAll('form[data-chargement]').forEach(function (formulaire) {
      var bouton = formulaire.querySelector('[data-libelle-chargement]');
      if (!bouton) return;
      var texte = bouton.querySelector('.bouton__texte') || bouton;
      var libelleInitial = texte.textContent;

      function restaurer() {
        formulaire.removeAttribute('data-envoi');
        bouton.disabled = false;
        bouton.classList.remove('is-chargement');
        bouton.removeAttribute('aria-busy');
        texte.textContent = libelleInitial;
      }

      formulaire.addEventListener('submit', function (evenement) {
        if (formulaire.hasAttribute('data-envoi')) {
          evenement.preventDefault();
          return;
        }
        formulaire.setAttribute('data-envoi', '1');
        texte.textContent = bouton.getAttribute('data-libelle-chargement');
        bouton.classList.add('is-chargement');
        bouton.setAttribute('aria-busy', 'true');
        // Désactivation après l'événement : le formulaire part normalement.
        window.setTimeout(function () { bouton.disabled = true; }, 0);
      });
      // Retour arrière : le navigateur peut rendre la page figée en état « chargement ».
      window.addEventListener('pageshow', function (evenement) { if (evenement.persisted) restaurer(); });
    });
  }

  /* ---- Bouton « Copier » ---- */
  function initialiserCopie() {
    document.querySelectorAll('[data-copier]').forEach(function (bouton) {
      bouton.addEventListener('click', function () {
        var source = document.querySelector(bouton.getAttribute('data-copier'));
        if (!source) return;
        var texte = 'value' in source && source.tagName === 'INPUT'
          ? source.value
          : Array.prototype.map.call(source.children, function (e) { return e.textContent.trim(); }).join('\n');
        var libelle = bouton.querySelector('[data-copier-texte]');
        function confirmer(message) {
          if (!libelle) return;
          var avant = libelle.textContent;
          libelle.textContent = message;
          window.setTimeout(function () { libelle.textContent = avant === message ? 'Copier' : avant; }, 2000);
        }
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(texte).then(function () { confirmer('Copié'); }, function () { confirmer('Copie impossible'); });
        } else {
          confirmer('Copie impossible');
        }
      });
    });
  }

  /* ---- Codes de récupération : « Continuer » après confirmation ---- */
  function initialiserConfirmationCodes() {
    var case_ = document.querySelector('[data-confirmation-codes]');
    var lien = document.querySelector('[data-continuer-codes]');
    if (!case_ || !lien) return;
    function maj() {
      lien.classList.toggle('bouton--desactive', !case_.checked);
      lien.setAttribute('aria-disabled', case_.checked ? 'false' : 'true');
    }
    lien.addEventListener('click', function (evenement) {
      if (!case_.checked) evenement.preventDefault();
    });
    case_.addEventListener('change', maj);
    maj();
  }

  /* ---- Robustesse du nouveau mot de passe ---- */
  function initialiserRobustesse() {
    var formulaire = document.querySelector('[data-mdp-form]');
    var champ = document.querySelector('[data-mdp-nouveau]');
    if (!formulaire || !champ) return;
    var email = (formulaire.getAttribute('data-email') || '').trim().toLowerCase();
    var barre = formulaire.querySelector('[data-force]');
    var annonce = formulaire.querySelector('[data-force-texte]');
    var criteres = {};
    formulaire.querySelectorAll('[data-critere]').forEach(function (li) { criteres[li.getAttribute('data-critere')] = li; });
    var libelles = ['', 'Faible', 'Moyen', 'Bon', 'Excellent'];

    function evaluer() {
      var mdp = champ.value;
      var vide = mdp.length === 0;
      var etat = {
        longueur: mdp.length >= 12,
        chiffres: !vide && !/^\d+$/.test(mdp),
        email: !vide && mdp.toLowerCase() !== email
      };
      Object.keys(etat).forEach(function (cle) {
        if (criteres[cle]) criteres[cle].classList.toggle('ok', etat[cle]);
      });
      var niveau = 0;
      if (mdp.length >= 8) niveau += 1;
      if (etat.longueur && etat.chiffres && etat.email) niveau += 1;
      if (/[a-z]/.test(mdp) && /[A-Z]/.test(mdp) && /\d/.test(mdp)) niveau += 1;
      if (/[^A-Za-z0-9]/.test(mdp) && mdp.length >= 14) niveau += 1;
      if (!(etat.longueur && etat.chiffres && etat.email)) niveau = Math.min(niveau, 1);
      if (barre) barre.setAttribute('data-niveau', String(niveau));
      if (annonce) annonce.textContent = niveau ? 'Robustesse : ' + libelles[niveau] : '';
    }
    champ.addEventListener('input', evaluer);
    evaluer();
  }

  initialiserBasculeMdp();
  initialiserMajuscules();
  initialiserChargement();
  initialiserCopie();
  initialiserConfirmationCodes();
  initialiserRobustesse();
}());
