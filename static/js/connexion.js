/*
  Pages d'authentification : rideau d'ouverture de la page de connexion.
  Chargé SANS « defer » dans <head> pour que la classe « js » soit posée avant le premier affichage.
  L'animation elle-même est en CSS (auth.css) ; ce script ne fait qu'enclencher et nettoyer.
  Rien n'est stocké hors du drapeau « rideau déjà joué » (sessionStorage, par onglet).
*/
(function () {
  var racine = document.documentElement;
  var CLE = 'acr-rideau';
  racine.classList.add('js');

  // Page de déconnexion : le rideau rejouera à la prochaine arrivée sur la connexion.
  if (racine.hasAttribute('data-reinit-rideau')) {
    try { window.sessionStorage.removeItem(CLE); } catch (e) { /* stockage indisponible */ }
  }
  if (!racine.hasAttribute('data-rideau')) return;

  var dejaJoue = false;
  try { dejaJoue = window.sessionStorage.getItem(CLE) === '1'; } catch (e) { /* stockage indisponible */ }
  if (dejaJoue) {
    racine.classList.add('rideau-saute');
    return;
  }
  try { window.sessionStorage.setItem(CLE, '1'); } catch (e) { /* stockage indisponible */ }
  racine.classList.add('rideau-actif');

  var termine = false;

  function terminer() {
    if (termine) return;
    termine = true;
    racine.classList.add('rideau-termine');
    var champ = document.getElementById('id_login');
    if (champ && document.activeElement !== champ) champ.focus({ preventScroll: true });
  }

  function ouvrir() { racine.classList.add('rideau-ouvert'); }

  function accelerer() { racine.classList.add('rideau-rapide'); }

  if (document.readyState === 'complete') ouvrir();
  else window.addEventListener('load', ouvrir);
  window.setTimeout(ouvrir, 2500);   // filet de sécurité si « load » tarde
  window.setTimeout(terminer, 7000); // filet de sécurité si l'animation ne se termine jamais

  document.addEventListener('DOMContentLoaded', function () {
    var droite = document.querySelector('.rideau--droite');
    if (droite) {
      droite.addEventListener('animationend', function (evenement) {
        if (evenement.target === droite && evenement.animationName.indexOf('rideau-sortie') === 0) terminer();
      });
    }
    ['pointerdown', 'keydown'].forEach(function (nom) {
      document.addEventListener(nom, accelerer, { once: true });
    });
  });

  // Retour arrière depuis le navigateur (cache de page) : jamais de rideau fermé devant le formulaire.
  window.addEventListener('pageshow', function (evenement) {
    if (evenement.persisted) terminer();
  });
}());
