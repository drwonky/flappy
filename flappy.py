#!/usr/bin/env python3
"""
flappy-vt100  --  self-playing Flappy Bird for an 80x25 terminal.

  python3 flappy-vt100.py            UTF-8 half-blocks + 4-bit colour (80x48 sub-pixels)
  python3 flappy-vt100.py --vt100    strict DEC Special Graphics, mono, 4 tones, ESC(0
  python3 flappy-vt100.py --frames 6 print 6 text frames and exit (no tty needed)
  python3 flappy-vt100.py --selftest 40 headless games -> crash distribution
  --seed N  --fps N  --stats (bytes/frame, for 9600-baud curiosity)

Everything physical lives in SUB-PIXEL units (1 col x 1 half-cell = square).
"""
import sys, time, math, random

COLS, ROWS      = 80, 25
HUD             = 1                      # row 0 = score/hud
FH              = ROWS - HUD             # 24 field cells
SUBH          = 2 * FH                   # 48 sub-rows
GROUND        = 8                        # sub-rows of ground
SKY           = SUBH - GROUND            # 40 sub-rows of flyable sky

# ---- physics: time is the honest shared dimension between the original and
# a 25-row terminal, so FLAP/GRAVITY is pinned to the original's hover period.
GRAV   = 177.8     # sub-rows/s^2   ( = FLAP/HOVER )
FLAP   = 53.3      # sub-rows/s     -> apex = FLAP^2/2GRAV = 8 = 20% of sky
MAXVY  = 56.0
FIXED  = 1.0/60.0
COOLD  = 0.34      # > HOVER, so the bird cannot hover; every flap is committed
HOVER  = FLAP/GRAV

BIRD_X = 14
HRX, HRY = 4, 3                        # hitbox, sub-pixels
PIPE_W = 14                            # cols; original pipe = 18% of width
CAP_H  = 3                             # sub-rows of pipe lip

SPEED0, SPEED1 = 16.0, 26.0            # cols/s
GAP0, GAP1     = 19.0, 12.0            # sub-rows (GAP1/SKY = 30%)
SPACE0, SPACE1 = 1.30, 0.95            # seconds between pipes
TAU            = 85.0                  # asymptote: never a hard difficulty wall

K, MARGIN_FRAC, WOBBLE_FRAC = 0.30, 0.06, 0.12

# ---- tone ramps.  DEC's only shade is 0x61; the set carries no 0.25/0.75
# shade, so mid tones come from the diamond and the middot.
UNI_GLYPH = (" ", "\u2591", "\u2592", "\u2593", "\u2588")
DEC_TONE  = (" ", "~", "`", "a")           # space, ., diamond, chequerboard
DEC_LINE  = {"h": "q", "v": "x", "tl": "l", "tr": "k", "bl": "m", "br": "j",
             "lt": "t", "rt": "u", "tu": "w", "td": "v", "cr": "n"}
# CUP/EL/DECSC/DECRC; hide-cursor is VT220, alt-buffer is xterm -> --vt100 skips them
CUP, EL, SGR0, SGR = "\x1b[%d;1H", "\x1b[K", "\x1b[0m", "\x1b[%dm"
GON, GOFF = "\x1b(0", "\x1b(B"

BAYER = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))

# palette slots -> SGR fg (colour mode only; a real VT100 is monochrome)
PAL = {"far": 34, "near": 36, "cloud": 37, "pipe": 32, "pipehi": 92,
       "ink": 30, "ground": 33, "bird": 93, "beak": 91, "hud": 37}

class Scene:
    def __init__(self, vt100):
        self.vt100 = vt100
        self.lum = [[0.0]*COLS for _ in range(SUBH)]
        self.pal = [[None]*COLS for _ in range(SUBH)]

    def put(self, y, x, v, p=None):
        if 0 <= y < SUBH and 0 <= x < COLS:
            self.lum[y][x] = v
            self.pal[y][x] = p

    def rect(self, x0, y0, w, h, v, p=None):
        for y in range(int(y0), int(y0+h)):
            for x in range(int(x0), int(x0+w)):
                self.put(y, x, v, p)

    def ell(self, cx, cy, rx, ry, v, p=None):
        """axis-aligned ellipse in sub-pixels; edge pixels get an outline."""
        for y in range(int(cy-ry)-1, int(cy+ry)+2):
            for x in range(int(cx-rx)-1, int(cx+rx)+2):
                dx, dy = (x-cx)/float(rx), (y-cy)/float(ry)
                d = dx*dx + dy*dy
                if d <= 1.0:
                    # light from upper-left -> give it a real shaded body
                    t = max(0.0, min(1.0, 0.5 - 0.5*(dx+dy)))
                    self.put(y, x, v*(0.72+0.36*t), p)
                elif d <= 1.9:
                    self.put(y, x, 0.10, "ink")

# ------------------------------------------------------------------ world
class Game:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.reset()

    def reset(self):
        self.y, self.vy = SKY*0.45, 0.0
        self.pipes, self.score, self.best = [], 0, getattr(self, "best", 0)
        self.cooldown, self.since = 0.0, 1e9
        self.aim, self.dead, self.deadT = 0.0, False, 0.0
        self.clock, self.wing = 0.0, 0.0
        self.speed, self.gap, self.space = SPEED0, GAP0, SPACE0
        self.flaps = 0

    def ramp(self):
        k = 1.0 - math.exp(-self.score/TAU)
        self.speed = SPEED0 + (SPEED1-SPEED0)*k
        self.gap   = GAP0   + (GAP1-GAP0)*k
        self.space = SPACE0 + (SPACE1-SPACE0)*k

    def usable(self):
        return self.gap - 2*HRY

    def spawn(self):
        top = 4 + self.rng.random()*(SKY - 8 - self.gap)
        self.pipes.append({"x": float(COLS), "top": top, "bot": top+self.gap, "pass": False})
        self.aim = (self.rng.random()*2-1)*self.usable()*WOBBLE_FRAC

    def want_flap(self, n):
        tgt = 0.5*(n["top"]+n["bot"]) + self.aim
        if (self.y - tgt) + K*self.vy <= 0:      # switching curve, not "am I low"
            return False
        apex = self.y - FLAP*FLAP/(2*GRAV)
        return apex >= n["top"] + HRY + self.usable()*MARGIN_FRAC

    def step(self, dt):
        self.clock += dt
        self.wing = max(0.0, self.wing - dt*6)
        if self.dead:
            self.deadT += dt
            if self.deadT > 1.3: self.reset()
            return
        self.ramp()
        self.since += self.speed*dt
        if self.since >= self.speed*self.space:
            self.since, _ = 0.0, self.spawn()
        self.cooldown -= dt
        nxt = next((p for p in self.pipes if p["x"]+PIPE_W > BIRD_X-HRX), None)
        if nxt and self.cooldown <= 0 and self.want_flap(nxt):
            self.vy, self.cooldown, self.wing = -FLAP, COOLD, 1.0
            self.flaps += 1
        self.vy = min(self.vy + GRAV*dt, MAXVY)
        self.y += self.vy*dt
        for p in self.pipes:
            p["x"] -= self.speed*dt
            if not p["pass"] and p["x"]+PIPE_W < BIRD_X-HRX:
                p["pass"] = True; self.score += 1
                self.best = max(self.best, self.score)
        self.pipes = [p for p in self.pipes if p["x"]+PIPE_W > -PIPE_W]
        if self.y+HRY >= SKY or self.y-HRY <= 0: self.die(); return
        for p in self.pipes:
            if (BIRD_X+HRX > p["x"] and BIRD_X-HRX < p["x"]+PIPE_W and
                (self.y-HRY < p["top"] or self.y+HRY > p["bot"])):
                self.die(); return

    def die(self): self.dead, self.deadT = True, 0.0

# ------------------------------------------------------------------ paint
def paint(g, sc):
    # ---- sky: banded luminance = aerial perspective (top lighter, near-void dark)
    for y in range(SUBH):
        v = 0.94 - 0.30*(y/float(SUBH))
        for x in range(COLS):
            sc.put(y, x, v, "cloud")
    # ---- far hills: lowest dither density, so they recede
    off = g.clock*g.speed*0.18
    for i in range(10):
        x = int(((i*22 - off) % (COLS+22)) - 11)
        sc.rect(x, SKY-14, 18, 14, 0.52, "far")
    # ---- near hills: denser + darker, sits in front
    off = g.clock*g.speed*0.42
    for i in range(8):
        x = int(((i*26 - off) % (COLS+26)) - 13)
        sc.rect(x, SKY-8, 20, 8, 0.38, "near")
    # ---- clouds, bright enough to sit above the haze
    off = g.clock*g.speed*0.10
    for i in range(4):
        x = int(((i*37 - off) % (COLS+30)) - 15)
        y = 5 + (i % 3)*7
        sc.rect(x, y, 16, 3, 1.0, "cloud")
        sc.rect(x+4, y-2, 8, 2, 1.0, "cloud")
    # ---- pipes: cylindrical shading + hard outline + lip (Mario grammar)
    for p in g.pipes:
        x = int(round(p["x"]))
        for y0, y1, top in ((0, p["top"], True), (p["bot"], SKY, False)):
            y0, y1 = int(y0), int(y1)
            for y in range(y0, y1):
                sc.put(y, x,        0.16, "ink")          # outline
                sc.put(y, x+1,      0.80, "pipehi")       # specular strip
                sc.put(y, x+2,      0.62, "pipe")
                for c in range(3, PIPE_W-3):
                    sc.put(y, x+c,  0.52 - 0.28*(c-3)/float(PIPE_W-6), "pipe")
                sc.put(y, x+PIPE_W-3, 0.30, "pipe")
                sc.put(y, x+PIPE_W-2, 0.14, "pipe")       # terminator
                sc.put(y, x+PIPE_W-1, 0.16, "ink")        # outline
                sc.put(y, x+PIPE_W,   0.11, "ink")        # cast shadow
            cap = y1-CAP_H if top else y0
            for y in range(cap, cap+CAP_H):
                for c in range(-1, PIPE_W+1):
                    sc.put(y, x+c, 0.86 if c < 2 else 0.20 if c > PIPE_W-4 else 0.58, "pipe")
                sc.put(y, x-2, 0.16, "ink"); sc.put(y, x+PIPE_W+1, 0.13, "ink")
            for c in range(-2, PIPE_W+2):
                sc.put(cap,       x+c, 0.92, "pipehi")
                sc.put(cap+CAP_H-1, x+c, 0.10, "ink")
    # ---- ground: hard grass edge, dithered dirt, scrolling texture
    sc.rect(0, SKY, COLS, 2, 0.78, "ground")
    sc.rect(0, SKY+2, COLS, GROUND-2, 0.44, "ground")
    off = int((g.clock*g.speed) % 12)
    for x in range(-12, COLS+12, 12):
        sc.rect(x-off, SKY+4, 6, GROUND-4, 0.30, "ground")
    sc.rect(0, SUBH-2, COLS, 2, 0.20, "ink")
    # ---- bird: 11x7 sub-pixels, lit upper-left, outlined, wing beats
    cx, cy = BIRD_X+5, int(round(g.y))
    sc.ell(cx, cy, 5, 3, 0.86, "bird")
    sc.ell(cx+4, cy-2, 2, 2, 0.92, "bird")
    sc.put(cy-2, cx+5, 1.0, "cloud"); sc.put(cy-2, cx+4, 0.12, "ink")
    sc.rect(cx+6, cy-1, 2, 2, 0.90, "beak")
    sc.ell(cx-1, cy+int(round(1.0-g.wing*2)), 3, 1, 0.55, "bird")
    if g.dead:
        f = max(0.0, 0.55*(1.0-g.deadT/0.35))
        for y in range(SUBH):
            for x in range(COLS):
                sc.lum[y][x] = sc.lum[y][x]*(1-f) + 0.95*f

def render(sc):
    """luminance -> glyphs, via ordered 4x4 Bayer dithering."""
    rows = []
    for r in range(FH):
        a, b = r*2, r*2+1
        out, last = [], -1
        for x in range(COLS):
            ba = BAYER[a & 3][x & 3]/16.0
            bb = BAYER[b & 3][x & 3]/16.0
            if sc.vt100:
                v = 0.5*(sc.lum[a][x] + sc.lum[b][x]) + (ba-0.5)*0.25
                g = DEC_TONE[max(0, min(3, int(v*4)))]
            else:
                top = sc.lum[a][x] > ba
                bot = sc.lum[b][x] > bb
                g = ("\u2588" if top and bot else "\u2580" if top
                     else "\u2584" if bot else " ")
            out.append(g)
            if g != " ": last = x
        out = out[:last+1] if last >= 0 else []
        rows.append((sc.pal[a][0], out))
    return rows

# ------------------------------------------------------------------ output
class TTY:
    def __init__(self, vt100, colour, stats):
        self.vt100, self.colour, self.stats = vt100, colour and not vt100, stats
        self.prev, self.gmode, self.written = [""]*FH, None, 0

    def _emit(self, s):
        self.written += len(s.encode("latin-1", "replace"))
        sys.stdout.write(s)

    def home(self):
        if not self.vt100: self._emit("\x1b[?1049h\x1b[?25l")
        self._emit("\x1b[2J")

    def draw(self, rows, hud):
        buf = []
        buf.append(CUP % 1); buf.append(GOFF if self.gmode else "")
        self.gmode = None
        buf.append(hud[:COLS].ljust(COLS))
        for i, (pal, glyphs) in enumerate(rows):
            line = "".join(glyphs)
            if line == self.prev[i]:
                continue
            buf.append(CUP % (i+1+HUD))
            if self.vt100:
                need = any(c != " " for c in line)
                if need and self.gmode is None:
                    buf.append(GON); self.gmode = True
                if not need and self.gmode:
                    buf.append(GOFF); self.gmode = None
            if self.colour and pal:
                buf.append(SGR % PAL[pal])
            buf.append(line); buf.append(EL)
            if self.colour: buf.append(SGR0)
            self.prev[i] = line
        if self.gmode: buf.append(GOFF); self.gmode = None
        buf.append(CUP % ROWS)
        s = "".join(buf)
        self._emit(s)
        sys.stdout.flush()
        if self.stats:
            sys.stderr.write("frame %d bytes = %.2f s at 9600 baud\n"
                             % (self.written, self.written/960.0))

    def close(self):
        self._emit(SGR0 + GOFF + "\x1b(B")
        if not self.vt100: self._emit("\x1b[?25h\x1b[?1049l")

def hud_line(g):
    k = 1.0 - math.exp(-g.score/TAU)
    bar = int(20*k)
    return (" FLAPPY-VT100  SCORE %3d  BEST %3d  GAP %4.1f  SPD %4.1f  [%s%s] "
            % (g.score, g.best, g.gap, g.speed, "#"*bar, "."*(20-bar)))

def selftest(n, seed, fps):
    print("selftest: %d games, seed %s, step %.4f" % (n, seed, FIXED))
    scores = []
    for i in range(n):
        g = Game((seed or 1) + i*7919)
        for _ in range(int(60*8/fps)):
            g.step(FIXED)
            if g.dead: break
        scores.append(0 if not g.dead else g.score if False else g.score)
        if not g.dead: scores[-1] = -1
    died = sorted(s for s in scores if s >= 0)
    print("crashed  %d/%d" % (len(died), n))
    if died:
        q = lambda p: died[max(0, min(len(died)-1, int(p*(len(died)-1))))]
        print("crash score  min %d  p25 %d  median %d  p75 %d  max %d"
              % (died[0], q(.25), q(.5), q(.75), died[-1]))
        print("distinct crash scores: %d" % len(set(died)))
        print("deaths before pipe 20: %d" % sum(1 for s in died if s < 20))
    print("NOTE: if 'crashed' is 0, the pilot is too strong here -> raise GAP1")
    print("NOTE: if deaths cluster at one score, the ramp is a wall -> raise TAU")

def main():
    a = sys.argv[1:]
    vt100  = "--vt100" in a
    stats  = "--stats" in a
    frames = 0
    for i, x in enumerate(a):
        if x == "--frames": frames = int(a[i+1])
    if "--selftest" in a:
        seed = next((int(a[i+1]) for i, x in enumerate(a) if x == "--seed"), 1)
        selftest(next((int(a[i+1]) for i, x in enumerate(a) if x == "--n"), 40), seed, 60)
        return
    g, sc = Game(), Scene(vt100)
    if frames:                                     # no tty required
        for f in range(frames):
            for _ in range(int(1.0/(60*FIXED))): g.step(FIXED)
            paint(g, sc)
            print("\n".join("".join(r[1]) for r in render(sc)))
            print(hud_line(g))
        return
    t = TTY(vt100, True, stats); t.home()
    acc, last = 0.0, time.time()
    try:
        while True:
            now = time.time()
            acc = min(0.25, acc + now-last); last = now
            while acc >= FIXED: g.step(FIXED); acc -= FIXED
            paint(g, sc)
            t.draw(render(sc), hud_line(g))
            time.sleep(0.004)
    except KeyboardInterrupt:
        pass
    finally:
        t.close()

if __name__ == "__main__":
    main()
