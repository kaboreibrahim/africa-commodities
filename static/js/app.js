/* ==========================================================================
   Suivi des marges – comportements communs (aucun script inline : CSP stricte).
   - toasts (messages Django + évènement HTMX « toast ») ;
   - sélecteur de mois ;
   - boîte de dialogue de modification ;
   - célébration de l'objectif (évènement HTMX « objectifAtteint » ou message Django « objectif »).
   ========================================================================== */
(function () {
  "use strict";

  document.documentElement.classList.add("js");

  var DUREE_TOAST = 3000;

  /* ---------- Toasts ---------- */
  function pile() { return document.getElementById("toasts"); }

  function fermerToast(toast) {
    toast.classList.add("toast--sortie");
    window.setTimeout(function () { toast.remove(); }, 350);
  }

  function preparerToast(toast) {
    // Un toast avec un bouton d'action (ex. « Annuler ») reste affiché jusqu'au clic.
    if (!toast.querySelector("button")) {
      window.setTimeout(function () { fermerToast(toast); }, DUREE_TOAST);
    }
  }

  function afficherToast(message, niveau, action) {
    var conteneur = pile();
    if (!conteneur) { return; }
    var toast = document.createElement("div");
    toast.className = "toast toast--" + (niveau || "info");
    var texte = document.createElement("span");
    texte.textContent = message;
    toast.appendChild(texte);
    if (action && action.url) {
      var bouton = document.createElement("button");
      bouton.type = "button";
      bouton.className = "btn--lien";
      bouton.textContent = action.libelle || "Annuler";
      bouton.setAttribute("hx-post", action.url);
      bouton.setAttribute("hx-swap", "none");
      bouton.addEventListener("click", function () { window.setTimeout(function () { fermerToast(toast); }, 150); });
      toast.appendChild(bouton);
      var fermer = document.createElement("button");
      fermer.type = "button";
      fermer.className = "btn--lien";
      fermer.setAttribute("aria-label", "Fermer");
      fermer.textContent = "✕";
      fermer.addEventListener("click", function () { fermerToast(toast); });
      toast.appendChild(fermer);
    }
    conteneur.appendChild(toast);
    if (window.htmx) { window.htmx.process(toast); }
    preparerToast(toast);
  }
  window.afficherToast = afficherToast;

  /* ---------- Célébration de l'objectif ---------- */
  function couleursTheme() {
    var styles = window.getComputedStyle(document.documentElement);
    return ["--c-principale", "--c-accent", "--c-foncee"].map(function (nom) {
      return styles.getPropertyValue(nom).trim();
    }).filter(Boolean);
  }

  function celebrer(detail) {
    detail = detail || {};
    if (detail.message) { afficherToast(detail.message, "success"); }
    if (window.lancerConfettis) { window.lancerConfettis(detail.couleurs || couleursTheme()); }
  }

  /* ---------- Initialisation ---------- */
  function initialiser() {
    // Messages Django déjà présents dans la page
    Array.prototype.forEach.call(document.querySelectorAll("#toasts .toast"), function (toast) {
      preparerToast(toast);
      if ((toast.dataset.etiquettes || "").split(" ").indexOf("objectif") !== -1) {
        celebrer({});  // le toast est déjà affiché : seulement les confettis
      }
    });

    // Sélecteur de mois : envoi automatique au changement
    var formMois = document.querySelector("[data-selecteur-mois]");
    if (formMois) {
      var champ = formMois.querySelector("input[type=month]");
      champ.addEventListener("change", function () { if (champ.value) { formMois.submit(); } });
    }
  }

  document.addEventListener("DOMContentLoaded", initialiser);

  /* ---------- Lignes de tableau cliquables (Vue Groupe) ---------- */
  document.addEventListener("click", function (evt) {
    var ligne = evt.target.closest("tr[data-href]");
    if (ligne && !evt.target.closest("a, button")) { window.location.href = ligne.dataset.href; }
  });

  /* ---------- Boîte de dialogue (modification) ---------- */
  document.addEventListener("htmx:afterSwap", function (evt) {
    var dialogue = evt.detail.target && evt.detail.target.closest("dialog");
    if (dialogue && !dialogue.open && evt.detail.target.innerHTML.trim()) {
      dialogue.showModal();
      var premier = dialogue.querySelector("input:not([type=hidden]), select, textarea");
      if (premier) { premier.focus(); }
    }
  });
  document.addEventListener("click", function (evt) {
    var bouton = evt.target.closest("[data-fermer-dialogue]");
    if (bouton) {
      var dialogue = bouton.closest("dialog");
      if (dialogue) { dialogue.close(); }
    }
  });
  document.addEventListener("fermerDialogue", fermerDialogues);
  function fermerDialogues() {
    Array.prototype.forEach.call(document.querySelectorAll("dialog[open]"), function (d) { d.close(); });
  }

  /* ---------- Évènements envoyés par le serveur (en-tête HX-Trigger) ---------- */
  document.addEventListener("toast", function (evt) {
    var d = evt.detail || {};
    afficherToast(d.message || "", d.niveau || "success", d.action);
  });
  document.addEventListener("objectifAtteint", function (evt) {
    var d = evt.detail || {};
    celebrer({
      message: "🎉 Objectif " + (d.societe || "") + " de " + (d.mois || "") + " atteint !",
      couleurs: d.couleurs
    });
  });

  /* ---------- Erreurs HTMX ---------- */
  document.addEventListener("htmx:responseError", function (evt) {
    var statut = evt.detail.xhr ? evt.detail.xhr.status : 0;
    var message = statut === 403 ? "Action non autorisée."
      : statut === 404 ? "Élément introuvable ou non accessible."
      : "Une erreur est survenue. Réessayez.";
    afficherToast(message, "error");
  });
  document.addEventListener("htmx:sendError", function () {
    afficherToast("Connexion au serveur impossible. Vérifiez votre réseau.", "error");
  });
})();
