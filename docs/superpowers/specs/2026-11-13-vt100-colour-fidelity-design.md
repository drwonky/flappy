# flappy-vt100: colour + glyph fidelity at 80x25

Date: 2026-11-13
Owner: agreed with the human partner in conversation; calls marked "my call" are mine.

## Intent and the why

`flappy-vt100.py` plays Flappy Bird well but does not *look* like Flappy Bird. The
physics and the 160x48 sub-pixel dither engine are good; the picture fails because
(a) colour is invented from a per-row heuristic instead of per-pixel material, and
(b) the bird is drawn at less than half its correct size, so no amount of shading
makes it read as the original character.

Goal: a terminal rendering that a viewer recognises as Flappy Bird, without leaving
80x25 text mode.

## Reference material used

- Wikipedia, *Flappy Bird*: the character is "a small yellow bird with big red
  beak"; the obstacles are green pipes. Collision with a pipe or the ground ends play.
- Wikipedia, *DEC Special Graphics*: the set a **Linux console** reaches with Shift Out
  is a *modified* DEC set "with additional fill blocks". So `▀▄█▌▐░▒▓` are safe on a real
  Linux VT; the Unicode eighth-blocks (`▁▂▃▅▆▇`, `▏▎▍▋▐`) are not in CP437.
- `console_codes(4)`, Linux man pages: the kernel console implements
  `38;5;x` / `48;5;x` but the value is "**shoehorned into 16 basic colors**".
  256-colour SGR is accepted-and-lossy on a real VT; full 256 needs a terminal emulator.
- The repo's own `flappy-8bit.html`: authentic palette plus four hand-authored 17x12
  bird sprite frames (`.` `K` `Y` `D` `C` `W` `R` `O`), and a HUD note that the bird's
  width must be **0.65 of the pipe shaft**.

Authentic palette (from `flappy-8bit.html`), with measured quantisation error
(CIE76 dE in CIELAB):

| material | hex | best 256 | dE | best 16 | dE |
|---|---|---|---|---|---|
| birdY  | #f8e018 | 220 | 7.6 | 11 | 17.4 |
| birdD  | #d9a90f | 178 | 5.1 |  3 | 31.6 |
| birdC  | #f5f2c0 | 230 | 7.0 | 15 | 26.1 |
| beak   | #e8483a | 203 | 13.0 | 9 | 30.8 |
| pipeHi | #74bf2e |  70 | 7.6 |  2 | 27.2 |
| pipeLo | #3d7a12 |  64 | 13.0 |  2 | 14.7 |
| sand   | #ded895 | 186 | 6.9 |  7 | 35.6 |
| skyA   | #6cc5de |  81 | 10.8 | 7 | 28.9 |

The 256-colour cube lands at dE <= 15 (mostly under 11). The current 16-colour
projection sits at dE 16-36. That gap is most of why the colours read wrong today.

## Goals

- Bird reads as the original: yellow body, darker yellow shading, pale belly, white
  eye with dark pupil, large red beak, beating wing, four-frame flap animation.
- Pipes read as the original: black outline, left catch-light, highlight, body, shadow.
- Sky and ground painted as coloured backgrounds; ink dither still carries the shading.
- Per-pixel (not per-row) colour.
- Bird at 0.65 of the pipe shaft width, matching the repo's own reference build.
- `--vt100` still emits strict DEC Special Graphics, monochrome, `ESC(0` / `ESC(B`.

## Non-goals

- Not a rewrite of the physics, autopilot, difficulty ramp, or `--selftest`.
- Not leaving 80x25. No resize, no alt-screen width change, no sixel/ReGIS.
- Not matching the original's aspect ratio. A landscape 80x25 field cannot hold a
  288x512 portrait game; proportions are a reinterpretation, already chosen by the
  existing code (pipe 29/160 = 0.181 of width, gap 16-20 of 38 sky).

## Constraints

- 80x25 characters, 160x48 sub-pixels. Unchanged.
- Three output modes must keep working: rich colour, `--vt100` strict mono, `--frames` text dump.
- Byte budget is a stated interest of this file (`--stats`, "9600-baud curiosity").
  Now: median 1938 B/frame, p90 2073, max 2225. Per-cell FG+BG pairs cost about
  10 B/cell against a 1920-cell frame; delta-coding run lengths is required, not optional.
- The Linux kernel console cannot show more than 16 colours, and CP437 has no
  eighth-block glyphs. Rich mode must therefore degrade correctly, not merely differently.

## Approaches considered

**A. Keep ink-on-paper dither; add a material tag for foreground colour only.**
Cheapest, smallest byte growth. Trade-off: the bird stays a dithered dot; the pale
belly, white eye and sky separation are impossible without backgrounds. Rejected: it
cannot deliver the bird, which is the main ask.

**B. Two colours per cell: FG paints the top half, BG the bottom half, via
`▀`/`▄`/`█`/space plus the 16 quadrant glyphs. Authentic palette quantised to 16 ANSI
colours; sky and ground as backgrounds. Colour resolution doubles to 160x48.**
Correct on a real Linux VT (16 colours, CP437-safe glyphs). Trade-off: 16 colours cap
the palette at the dE 16-36 errors above, and the sky gradient can only be banded.

**C. Chosen: B's two-colours-per-cell model, plus Unicode eighth-blocks and 256-colour
SGR gradients.**
Best fidelity in a terminal emulator. Trade-offs, and how each is contained:
256-colour SGR is lossy on a kernel VT, so the 16-colour projection is authored to be
already correct and 256 is an additive layer; eighth-blocks are not CP437, so they are
gated behind a capability check with a CP437-only fallback that keeps all 16 quadrant glyphs.

C was chosen by the human partner. B remains available as the built-in fallback path,
not as a discarded option.

## The how, as decided

1. **Framebuffer gains a material plane.** `Scene` keeps `L` (darkness 0..1) and gains
   `M` (material id per sub-pixel). Every painter call tags what it paints: sky, cloud,
   hill-far, hill-near, pipe-outline/light/high/body/shadow, grass, sand, sand-dark,
   bird-body/shade/belly, eye, pupil, beak, beak-dark, ink.
2. **Colour is resolved per cell, not per row.** `TTY.draw`'s `band=` heuristic is
   deleted. Each cell samples the material of its 4 sub-pixels; dominant material picks
   the pair, and the quadrant glyph decides which half gets FG and which gets BG.
3. **Palette authored in two tiers.** A 16-colour ANSI set chosen so the hues are right
   when shoehorned, plus a 256-colour table of exact quantised authentic colours.
   Rich mode emits `38;5;n`/`48;5;n`; conservative mode emits `30..37`/`40..47`/`90..97`.
4. **Bird sprite ported from the reference build.** Four authored flap frames mapped
   into the sub-pixel grid, at ~19 sub-px wide (0.65 of the 29-sub-px shaft) and ~12 tall,
   instead of today's 8x6 ellipse. Pitch rotation and wing beat come from `g.wing` and `g.vy`.
   My call: hitbox (`HW`, `HH`) stays at its current values so physics, autopilot and
   `--selftest` statistics are untouched; only the drawn sprite grows. `assert SAFE > 0`
   keeps its meaning.
5. **Ground becomes the original's banded sand**: sand body, darker sand stripes, a grass
   strip at the horizon, drawn as FG/BG pairs.
6. **`--vt100` stays strict.** DEC Special Graphics only, monochrome, one chequerboard
   shade, `ESC(0`/`ESC(B`. My call: improve its glyph map from the current 4-level
   `~`/`` ` ``/`a` buckets to a 4-tone map that uses DEC's `░`(chequerboard)/`▒`/`·`/`-`
   and box-drawing lines for hard pipe edges. It remains 7-bit DEC, so a real VT100 draws it.
7. **Byte budget handled by run-length colour coding**: emit an SGR pair only when the
   cell's colour pair actually changes from the previous cell, and reuse the existing
   per-row line diffing. Target: under 3000 B/frame median.

## Left to the builder

- Exact material ids, exact 16-colour projection table, and the frame-to-frame sprite
  mapping of the 17x12 authored frames onto a 19x12 sub-pixel bird.
- Whether eighth-blocks are auto-detected from `TERM`/`TERM_PROGRAM` or set by a flag;
  my call is a flag with a conservative default, since auto-detection lies often.
- Whether to add a `--no-colour` flag; my call: no, `--vt100` already covers it.

## Verification

- `--selftest` must not regress: same crash distribution as before the change
  (physics untouched). Diff the numbers before and after.
- `--frames N` output must stay 80 columns wide and 24 field rows.
- `--stats` byte count reported before/after; must stay under the agreed budget.
- Render one frame into a `script` capture of a real tty and confirm no stray escape
  state leaks at exit (`bye()` resets SGR and glyph set).
- Visual check by the human partner in their own terminal: bird recognisable, pipes
  read as the original, sky/ground read as background-filled.
