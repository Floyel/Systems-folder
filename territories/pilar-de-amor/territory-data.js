// ================================================================
//  territory-data.js
//  ─────────────────
//  Self-registering territory metadata.
//  Loaded via <script> tag by GUIDE.html — no server needed.
//
//  Edit the fields below to describe this territory.
//  This file is separate from scene-config.js so the territory
//  picker can read metadata without loading the full AR scene.
// ================================================================

window.TERRITORIES = window.TERRITORIES || [];

window.TERRITORIES.push({

  // ── Identity ────────────────────────────────────────────────────
  id:          "Pilar d'amor",
  name:        "Pilar d'amor",
  description: "Place the anchor by your feet",

  // ── Details ─────────────────────────────────────────────────────
  date:        "2025-08",               // release date, YYYY-MM
  symbols:     12,                       // number of symbols in the scene
  size:        "12 MB",                 // total download size (fill in manually)
  duration:    "open",                  // "open" or e.g. "until 2025-12"

  // ── Physical presence ───────────────────────────────────────────
  attached:    false,
  location:    "",                      // e.g. "Trondheim, NO"

  // ── Entry point ─────────────────────────────────────────────────
  path:        "territories/pilar-de-amor/webar-scene.html",

});
