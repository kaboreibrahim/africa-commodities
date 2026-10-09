/* ==========================================================================
   Suivi des marges – comportements communs (aucun script inline : CSP stricte).
   - toasts (messages Django + évènement HTMX « toast ») ;
   - sélecteur de mois ;
   - menu latéral (tiroir sur mobile) et menus déroulants ;
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

  /* ---------- Menu latéral (tiroir sur mobile) et menus déroulants ---------- */
  function basculerMenu(ouvert) {
    var appli = document.getElementById("app");
    if (!appli) { return; }
    appli.classList.toggle("menu-ouvert", ouvert);
    Array.prototype.forEach.call(document.querySelectorAll("[data-ouvrir-menu]"), function (b) {
      b.setAttribute("aria-expanded", ouvert ? "true" : "false");
    });
    if (ouvert) {
      var premier = document.querySelector("#menu-lateral a");
      if (premier) { premier.focus(); }
    }
  }
  document.addEventListener("click", function (evt) {
    if (evt.target.closest("[data-ouvrir-menu]")) {
      basculerMenu(!document.getElementById("app").classList.contains("menu-ouvert"));
    } else if (evt.target.closest("[data-fermer-menu]") || evt.target.closest("#menu-lateral a")) {
      basculerMenu(false);
    }
    // Menu du compte : se ferme au clic en dehors
    Array.prototype.forEach.call(document.querySelectorAll("details[data-menu][open]"), function (d) {
      if (!d.contains(evt.target)) { d.removeAttribute("open"); }
    });
  });
  document.addEventListener("keydown", function (evt) {
    if (evt.key !== "Escape") { return; }
    basculerMenu(false);
    Array.prototype.forEach.call(document.querySelectorAll("details[data-menu][open]"), function (d) {
      d.removeAttribute("open");
      var resume = d.querySelector("summary");
      if (resume) { resume.focus(); }
    });
  });

  /* ---------- Lignes de tableau cliquables (Vue Groupe) ---------- */
  document.addEventListener("click", function (evt) {
    var ligne = evt.target.closest("tr[data-href]");
    if (ligne && !evt.target.closest("a, button")) { window.location.href = ligne.dataset.href; }
  });

  /* ---------- Boîte de dialogue (modification) ---------- */
  document.addEventListener("htmx:afterSwap", function (evt) {
    var dialogue = evt.detail.target && evt.detail.target.closest("dialog");
    // Seul le contenu chargé à la demande (#dialogue-contenu) ouvre la fenêtre ; la fenêtre de saisie a son bouton.
    if (dialogue && !dialogue.open && evt.detail.target.id === "dialogue-contenu" && evt.detail.target.innerHTML.trim()) {
      dialogue.showModal();
      var premier = dialogue.querySelector("input:not([type=hidden]), select, textarea");
      if (premier) { premier.focus(); }
    }
  });
  function ouvrirDialogue(dialogue) {
    if (!dialogue) { return; }
    // Toujours en modale : si la fenêtre est restée ouverte « à plat » (page restaurée, ancienne version…), on la referme d'abord.
    try {
      if (dialogue.open && !dialogue.matches(":modal")) { dialogue.close(); }
      if (!dialogue.open) { dialogue.showModal(); }
    } catch (erreur) {
      dialogue.setAttribute("open", "");
    }
    var premier = dialogue.querySelector("input:not([type=hidden]), select, textarea");
    if (premier) { premier.focus(); }
  }
  function ouvrirDialoguesDemandees() {
    Array.prototype.forEach.call(document.querySelectorAll("dialog[data-ouvrir-auto], dialog[open]"), function (d) {
      if (!d.matches(":modal")) { ouvrirDialogue(d); }
    });
  }
  document.addEventListener("DOMContentLoaded", ouvrirDialoguesDemandees);
  window.addEventListener("pageshow", function (evt) { if (evt.persisted) { ouvrirDialoguesDemandees(); } });
  document.addEventListener("click", function (evt) {
    var ouvreur = evt.target.closest("[data-ouvrir-dialogue]");
    if (ouvreur) {
      evt.preventDefault();
      ouvrirDialogue(document.getElementById(ouvreur.getAttribute("data-ouvrir-dialogue")));
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
      message: "🎉 Objectif " + (d.societe || "") + " " + (d.deMois || "") + " atteint !",
      couleurs: d.couleurs
    });
  });

  /* Client ajouté (ajout rapide) : il est sélectionné dès que la liste déroulante est rafraîchie. */
  var clientAjoute = null;
  document.addEventListener("clientsModifies", function (evt) {
    clientAjoute = evt.detail && evt.detail.nom ? String(evt.detail.id) : null;
  });
  document.addEventListener("htmx:afterSwap", function (evt) {
    var champ = evt.detail.target;
    if (clientAjoute && champ && champ.id === "champ-client-ajout") {
      var liste = document.getElementById("id_client");
      if (liste) { liste.value = clientAjoute; }
      clientAjoute = null;
    }
  });

  document.addEventListener("chargesCouvertes", function (evt) {
    var d = evt.detail || {};
    // Simple notification : les confettis restent réservés à l'objectif.
    afficherToast("✔ Charges " + (d.societe || "") + " " + (d.deMois || "") + " couvertes", "success");
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
