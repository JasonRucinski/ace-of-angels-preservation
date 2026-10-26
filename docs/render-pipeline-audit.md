# 2.9.2 rendering pipeline audit

The automated CPU audit reproduced invalid trigonometric inputs in visibility
calculation and a zero-distance normalization failure. It did **not** establish
that these cause the reported scenery jumps. The initial audit made no
executable changes; the subsequent isolated culling correction is documented
below. No GUI automation, client launch, or network access is used.

Run with the repository environment:

```powershell
.venv\Scripts\python.exe -I tools/audit_render_pipeline.py evidence/2.9.2/render_pipeline_audit.json
.venv\Scripts\python.exe -I tools/test_object_lod.py
.venv\Scripts\python.exe -I tools/test_render_motion.py
```

The runner requires the hash-pinned original executable. It executes original
x86 routines in Unicorn with synthetic objects. `_CIasin` and `_CIacos` use
Python math substitutes; their **inputs are recorded before substitution**.
Mock device calls validate CPU arguments and failure handling, not graphics.
The generated [evidence](../evidence/2.9.2/render_pipeline_audit.json) records
reproductions, numerical errors, and comparisons with current prepared clients.

## Findings

1. **Unclamped direction dot product reaches `acos`.** `0x543000` normalizes the
   relative direction, dots it with camera forward, then calls `_CIacos` at
   `0x5431A7`. At single precision, a valid moving/turning fixture produces
   `1.0000001192092896`, outside [-1,1]. There are 17 invalid-domain cases in
   480 samples. With a NaN-returning math substitute, ten behind-camera cases
   become visible. Those visibility results depend on the substitute; the
   out-of-domain inputs are produced by the original code. This is not proof
   of on-screen position jumps or of the installed CRT's error behavior.
2. **Entering a bounding sphere produces an invalid `asin` input.** At
   `0x5431B0..0x5431BC`, radius/distance is unbounded. Radius 100 and distance
   99 produces approximately 1.010101; distance 1 produces 100. The substitute
   yields a nonfinite angular bound, while visibility remains true in the
   forward-facing fixtures. It must not be reported as proven disappearance.
3. **Coincident camera/object origins create nonfinite direction values.**
   Normalization at `0x54307D..0x543090` divides by zero before the later
   zero-distance branch. At distance zero, the original code marks the node
   invisible. This result requires no trigonometry substitute. It is an exact
   center edge case, not a reproduction of ordinary flight jitter.
4. **Device failures can be hidden.** The render-state wrapper `0x566DF0`
   ignores the device return at `0x566EF2` and returns 1. Injected S_OK and
   E_FAIL both return 1. The world-matrix submission calls at `0x56DC89` and
   `0x56DD9D` likewise do not inspect their return values (static inspection).
   A driver failure is not known to be occurring in the user's session.

The small-object gate requires projected size **strictly greater than 5**,
even though the LOD selector includes its lower bound. Radius 1 at distances
383/384/385 produces visible/hidden/hidden. This is a reproducible cutoff,
not evidence that the cutoff is incorrect.

## Coverage across the pipeline

| Stage | Code / evidence | Audit result |
|---|---|---|
| Frame time | Clock comparison and existing motion tests | Clock quantization already reproduced; full presentation timing remains open |
| Terrain placement | `emulate_terrain_nodes.py` | Existing probes cover category dispatch and parent position arithmetic; not full scene loading |
| Node hierarchy | `0x542C80`, multiply `0x5451C0` | 120 three-level rotated/translating cases pass; worst matrix-element error 0.003502 at large world coordinates |
| Transform caches | `0x542F00`, `0x542AA0` | Position setter invalidates the changed node only; generic update clears additional caches. Complete descendant notification traversal remains unverified |
| Camera/view | `0x569880`, submission `0x43B49A` | Existing moving/turning camera tests pass; static trace confirms view matrix submission and error check |
| Visibility | `0x543000`, caller `0x546B20` | 480 moving/turning cases executed; numerical edge cases above reproduced |
| Object LOD | `0x542920` | Existing ten-asteroid boundary and placement tests pass |
| World matrix conversion | `0x56CEE0` | 120 byte-exact copies pass; no transposition or translation loss in this helper |
| Mesh submission | `0x56DC6B..0x56DE4E` → `0x562210` | Static trace connects world matrix to primitive submission. Twelve mocked-device cases verify indexed/non-indexed arguments and empty-buffer suppression |
| State/depth settings | `0x566DF0`; depth setup around `0x553DF6..0x553EBC` | Error propagation weakness reproduced. Effective per-pass depth/alpha/cull settings and depth precision remain unverified |
| Texture allocation/upload | `0x562A30` | Static branches reject missing texture data, unsupported bit sizes, and allocation failure. Texture sampling, mip bias, upload/recovery and binding order remain unverified |
| Presentation | windowed path `0x556120` → `0x556890`; flip `0x556220` | Frame pacing measured live at 60 Hz and fixed by `frame-clock-v1` ([findings 9.35](findings.md)). GPU output, surface recovery and >60 Hz displays remain unverified |

Cached transform reuse is intentional. A fixture that mutates a parent using
its position setter leaves a previously cached descendant unchanged. This is
a contract to inspect in the normal update/notification traversal, **not**
proof of a stale-cache defect in normal gameplay. For transform correctness
tests, all three nodes are explicitly invalidated before each frame.

The report compares six audited code spans with both the isolated offline
baseline and main prepared client. Matching spans establish shared code only;
they do not establish identical timing, state, assets, or host/client behavior.

## Culling correction applied to the offline baseline

**Promoted (23 October 2026):** the dot clamp and inside-sphere parts are now
the supported patch `visibility-math-v1` (`tools/visibility_fix.py`), applied
by default in client preparation. The exact-centre part below was **not**
promoted. The player's own ship node sits at distance 0 from the camera in
flight, and the original's "hidden" result there is what keeps your own hull
out of view ([findings 9.36](findings.md)). The experiment's caves now overlap
online terrain, so the tool below applies only to images without it.

`tools/render_culling_experiment.py` now corrects the two visibility entry
points at `0x543077` and `0x5431A1`, with code in verified padding at `0x58B700`.
It handles zero distance before normalization, bounds the dot product to [-1,1]
before `acos`, and handles a camera inside/on a bounding sphere without calling
`asin`. The latter is conservatively visible, subject to the original enabled
and LOD gates. At the exact center it uses camera forward as the otherwise
undefined relative direction and selects the close-range projected size.

The patch is installed only in `game/offline-baseline-2.9.2/AOACLIENT.EXE` and
preserves the existing clock correction. It does not alter the main prepared
client, networking, or assets. Whole-image normalization rejects unknown edits,
partial patches, and occupied patch padding. The adjacent `.EXE.before-culling`
backup and `_render_culling.json` provide exact rollback and installed hashes.

Four regression methods pass: 480 moving/turning cases and 48 inside-sphere
cases (also checking disabled nodes) at each of three FPU precision settings,
unchanged valid outside-sphere results and small-object cutoff, and bounded,
idempotent, exact-undo patching with corruption/partial-patch rejection.
The original 17 invalid trig-input cases and ten visibility mismatches become
zero in the single-precision fixture. See
[fix evidence](../evidence/2.9.2/render_culling_fix.json).

```powershell
.venv\Scripts\python.exe -I tools/test_render_culling.py
# Close the isolated baseline before either operation:
.venv\Scripts\python.exe -I tools/render_culling_experiment.py --undo
.venv\Scripts\python.exe -I tools/render_culling_experiment.py
```

Undo culling **before** changing/removing the clock experiment: the older clock
tool deliberately rejects a culling-modified image. If intentionally changing
the clock, retain the old culling backup as an archive outside its expected
backup filename before applying culling to the new image; backup mismatch
checks prevent silently replacing the prior rollback point.

Full-frame visual behavior remains unverified. The patch removes demonstrated
invalid math and the coincident-origin visibility failure; it does not prove
that all reported scenery jumping is resolved. Device-error handling and
descendant cache propagation have not been changed.

## Remaining verification priorities

The isolated correction removes the demonstrated trig domain-error dependency.
Validate full frames before promoting it into general client preparation.

Next, follow the actual node update/notification path to prove that moving
parents refresh every draw transform. Then instrument device submissions and
surface results with deterministic flight input. Compare matrices and geometry
submitted for successive frames before attributing any remaining jump to the
wrapper or driver. This can stay entirely programmatic, without computer use.

GPU rasterization and presentation cannot be certified by these emulated CPU
tests. This audit is an evidence-backed map of tested stages and remaining gaps,
not a claim that the whole rendering pipeline passes.
