/* ==========================================================================
   Graphiques (Chart.js 4, hébergé localement). Aucune donnée n'est calculée ici :
   les montants arrivent du serveur par <script type="application/json"> (json_script).
   Chaque <canvas data-graphique="…" data-source="id-du-json"> est dessiné au chargement
   et après chaque échange HTMX.
   ========================================================================== */
(function () {
  "use strict";

  var NOMBRE = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });
  var DECIMAL = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });
  var NBSP = " ";

  function fcfa(v) { return NOMBRE.format(Math.round(v || 0)) + NBSP + "F"; }
  function court(v) {
    var a = Math.abs(v || 0);
    if (a >= 1e6) { return DECIMAL.format(v / 1e6) + NBSP + "M"; }
    if (a >= 1e3) { return NOMBRE.format(Math.round(v / 1e3)) + NBSP + "k"; }
    return NOMBRE.format(Math.round(v || 0));
  }
  function pct(v) { return DECIMAL.format(v) + NBSP + "%"; }

  function variable(nom, defaut) {
    var v = window.getComputedStyle(document.documentElement).getPropertyValue(nom).trim();
    return v || defaut;
  }
  function attenuer(hex, alpha) {
    var h = (hex || "#000000").replace("#", "");
    var r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16);
    return "rgba(" + r + "," + g + "," + b + "," + alpha + ")";
  }

  /* Texte au centre des anneaux (dessiné sur le canvas : compatible CSP). */
  var texteCentre = {
    id: "texteCentre",
    afterDraw: function (chart, args, options) {
      if (!options || !options.texte) { return; }
      var zone = chart.chartArea, ctx = chart.ctx;
      var x = (zone.left + zone.right) / 2, y = (zone.top + zone.bottom) / 2;
      ctx.save();
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = variable("--navy", "#1A2B4A");
      ctx.font = "700 20px 'Segoe UI', Roboto, Arial, sans-serif";
      ctx.fillText(options.texte, x, y - 8);
      if (options.sousTitre) {
        ctx.fillStyle = variable("--gris", "#5B6472");
        ctx.font = "11px 'Segoe UI', Roboto, Arial, sans-serif";
        ctx.fillText(options.sousTitre, x, y + 14);
      }
      ctx.restore();
    }
  };

  function optionsCommunes() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 400 },
      plugins: { legend: { display: false } }
    };
  }

  function axeMontants() {
    return {
      beginAtZero: true,
      ticks: { callback: function (v) { return court(v); }, color: variable("--gris", "#5B6472") },
      grid: { color: variable("--gris-clair", "#E5E7EB") }
    };
  }

  /* ---------- Fabriques par type de graphique ---------- */
  var FABRIQUES = {
    repartition: function (d) {
      var donnees = d.repartition;
      return anneau(donnees, donnees.parts.map(function (p) { return p.couleur; }));
    },
    objectif: function (d) {
      var donnees = d.objectif;
      var couleurs = { realise: variable("--c-principale"), reste: variable("--gris-clair"), depassement: variable("--c-accent") };
      return anneau(donnees, donnees.parts.map(function (p) { return couleurs[p.cle]; }));
    },
    mois: function (d) {
      var m = d.mois, principale = variable("--c-principale"), foncee = variable("--c-foncee");
      return {
        type: "bar",
        data: {
          labels: m.etiquettes,
          datasets: [{
            type: "bar", label: "Marge", data: m.marges, order: 2, borderRadius: 4,
            backgroundColor: m.marges.map(function (v, i) { return m.atteints[i] ? principale : attenuer(principale, 0.45); }),
            borderColor: m.marges.map(function (v, i) { return i === m.selection ? foncee : "transparent"; }),
            borderWidth: m.marges.map(function (v, i) { return i === m.selection ? 2 : 0; })
          }, {
            type: "line", label: "Objectif", data: m.objectifs, order: 1,
            borderColor: variable("--navy", "#1A2B4A"), borderWidth: 2, borderDash: [5, 4],
            pointRadius: 0, pointHoverRadius: 4, stepped: "middle", fill: false
          }]
        },
        options: Object.assign(optionsCommunes(), {
          scales: {
            y: axeMontants(),
            x: { grid: { display: false }, ticks: {
              color: function (c) { return c.index === m.selection ? variable("--navy") : variable("--gris"); },
              font: function (c) { return { weight: c.index === m.selection ? "700" : "400" }; }
            } }
          },
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: {
              title: function (items) { return items.length ? m.titres[items[0].dataIndex] : ""; },
              label: function (c) { return c.dataset.label + " : " + fcfa(c.parsed.y); },
              afterBody: function (items) {
                var i = items.length ? items[0].dataIndex : 0;
                return m.atteints[i] ? "✔ Objectif atteint" : "";
              }
            } }
          }
        })
      };
    },
    "charges-depenses": function (d) {
      var c = d.chargesDepenses;
      return {
        type: "bar",
        data: {
          labels: c.etiquettes,
          datasets: [
            { label: "Part charges", data: c.parts, backgroundColor: variable("--c-charges", "#2F6FB0"), borderRadius: 3 },
            { label: "Dépenses", data: c.depenses, backgroundColor: "#4B5563", borderRadius: 3 }
          ]
        },
        options: Object.assign(optionsCommunes(), {
          scales: {
            y: axeMontants(),
            x: { grid: { display: false }, ticks: {
              color: function (t) { return t.index === c.selection ? variable("--navy") : variable("--gris"); },
              font: function (t) { return { weight: t.index === c.selection ? "700" : "400" }; }
            } }
          },
          interaction: { mode: "index", intersect: false },
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: {
              title: function (items) { return items.length ? c.titres[items[0].dataIndex] : ""; },
              label: function (t) { return t.dataset.label + " : " + fcfa(t.parsed.y); },
              footer: function (items) {
                var e = items.length ? c.ecarts[items[0].dataIndex] : null;
                if (e === null || e === undefined) { return "Dépenses non saisies"; }
                return e >= 0 ? "Excédent : " + fcfa(e) : "Reste à couvrir : " + fcfa(-e);
              }
            } }
          }
        })
      };
    },
    projets: function (d) {
      var p = d.projets;
      return {
        type: "bar",
        data: { labels: p.etiquettes, datasets: [{ label: "Marge", data: p.marges, backgroundColor: variable("--c-principale"), borderRadius: 4 }] },
        options: Object.assign(optionsCommunes(), {
          indexAxis: "y",
          scales: { x: axeMontants(), y: { grid: { display: false }, ticks: { color: variable("--navy") } } },
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: {
              label: function (c) { return "Marge : " + fcfa(c.parsed.x); },
              afterLabel: function (c) { return NOMBRE.format(p.quantites[c.dataIndex]) + " " + p.unite + "(s)"; }
            } }
          }
        })
      };
    },
    "groupe-societes": function (d) {
      var g = d.societes;
      return {
        type: "bar",
        data: {
          labels: g.etiquettes,
          datasets: [{ type: "bar", label: "Marge", data: g.marges, backgroundColor: g.couleurs, borderRadius: 4, order: 2 }, {
            type: "line", label: "Objectif", data: g.objectifs, order: 1, showLine: false,
            borderColor: variable("--navy", "#1A2B4A"), backgroundColor: variable("--navy", "#1A2B4A"),
            pointStyle: "line", pointRadius: 14, pointBorderWidth: 3, pointHoverRadius: 16, borderDash: [3, 2]
          }]
        },
        options: Object.assign(optionsCommunes(), {
          indexAxis: "y",
          scales: { x: axeMontants(), y: { grid: { display: false }, ticks: { color: variable("--navy") } } },
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: {
              title: function (items) { return items.length ? g.noms[items[0].dataIndex] : ""; },
              label: function (c) { return c.dataset.label + " : " + fcfa(c.parsed.x); },
              afterBody: function (items) { return items.length ? pct(g.progressions[items[0].dataIndex]) + " de l'objectif" : ""; }
            } }
          }
        })
      };
    },
    "groupe-ac": function (d) {
      var donnees = d.africaCommodities;
      return anneau(donnees, donnees.parts.map(function (p) { return p.couleur; }));
    },
    "groupe-mois": function (d) {
      var g = d.mois;
      return {
        type: "bar",
        data: {
          labels: g.etiquettes,
          datasets: g.series.map(function (s) {
            return { label: s.nom, data: s.marges, backgroundColor: s.couleur, stack: "groupe", borderRadius: 2 };
          })
        },
        options: Object.assign(optionsCommunes(), {
          scales: {
            x: { stacked: true, grid: { display: false }, ticks: {
              color: function (c) { return c.index === g.selection ? variable("--navy") : variable("--gris"); },
              font: function (c) { return { weight: c.index === g.selection ? "700" : "400" }; }
            } },
            y: Object.assign(axeMontants(), { stacked: true })
          },
          interaction: { mode: "index", intersect: false },
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: {
              title: function (items) { return items.length ? g.titres[items[0].dataIndex] : ""; },
              label: function (c) { return c.dataset.label + " : " + fcfa(c.parsed.y); },
              footer: function (items) {
                var total = items.reduce(function (s, it) { return s + it.parsed.y; }, 0);
                return "Total : " + fcfa(total);
              }
            } }
          }
        })
      };
    }
  };

  function anneau(donnees, couleurs) {
    var total = donnees.parts.reduce(function (s, p) { return s + p.valeur; }, 0) || 1;
    return {
      type: "doughnut",
      data: {
        labels: donnees.parts.map(function (p) { return p.nom; }),
        datasets: [{ data: donnees.parts.map(function (p) { return p.valeur; }), backgroundColor: couleurs, borderWidth: 2, borderColor: "#FFFFFF" }]
      },
      options: Object.assign(optionsCommunes(), {
        cutout: "62%",
        plugins: {
          legend: { display: false },
          texteCentre: { texte: donnees.centre, sousTitre: donnees.sousTitre },
          tooltip: { callbacks: {
            label: function (c) { return c.label + " : " + fcfa(c.parsed) + " · " + pct(c.parsed / total * 100); }
          } }
        }
      })
    };
  }

  /* ---------- Dessin ---------- */
  function dessiner(racine) {
    if (!window.Chart) { return; }
    var canvases = (racine || document).querySelectorAll("canvas[data-graphique]");
    Array.prototype.forEach.call(canvases, function (canvas) {
      var source = document.getElementById(canvas.dataset.source);
      var fabrique = FABRIQUES[canvas.dataset.graphique];
      if (!source || !fabrique) { return; }
      var existant = window.Chart.getChart(canvas);
      if (existant) { existant.destroy(); }
      var config = fabrique(JSON.parse(source.textContent));
      config.plugins = [texteCentre];
      new window.Chart(canvas, config);
    });
  }

  document.addEventListener("DOMContentLoaded", function () { dessiner(document); });
  document.addEventListener("htmx:afterSettle", function () { dessiner(document); });
})();
