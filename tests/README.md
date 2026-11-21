# Tests for flappy-seasons.html

The tests need Node 22 or newer, plus Chrome or Chromium for the browser parts. There is nothing to `npm install`.

```sh
npm test              # everything (~2 min; the balance runs are most of it)
npm run test:quick    # all but the balance runs (~30 s)
npm run test:unit     # logic only, no browser (~20 s)
npm run test:browser  # the page in headless Chrome
npm run test:snapshots
npm run test:balance
npm run test:update   # accept the current look as the new snapshots
npm run bench         # draw cost, WebGL vs Canvas 2D, under CPU throttling (~1 min)
```

To run one test, use `node --test --test-name-pattern="abduct" tests/browser.test.mjs`.

## What is covered

| File | What it checks |
|---|---|
| `unit.test.mjs` | Logic, run in Node through `lib/sandbox.mjs` with no browser. It covers the Morse plans and timing, the ENV slider scale and labels, stats (brackets, causes of death, saving, `?resetstats`, a corrupt saved record) and frame pacing at 50/60/120/144 Hz with jitter, dropped frames, the automatic drop to 60 and `?hz`. It also checks that visual-only effects step once per frame, that quakes stay `QUAKE.calm` apart and that the pipes come back up at varied heights. The saucer must come at most once a night (and most nights), never with `?noclock`, and leave the dish behind. The same seed must give the same game. |
| `balance/*.test.mjs` | 60 seeded autopilot games each (set `BALANCE_GAMES` for more), for the default settings, `?noclock` and `?tvs`. The average and median scores must stay in range, the bottom 10% must not crash early, and pipes must cause most deaths. Lightning, saucers, hawks and flytraps each stay under a cap, and the autopilot never flies into the ground. |
| `browser.test.mjs` | The real page in headless Chrome. Every mode and URL option (`?tv`, `?tvs`, `?tod`, `?2d`, `?scan=`, `?noclock`, `?env=`, `?fps`, `?prof`, `?lowres`, `?hz`, `?daylen`, `?resetstats`, snow/sand) must load and run at phone, desktop and TV sizes with no errors and no page overflow. It also checks the canvas pixel cap on a 4K screen in both renderers. WebGL must be the default and `?2d` must give Canvas 2D, with the right canvases shown. Losing the WebGL context must drop to 2D and keep the game running, and `SCAN_STYLE` must follow `?scan=`. It plays out each event: a crash with the stats card and restart, an abduction followed by the Morse dish, a quake, a storm with lightning, a hawk, a flytrap, DISCO from the button, and the ENV slider. |
| `snapshot.test.mjs` | Eighteen scenes made from a seeded random and a frozen clock. Each is loaded with `&2d` and compared pixel for pixel with `snapshots/*.png`. A second block, "GL matches 2D", draws each scene in WebGL (with `&shadow=classic`) and in 2D and compares them with a tolerance (see below). A third, "GL shadow styles", renders two scenes in each of `dither`, `smooth`, `blocky` and `off` and compares them with `snapshots/gl-<scene>-<style>.png`. Skipped where WebGL is unavailable. |
| `bench.mjs` | Not a test. `npm run bench` (see below). |

## When a snapshot fails

A failure writes `tests/out/<scene>.actual.png` and `<scene>.diff.png`, with the changed pixels in red, then:

- If the change was not meant to happen (a speed-up, a refactor), it is a bug. Fix it.
- If it was meant (new art, a new HUD line), look at the images. If they are right, run `npm run test:update` and commit the new PNGs.

The reference images come from Chrome's software renderer. A Chrome upgrade can shift a few pixels, which means re-accepting them once.

## GL against 2D

WebGL is the default renderer and `?2d` forces Canvas 2D. The snapshot references are the 2D look, so they stay exact. The GL renderer cannot match them bit for bit, so "GL matches 2D" renders the same scene both ways and compares in the page. A pixel differs when its largest channel difference is over `TOL_CH` (8 of 255). A scene fails when more than `TOL_PCT` percent of its pixels differ (1.0). Both constants are at the top of `snapshot.test.mjs`. A failure writes `tests/out/<scene>.gl.png`, `<scene>.2d.png` and `<scene>.gldiff.png`. Set `GL_DIFF_LOG=1` to print each scene's percentage.

`?scan=lines|soft|grille|delta|slot|off` picks the scanline style (default `lines`; `SCAN_STYLE` holds the effective one). The 2D path only has `lines` and `off`, so `delta` and `slot` report `lines` there. `?bloom=N` sets the glow (`BLOOM`; 1 for delta/slot, 0 otherwise, 0 in 2D). "GL screen styles" renders one seeded scene at DPR 1 in a viewport that gives exactly 3 device px per game px, reads the SCREEN canvas back right after `draw()` (`GLR.screenDataURL`, a crop) for `delta`, `slot`, `delta&bloom=0` and `lines`, and compares each with `snapshots/gl-screen-<style>.png` (the other snapshots stop before the final pass, so they never see the masks). It also checks that `delta` differs from `lines` and `bloom=0` from bloom.

`?shadow=dither|smooth|blocky|classic|off` picks the shadow style (GL default `dither`; `SHADOW_STYLE` holds the effective one). `classic` is the flat brown shadow of the 2D path; the others are soft shadows from a mask pass and one shader pass, as tinted light, with a penumbra that widens with distance (`dither` quantizes it with a 4x4 Bayer on the game's pixel grid, `blocky` quantizes without dither, `smooth` is continuous). In 2D only `classic` and `off` exist, and a lost GL context drops to `classic`. "GL shadow styles" uses a tolerance of its own against references made by `UPDATE_SNAPSHOTS=1`, and checks that `off` differs from `dither`.

## Benchmark

`npm run bench` opens three scenes (phone, TV, TV with night snow) in WebGL and in 2D with `?fps`, waits 8 s and reads the readout three times. It prints FPS, SIM and DRAW ms per frame, and how many times faster WebGL draws. The CPU is throttled by `BENCH_THROTTLE` (default 6).

## Writing a test

`loadGame({ search, seed, storage, screen })` runs the game's script in Node. Its `ev(code)` evaluates `code` inside the game's own scope, so it can read any variable (`ev("stats.runs")`), call any function (`ev("die(birdX, bird.y, 'pipe')")`) or wrap one (`ev("startQuake = wrap(startQuake)")`). The game's internal calls see the wrapped version. `run(seconds)` steps the game at 1/120 s.

`lib/chrome.mjs` drives headless Chrome with a throwaway profile. `page.ev()` evaluates in the page, and `page.errors` collects any exceptions.
