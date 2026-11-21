# Flappy Seasons: URL options

`flappy-seasons.html` is a self-playing 8-bit Flappy demo. Open it in a browser and it plays by itself. You can change how it looks, how fast its clock runs, what the weather does, and how it draws, all with options in the page address.

## How to give options

Options go after the file name, starting with `?`. Separate them with `&`:

```
flappy-seasons.html?tvs&fps
flappy-seasons.html?season=2&hour=21&noclock
```

There are two kinds of option:

- **Flags** have no value. `?tvs`, `?fps`, `?2d` are flags. Their presence turns them on. Any value after `=` is ignored for a flag, but do not rely on that.
- **Values** take `=` and a number, or one of a fixed set of words. `?daylen=60`, `?scan=soft`.

Options combine freely unless the table below says otherwise. Each option is read once, when the page loads. The one exception is the ENV slider, which writes its value back into the address (see [ENV slider and DISCO button](#env-slider-and-disco-button)).

Values that do not parse are ignored, and the default is used. For example `?daylen=-5` or `?hour=abc` behaves as if the option were absent (for `daylen`, a value that is not greater than 0 is ignored).

### Quick start

| You want | Use | Notes |
|---|---|---|
| A TV, filling the screen | `?tvs` | Scrolling world, bird held in the middle. Click or press Enter/F for fullscreen. |
| A TV with the timings shown | `?tvs&fps` | Frame rate and timings are drawn on the picture. |
| To see the night | `?hour=23` | Starts the clock at 23:00. |
| A quick day cycle | `?daylen=60` | One full day every 60 seconds instead of 240. |
| A slow device | `?lowres` or `?2d` | Lower-cost drawing. `?2d` skips WebGL altogether. |
| A steady frame rate on a fast screen | `?hz=60` | Pins the game to 60 frames a second. |

---

## Display

### `tv`

- **Syntax:** `?tv` (flag)
- **Default:** off.
- **What it does:** Makes the world as wide as the screen, so the picture fills a 16:9 TV edge to edge. The game still has a still stage with the bird flying across it. The ENV slider, the DISCO button, and the on-page caption are hidden, and the mouse pointer is hidden.
- **Example:** `flappy-seasons.html?tv`
- **Interactions and caveats:**
  - The width comes from the screen's shape (or the window's, if the window is narrower), so going fullscreen does not change the layout.
  - Click the page, or press Enter or F, to toggle fullscreen.
  - `?tv` and `?tvs` both set the TV layout. If both are given, `?tvs` wins.

### `tvs`

- **Syntax:** `?tvs` (flag)
- **Default:** off.
- **What it does:** The same TV layout as `?tv`, but the world scrolls as usual and the bird is held in the middle of the screen. The bird flies in from the left over the first 3 seconds, then stays there.
- **Example:** `flappy-seasons.html?tvs`
- **Interactions and caveats:** Everything in `?tv` applies. Use `?tvs` for a TV on a wall, and `?tv` if you want the stage with the bird crossing it.

### `scan`

- **Syntax:** `?scan=lines`, `?scan=soft`, `?scan=grille`, `?scan=delta`, `?scan=slot`, or `?scan=off`
- **Default:** `lines`. Any other value is treated as `lines`.
- **What it does:** Sets the scanline pattern laid over the picture.
  - `lines` is thin dark lines. `soft` and `grille` are other patterns, and `off` draws no scanlines.
  - `delta` imitates a shadow-mask tube, as in a small 1980s-90s colour monitor or console TV. There is one beam per game row, as on a 240p CRT: bright pixels get a fat beam that nearly fills the gap, dark pixels get a thin one with a clear dark gap. On top of that sit the phosphor dots in red, green and blue, in triads that form triangles (each band of dots is shifted half a triad from the one above). The brightness is raised to make up for the mask, and it glows (see `bloom`).
  - `slot` imitates the slot mask or stagger block of later consumer TVs. It has the same beams, but the phosphors are tall red, green and blue slots, each followed by a thin dark gap, and every other triad is shifted down half a slot, so the gaps make a staggered brick pattern. It also glows.
- **Example:** `flappy-seasons.html?scan=delta`
- **Interactions and caveats:**
  - With WebGL, all six styles work.
  - With `?2d` (or when WebGL is not available), the scanlines are a plain canvas overlay that only ever draws `lines`. `soft` and `grille` look the same as `lines` there, and so do `delta` and `slot` (`SCAN_STYLE` reports `lines`). `off` removes them.
  - `delta` and `slot` draw the CRT picture at a whole number of screen pixels per game pixel (2, 3, 4...), so every beam and dot has the same shape. How that picture meets the window is set by [`crtfit`](#crtfit): by default it is resized smoothly to fill the window. Below 2 screen pixels per game pixel there is no room for a beam, and they fall back to a gentle alternate-row shading with the same dots.
  - The shake moves the picture under the beams and the mask, which stay fixed to the screen.

### `bloom`

- **Syntax:** `?bloom=N`, where N is a number from 0 to 4
- **Default:** `1` with `?scan=delta` and `?scan=slot`, `0` with the other styles.
- **What it does:** Adds a glow around bright things (the moon, the sun, the bird's highlights, lightning, the saucer), as the light of a real tube spills over. `N` is the strength: `0` is no glow, `2` is twice as strong. The bright parts of the picture are blurred at a quarter of the game's resolution and added before the mask, so the glow shows the dots of the phosphor pattern, and it fattens bright scanlines so their gaps fill in. It costs little, because the work is done at that small size.
- **Example:** `flappy-seasons.html?scan=delta&bloom=0.5`, or `flappy-seasons.html?scan=grille&bloom=1` to add it to another style.
- **Interactions and caveats:**
  - It needs WebGL. With `?2d` there is no bloom.

### `crtfit`

- **Syntax:** `?crtfit=fill` or `?crtfit=exact`
- **Default:** `fill`.
- **What it does:** Sets how the `delta` and `slot` scanlines fit a window that is not an exact multiple of the game's size.
  - `fill` draws the CRT picture offscreen at the next whole scale up (every game pixel exactly k x k screen pixels), then shrinks it smoothly to fill the window. No borders and no uneven rows. The picture is a touch softer, like a real tube.
  - `exact` puts the picture on the screen at exactly k x k screen pixels per game pixel. Every dot is pixel-perfect, but it leaves black bars around the picture unless the window is close to a whole multiple. When the next scale up only crops 3% or less at the edges, it uses that scale and crops, like a TV's overscan.
- **Example:** `flappy-seasons.html?scan=slot&crtfit=exact`
- **Interactions and caveats:** Only matters for `?scan=delta` and `?scan=slot` with WebGL. The other scanline styles always fill the window.

### `2d`

- **Syntax:** `?2d` (flag)
- **Default:** off. The game uses WebGL when the browser supports it.
- **What it does:** Turns off WebGL and draws with the plain 2D canvas. Use it on a device where WebGL is slow or misbehaves, or to compare the two renderers.
- **Example:** `flappy-seasons.html?2d&fps`
- **Interactions and caveats:**
  - `?fps` shows `2D` in the last readout line where it would otherwise show `GL`.
  - `shadow` cannot use its soft styles in 2D. Only `classic` and `off` are available, and any other value becomes `classic`.
  - If the WebGL context is lost during play, the game switches to 2D by itself.

### `lowres`

- **Syntax:** `?lowres` (flag)
- **Default:** off.
- **What it does:** Paints the scene at one buffer pixel per logical pixel, and lets the browser stretch it to the screen. This is much cheaper on a large or high-density screen. The picture is blockier.
- **Example:** `flappy-seasons.html?lowres`
- **Interactions and caveats:** Without it, the buffer is the largest whole multiple of the screen's pixel density that stays under about 2.1 million pixels. `lowres` always uses the smallest buffer.

---

## Time and seasons

### `season`

- **Syntax:** `?season=N`, where N is a number (fractions allowed). The value wraps every 4, so `season=4` is the same as `season=0`.
- **Default:** the season saved in the browser, or spring (`0`) if nothing is saved.
- **What it does:** Starts the game in a given season. `0` is spring, `1` summer, `2` autumn, and `3` winter. Fractions start partway through a season.
- **Example:** `flappy-seasons.html?season=3`
- **Interactions and caveats:**
  - The value replaces the saved season at load. The game saves its season again every few seconds, so the URL value becomes the saved one.

### `seasonlen`

- **Syntax:** `?seasonlen=N`, a number of seconds greater than 0.
- **Default:** `28` seconds per season.
- **What it does:** Sets how long each season lasts. The last 9 seconds of a season (or half the season, if shorter) fade into the next.
- **Example:** `flappy-seasons.html?seasonlen=10`
- **Interactions and caveats:** A value that is not greater than 0 is ignored. The DISCO button changes the season length while it runs and restores it when it ends.

### `daylen`

- **Syntax:** `?daylen=N`, a number of seconds greater than 0.
- **Default:** `240` seconds for a full day and night.
- **What it does:** Sets how long one full day takes on the simulated clock. The night takes a bit over a third of it.
- **Example:** `flappy-seasons.html?daylen=60`
- **Interactions and caveats:**
  - Has no effect with `?tod`, which follows the real clock.
  - Has no effect with `?noclock`, which has no day cycle.

### `hour`

- **Syntax:** `?hour=N`, a number from 0 to 24. Values outside that range wrap (`hour=25` is the same as `hour=1`). Fractions are allowed.
- **Default:** the hour saved in the browser, or `8` if nothing is saved.
- **What it does:** Sets the time of day at load. The day cycle then runs on from that hour.
- **Example:** `flappy-seasons.html?hour=23`
- **Interactions and caveats:**
  - Ignored with `?tod`, which sets the hour from the clock on every frame.
  - The hour shown on screen is the hour of the day (DAWN, MORNING, MIDDAY, AFTERNOON, DUSK, NIGHT) with the time under it, unless `?noclock` is on.

### `tod`

- **Syntax:** `?tod` (flag)
- **Default:** off. The simulated clock runs on its own.
- **What it does:** Follows the time on the device watching. The sun, the moon (in its real phase), and the clock on screen all match the real local time.
- **Example:** `flappy-seasons.html?tod`
- **Interactions and caveats:**
  - Overrides `hour` and `daylen`.
  - Has no effect with `?noclock`. If both are given, `?noclock` wins.

### `noclock`

- **Syntax:** `?noclock` (flag)
- **Default:** off.
- **What it does:** Turns off the day cycle. The sun swings slowly to and fro across the sky, the clock text is hidden, and the moon, stars, shooting stars and flying saucers are not drawn.
- **Example:** `flappy-seasons.html?noclock`
- **Interactions and caveats:** Overrides `tod`, `hour` and `daylen`.

---

## Weather and world

### `env`

- **Syntax:** `?env=N`, a number greater than or equal to 0. `0` means OFF.
- **Default:** `1` (x1).
- **What it does:** Sets the environment strength for the wind, the sun's heat, and ice. It is the setting of the ENV slider. `0` is OFF, no wind, no heat, and no ice. `1` is the normal setting. Above `2` the wind gets harsh, and at `20` it is extreme.
- **Example:** `flappy-seasons.html?env=0`
- **Interactions and caveats:**
  - Values outside the slider's range are kept until you move the slider.
  - The ENV setting is not saved in the browser. It lives in the URL. See [ENV slider and DISCO button](#env-slider-and-disco-button).
  - DISCO sets `env` to 20 while it runs, and puts back the value it had when it ends.

### `wind`

- **Syntax:** `?wind=N`, a number greater than or equal to 0.
- **Default:** `1`.
- **What it does:** Multiplies the wind on its own, on top of the ENV setting and the season's own wind. `?wind=0` gives calm air in every season, and `?wind=2` doubles the wind.
- **Example:** `flappy-seasons.html?env=0&wind=2`
- **Interactions and caveats:** This is a separate knob. It does not change the ENV slider's position or the `env` value in the URL. `?env=0` also turns off the wind, so `?wind` has no effect there.

### `sand`

- **Syntax:** `?sand=N`, a number. Negative values are treated as 0.
- **Default:** the sand depth saved in the browser, or 0.
- **What it does:** Sets how deep the sand on the ground is at load. Sand drifts across the ground, banks against the pipes, and heaps on the bottom lips.
- **Example:** `flappy-seasons.html?sand=50`
- **Interactions and caveats:** The sand and snow depths are saved in the browser with the season clock. The value in the URL replaces the saved one at load and is saved in turn.

### `snow`

- **Syntax:** `?snow=N`, a number. Negative values are treated as 0.
- **Default:** the snow depth saved in the browser, or 0.
- **What it does:** Sets how deep the snow on the ground is at load. Snow lies on top of the sand, and the sun melts it.
- **Example:** `flappy-seasons.html?snow=50&season=3`
- **Interactions and caveats:** The same rules as `sand`.

### `flair`

- **Syntax:** `?flair=N`, a number greater than or equal to 0.
- **Default:** `1`.
- **What it does:** Sets how often the scenery sightings appear. Trains, blimps, geese, flocks, the yeti, the groundhog, gophers, the hawk, the woodpecker on the pipes, the flying saucer and a few others all come from this. `?flair=4` is four times as often.
- **Example:** `flappy-seasons.html?flair=0`
- **Interactions and caveats:**
  - `?flair=0` turns all of them off, including the hawk and the flying saucer. The hawk can take the bird, so `?flair=0` also removes that risk.
  - The flying saucer only appears at night, and does not appear with `?noclock`.

### `quake`

- **Syntax:** `?quake=N`, a number greater than or equal to 0.
- **Default:** `1`.
- **What it does:** Sets how often earthquakes happen. The ground rumbles, then the pipes topple flat and the ground cracks open. The bird gets a free pass for 30 seconds while the pipes lie down.
- **Example:** `flappy-seasons.html?quake=0`
- **Interactions and caveats:**
  - `?quake=0` turns earthquakes off altogether.
  - Values above 1 make them more frequent. The minimum wait between two quakes is 240 seconds divided by the value (240 seconds at 1 or below).

---

## Rendering

### `shadow`

- **Syntax:** `?shadow=dither`, `?shadow=smooth`, `?shadow=blocky`, `?shadow=classic`, or `?shadow=off`
- **Default:** `dither`. Any other value is treated as `dither`.
- **What it does:** Sets how the shadows of the pipes and the ground are drawn.
  - `dither` is a soft shadow with an ordered pattern in place of smooth shading. It is the default.
  - `smooth` is a soft shadow with smooth shading.
  - `blocky` is a soft shadow stepped to four flat tones, with no pattern.
  - `classic` is the original hard-edged shadow, drawn row by row.
  - `off` draws no shadows.
- **Example:** `flappy-seasons.html?shadow=smooth`
- **Interactions and caveats:**
  - The soft styles need WebGL. With `?2d`, or if WebGL cannot draw the shadows, `dither`, `smooth` and `blocky` become `classic`. `off` stays `off`.
  - Shadows are fainter under cloud and in winter, whatever the style.

### `hz`

- **Syntax:** `?hz=N`, a refresh rate greater than 0 (for example `60`, `30`).
- **Default:** off. The game learns the display's refresh rate. On a fast display that it cannot keep up with, it draws on every other refresh by itself.
- **What it does:** Sets the frame rate outright. The game draws on every k-th refresh, where k is the screen's refresh rate divided by N, rounded to a whole number. `?hz=60` on a 120 Hz screen draws every second refresh. `?hz=30` on a 60 Hz screen draws every second refresh.
- **Example:** `flappy-seasons.html?hz=60&fps`
- **Interactions and caveats:**
  - A value higher than the screen's refresh rate has no effect (`?hz=144` on a 60 Hz screen runs at 60).
  - With `?hz` set, the automatic every-other-refresh adjustment is off. The game uses the rate you gave.
  - On a 60 Hz screen, `?hz=60` changes nothing.

---

## Diagnostics

### `fps`

- **Syntax:** `?fps` (flag)
- **Default:** off.
- **What it does:** Draws two lines of timing numbers in the bottom-right corner of the picture. These are the frame rate, the refresh rate, the frame-time figures, the size of the scene buffer, and which renderer is in use. The lines are explained in [Reading the ?fps and ?prof readouts](#reading-the-fps-and-prof-readouts).
- **Example:** `flappy-seasons.html?tvs&fps`
- **Interactions and caveats:** The numbers are refreshed once a second. Measuring costs a little time, so the numbers are near the real figures, not exact.

### `prof`

- **Syntax:** `?prof` (flag)
- **Default:** off.
- **What it does:** Times the parts of the game that do the work each frame, and shows the six most expensive in milliseconds per frame, near the top middle of the picture. The list refreshes every 2 seconds. Nothing appears until the first 2 seconds have passed.
- **Example:** `flappy-seasons.html?prof`
- **Interactions and caveats:**
  - Timing each part adds a little work of its own, so the numbers run a little high.
  - A part that calls another part is counted in both. Their numbers overlap, so do not add them up.
  - `?fps` and `?prof` can be given together. Their readouts are in different places.

### `resetstats`

- **Syntax:** `?resetstats` (flag)
- **Default:** off.
- **What it does:** Clears the death statistics saved in this browser (the run count, the crash counts, the best score, and the scores by ENV level) when the page loads. The stats card after a crash starts again from zero.
- **Example:** `flappy-seasons.html?resetstats`
- **Interactions and caveats:**
  - The option is read on every load, so while it stays in the address, the stats are cleared on every reload. Remove it from the address after you have cleared them.
  - The stats are kept per browser, not per URL.

---

## ENV slider and DISCO button

The bottom of the page has two controls. Both are hidden with `?tv` and `?tvs`.

**ENV slider.** It sets the environment strength, the same as `?env=`. The far-left notch is OFF. From there the slider runs from x0.1 to x20 on a log scale, with a notch at x1. The label shows the value and its strength (`harsh` above x2, `extreme` at x20). With the keyboard, the arrow keys move the slider in notches, Page Up and Page Down move it further, and Home and End jump to OFF and x20.

When the slider changes, the game writes the new value into the address as `env=`, using `history.replaceState`. The rest of the address is kept, so a reload keeps the setting. The ENV setting is kept only in the address, not in the browser's saved data.

**DISCO button.** It runs a 60-second party: every season at once, the seasons flip every 6 seconds (with a shorter fade), and the ENV setting goes to x20. The HUD shows the time left. Pressing the button again ends it early. Moving the ENV slider also ends it, at the new setting. When it ends, the season length and ENV setting go back to what they were.

---

## Reading the ?fps and ?prof readouts

### The `?fps` readout

The `?fps` readout has two lines, drawn in the bottom-right corner. The numbers are updated once a second.

First line:

```
N FPS HZ[/k] MAX m JIT j
```

- **FPS** is the number of frames drawn in the last second.
- **HZ** is the display's refresh rate, as the game has learned it, rounded to a whole number.
- **HZ/2** (or `/3` and so on) appears when the game is drawing on every second (or third) refresh, either because the device cannot keep up with a fast screen, or because `?hz` asked for a lower rate. The `/k` is the number of refreshes per frame. A steady 60 on a 120 Hz screen shows `120HZ/2`.
- **MAX** is the longest gap between two frames in the last second, in milliseconds.
- **JIT** is the typical deviation of the frame timing from the refresh grid, in milliseconds. Small is smooth. Large means the frames are uneven, even if the FPS number looks fine.

Second line:

```
SIM s DRAW d WxH RENDERER
```

- **SIM** is the average time per frame spent moving the world (the game's logic), in milliseconds.
- **DRAW** is the average time per frame spent painting the picture, in milliseconds.
- **WxH** is the size of the internal scene buffer in pixels. It is the logical size (288 by 512, or wider with `?tv`/`?tvs`) times the buffer scale. A small buffer means `?lowres` or a small screen. Compare it with the window size to see how much the GPU has to stretch.
- **RENDERER** is `GL` for WebGL, or `2D` for the Canvas 2D fallback.

### The `?prof` readout

The `?prof` list shows the six parts of the game that take the most time, one per line, in the form:

```
NAME  x.x
```

`NAME` is the function name in upper case. The number is its average time per frame in milliseconds over the last 2 seconds. The list is ordered from most to least expensive. Nested calls are counted in both their own line and the line of the part that calls them. So a line can be part of another line, and the numbers do not add up to the frame time.

---

## Troubleshooting

**The game stutters on a TV.**
Open it with `?fps&prof`. Compare `SIM` and `DRAW` in the `?fps` readout. If `DRAW` is large, the picture is the cost. If `SIM` is large, the game logic is.

**The picture looks slow but the numbers look fine.**
Check `JIT` and `MAX` in the `?fps` readout. A high `JIT` or `MAX` with a reasonable FPS means the frames are uneven, which is usually the fast-screen problem. Try `?hz=60`.

**Compare with the plain renderer.**
Open the page with `?2d` and then without it. If `?2d` is smoother, the WebGL path is the slow part on this device, and `?2d` is the way to play it.

**Still slow.**
Try `?lowres` to draw fewer pixels. Combine it with `?2d` if needed, and with `?shadow=off` to drop the soft shadows.

**The frame rate is uneven on a 120 Hz screen.**
Pin the rate with `?hz=60`. The game then draws on every second refresh, a steady 60.
