/*
  Écran « Habilitations » (admin groupe) : amélioration progressive, aucune dépendance.
  - bouton « Copier » (mot de passe provisoire) ;
  - formulaire Vue Groupe : les champs dépendants sont désactivés tant qu'ils ne servent à rien
    (Vue Groupe non autorisée, ou portée « toutes les sociétés »).
  Sans JavaScript, tout reste utilisable : le serveur ignore ce qui n'est pas pertinent.
  Aucun mot de passe ni code n'est stocké dans le navigateur.
*/
(function () {
  "use strict";

  /* ---------- Copier ---------- */
  document.addEventListener("click", function (evt) {
    var bouton = evt.target.closest("[data-copier]");
    if (!bouton) { return; }
    var source = document.querySelector(bouton.getAttribute("data-copier"));
    if (!source) { return; }
    var texte = "value" in source && source.tagName === "INPUT" ? source.value : source.textContent.trim();
    var libelle = bouton.querySelector("[data-copier-texte]") || bouton;
    var avant = libelle.textContent;
    function confirmer(message) {
      libelle.textContent = message;
      window.setTimeout(function () { libelle.textContent = avant; }, 2000);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(texte).then(function () { confirmer("Copié"); }, function () { confirmer("Copie impossible"); });
    } else {
      confirmer("Copie impossible");
    }
  });

  /* ---------- Formulaire Vue Groupe ---------- */
  function mettreAJourVueGroupe(zone) {
    var autoriser = zone.querySelector("input[name=autoriser]");
    var toutes = zone.querySelector("input[name=portee][value=toutes]");
    if (!autoriser) { return; }
    var actif = autoriser.checked;
    Array.prototype.forEach.call(zone.querySelectorAll("input:not([name=autoriser]), select"), function (champ) {
      var estSociete = champ.name === "societes";
      champ.disabled = !actif || (estSociete && toutes && toutes.checked);
    });
  }

  function initialiser() {
    Array.prototype.forEach.call(document.querySelectorAll(".hab-groupe"), mettreAJourVueGroupe);
  }
  document.addEventListener("DOMContentLoaded", initialiser);
  // En phase de capture : l'état des champs est à jour avant que HTMX ne relise le formulaire (aperçu en direct).
  document.addEventListener("change", function (evt) {
    var zone = evt.target.closest && evt.target.closest(".hab-groupe");
    if (zone) { mettreAJourVueGroupe(zone); }
  }, true);
})();
