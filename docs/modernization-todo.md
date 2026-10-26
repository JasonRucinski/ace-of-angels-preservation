# Game modernization checklist

Updated 21 October 2026. Recommendations, not promises or completed work.
The playable-server prerequisites and measurable performance gates are in
[internet-server-todo.md](internet-server-todo.md).

Recommendation: preserve the game's ship silhouettes, factions, flight feel
and space atmosphere while improving readability, responsiveness and asset
quality. First prove a representative upgraded scene; avoid wholesale art
replacement or an engine rewrite before checking compatibility and budgets.

## 1. Choose the modernization path

- [ ] Capture a reference experience: menus, HUD, ship handling, weapon
  effects, map scale, sound and representative scenes from the existing game.
- [ ] Define an art direction and a short list of features that must retain
  their original identity; distinguish restoration from intentional redesign.
- [ ] Keep pristine assets and reproducible exports, provenance, names,
  dependencies and hashes. Never overwrite the only source copy.
- [ ] Determine rights and distribution permissions for original and new
  assets, fonts, music, wrappers and third-party tools before public packaging.
- [ ] Prototype the limits of the existing client: UI replacement hooks,
  accepted texture sizes/formats, model format limits, shaders, memory and
  graphics-wrapper behavior. Do not assume modern assets can be dropped in.
- [ ] Compare three concrete paths: maintained legacy client plus wrapper;
  incremental replacement of subsystems; new client on a maintained engine.
- [ ] If source cannot be obtained, estimate the reverse-engineering and
  maintenance cost explicitly. Full UI/renderer replacement may require a
  new client, not just binary patches.
- [ ] Evaluate engine candidates with one ship, one map section, the intended
  flight model and server connection. Compare performance, iteration speed,
  licensing, supported platforms and asset import before selecting one.
- [ ] Keep the server protocol/simulation contract independent of a visual
  prototype; preserve a reference client for behavior comparisons.
- [ ] Define milestones and rollback paths so a visual upgrade cannot block
  people from using the playable legacy-compatible release.

## 2. Recreate the UI and HUD — highest visible priority

- [ ] Replace tiny bitmap text with scalable, readable typography at 1080p,
  1440p and 4K; test Windows DPI scaling and ultrawide layouts.
- [ ] Redesign login, server browser, pilot selection, ship/loadout selection,
  settings and loading screens into a clear, consistent flow.
- [ ] Show actual server ping, population, mode, map, compatibility and
  connection errors; support direct connect and favorites.
- [ ] Rebuild the HUD around speed, shield/hull, energy/ammo, target, aim,
  navigation and objective information. Test what matters during combat.
- [ ] Make HUD scale, opacity and layout configurable with sensible presets.
- [ ] Improve radar/target identification, friendly/enemy distinction,
  off-screen indicators, lead cues and damage feedback without unfair assists.
- [ ] Use symbols plus color for critical state; provide color-vision options
  and legible contrast against both bright nebulae and black space.
- [ ] Support mouse and keyboard navigation, explicit focus, remapping,
  consistent back/cancel, and usable controller navigation if supported.
- [ ] Add captions/subtitles, separate audio sliders, reduced flashing,
  motion/shake controls and UI readability settings.
- [ ] Surface contextual control hints, a concise controls reference and
  a tutorial explaining flight, targeting, weapons and objectives.
- [ ] Replace the fragile legacy skin/OCX dependency where the selected
  modernization path permits it; test clean installation afterward.
- [ ] Measure HUD cost with many targets and effects. UI polish must remain
  inside the same frame-time budget as the rest of the game.

## 3. Textures and materials — selective upgrades, with visual checks

- [ ] Inventory texture dimensions, UV usage, alpha, tiling, palettes,
  compression, mipmaps and reuse across ships and environments.
- [ ] Rank upgrades by visible impact: cockpit/HUD, player ships, nearby
  bases and large repeated surfaces before distant scenery.
- [ ] Restore damaged/missing textures and resolve legacy material bindings
  before upscale work; an unbound high-resolution image fixes nothing.
- [ ] Test a small texture set at 2× resolution, comparing motion and common
  camera distances. Adopt larger sizes only where visibly useful.
- [ ] Compare careful repainting, conventional resampling and AI upscaling;
  inspect invented markings, seams, inconsistent panel lines and text.
- [ ] Rebuild typography, insignia and logos from clean artwork rather than
  asking an upscaler to invent legible text.
- [ ] Preserve intended alpha edges, emissive areas and tiled seams; generate
  correct mipmaps and test shimmer/flicker at distance.
- [ ] Correct color-space handling and compression formats in the chosen
  renderer; inspect gradients, stars and translucent effects for artifacts.
- [ ] If moving to a modern material pipeline, author coherent roughness,
  metalness, normal and emissive maps. Do not blindly derive every map from
  the old painted diffuse texture, which may contain baked lighting.
- [ ] Set texture memory/streaming budgets and low/medium/high variants.
  Provide an original-art option where feasible.
- [ ] Keep each converted asset reproducible, versioned and attributable.

## 4. Models — improve silhouettes and close-up detail, not every triangle

- [ ] Repair invalid geometry, normals, smoothing, UVs and material assignment
  in exported models; document unresolved legacy formats.
- [ ] Prioritize player ships, cockpit elements, docking structures and
  objects seen close up. Preserve distinctive faction silhouettes.
- [ ] Increase polygon count where it improves silhouettes or curved surfaces;
  use normal maps for small surface detail instead of blanket subdivision.
- [ ] Retopologize problematic meshes and maintain consistent scale, origin,
  axes, attachment points and orientation across exports.
- [ ] Preserve weapon hardpoints, engine positions, docking attachments and
  animation pivots; verify effects and aiming after replacing a mesh.
- [ ] Generate multiple LODs and tune transitions at gameplay distances.
  Test popping and readability during fast flybys.
- [ ] Keep collision meshes separate and simpler; never silently change a
  ship's hitbox or flight balance because its art became more detailed.
- [ ] Set per-scene triangle/draw-call budgets on reference hardware instead
  of choosing one large polygon target for every object.
- [ ] Add instancing/batching for repeated asteroids and base modules where
  supported, and use distance culling appropriately for open space.
- [ ] Review damage variants, wreckage and modular destruction only after
  authoritative damage and cleanup are reliable.

## 5. Renderer and presentation

- [ ] Establish a stable borderless/windowed path, proper resolution and DPI,
  aspect ratio, field of view and alt-tab behavior first.
- [ ] Improve frame pacing, VSync/frame-cap choices and high-refresh support;
  keep simulation and input independent from render frequency.
- [ ] Add scalable anti-aliasing and anisotropic filtering, verified against
  cockpit text, star fields and thin geometry.
- [ ] Upgrade lighting and exposure carefully so ships and targets remain
  readable against backgrounds; preserve the original visual mood.
- [ ] Improve engine trails, muzzle flashes, impacts, shield hits and
  explosions with bounded particle/light/overdraw budgets.
- [ ] Rebuild stars, backdrops and nebulae at suitable resolution with stable
  motion and no visible seams; avoid distracting oversized effects.
- [ ] Add shadows, reflections, bloom and tone mapping only where supported
  and useful; expose quality controls and test combat readability.
- [ ] Add HDR only with a correct output/calibration path and an equally
  good SDR result. It is optional polish, not a first-release requirement.
- [ ] If replacing the renderer, target a maintained API and platform path,
  then validate content, transparency and lighting parity before switching.
- [ ] Consider modern upscaling only after profiling; compare added blur,
  ghosting and latency against native rendering. Do not use it to conceal
  avoidable CPU stalls or an oversized asset budget.

## 6. Audio, controls and game feel

- [ ] Audit original sound/music quality and duplication; recover missing
  cues and preserve recognizable sounds where possible.
- [ ] Improve spatial audio, attenuation, mixing, weapon/engine feedback and
  clear directional threat cues; test headphones and speakers.
- [ ] Normalize loudness and prevent clipping; provide music/effects/UI/voice
  controls and captions for meaningful spoken information.
- [ ] Add reliable mouse sensitivity, inversion, smoothing options, joystick
  calibration/deadzones, controller mappings and saved per-device profiles.
- [ ] Make input focus and hot-plugging robust, including alt-tab and menus.
- [ ] Verify flight acceleration/turn rates at several frame rates and input
  devices; preserve a classic handling profile.
- [ ] Improve camera transitions, aiming feedback and hit confirmation;
  make shake and motion effects optional.
- [ ] Add a training arena and short guided tutorial before advanced mission
  content. Teach why an action failed rather than leaving silent buttons.
- [ ] Playtest loadout balance, time-to-kill, target visibility and respawn
  pacing before changing gameplay merely to match modern conventions.

## 7. Maps, tools and content production

- [ ] Build a documented import/export pipeline for recovered layouts,
  meshes, materials, ship definitions and mission data.
- [ ] Add validation for missing references, bad transforms, duplicate IDs,
  invalid spawns and collision/nav issues before content reaches a client.
- [ ] Create a small map/mission editing workflow with preview and validation;
  reuse a suitable editor if the chosen client architecture supports one.
- [ ] Upgrade one complete map as a showcase: terrain/modules, materials,
  lighting, navigation landmarks, collision, objectives and performance.
- [ ] Restore older useful geometry and placement records only after semantic
  validation; do not treat every old asset as compatible finished content.
- [ ] Package custom maps with versions, dependencies, previews and integrity
  checks. Define server/client compatibility and content download behavior.
- [ ] Consider mod support after the formats and trust model are stable;
  validate/sandbox user content rather than executing arbitrary scripts.
- [ ] Add spectator/replay/photo tools later if simulation snapshots and
  event recording make them practical. Keep spectator information fair.

## 8. Quality, maintenance and optional expansion

- [ ] Build automated content validation and reproducible client/server
  packaging, plus smoke tests for login, load, flight, match and update.
- [ ] Maintain representative screenshot/audio references and benchmark
  replays so upgrades can be compared fairly.
- [ ] Collect opt-in crash/performance reports with useful version and
  hardware metadata; avoid uploading credentials or raw private sessions.
- [ ] Test graphics/input hardware diversity, long sessions, resolution
  changes, device loss, updates and rollback.
- [ ] Prepare localization-ready UI layouts and externalized text; choose
  actual languages based on audience rather than promising every language.
- [ ] Evaluate Linux/Steam Deck and broader platform support only after the
  client architecture, dependencies and controls make it realistic.
- [ ] Consider achievements, progression, matchmaking or community features
  only after there is a stable game and a reason players need them.

## Recommended sequence and stop conditions

| Stage | Deliverable | Gate before scaling up |
|---|---|---|
| A | Playable, measurable networked baseline | Internet-server checklist's first-map match and performance gates |
| B | Readable UI/HUD, clean install, input and frame pacing | A new tester can install, find a match and understand combat |
| C | One upgraded ship and one arena section | Better visual quality in blind comparisons; no frame-budget regression |
| D | Complete upgraded map plus audio/effects | Full populated match meets client/server budgets and readability goals |
| E | Broader asset refresh and optional new client | Proven pipeline, sustainable maintenance and compatible gameplay |
| F | New content/platform/community features | Stable core game, demonstrated player demand and available capacity |

Avoid initially: automatic polygon multiplication across all models,
indiscriminate 4K/8K texture conversion, mandatory expensive lighting effects,
rebuilding every menu before proving UI integration, and committing to an
engine rewrite without a working networked prototype.

Performance measurements should include CPU/GPU timing and tail frame times,
not average FPS alone; see the linked
[profiling reference](https://learn.microsoft.com/en-us/windows/win32/direct3dtools/pix/articles/timing-captures/pix-timing-captures).
Tool compatibility must be established for the renderer actually selected.
