#!/usr/bin/env python3
"""flappy-vt100 - self-playing Flappy Bird for an 80x25 terminal.

  python3 flappy-vt100.py             half-block art, 4-bit colour
  python3 flappy-vt100.py --vt100     strict DEC Special Graphics, mono
  python3 flappy-vt100.py --frames 5  print 5 frames, no tty
  python3 flappy-vt100.py --selftest  headless games -> crash statistics
  --seed N   --stats (bytes/frame, for 9600-baud curiosity)

DITHERING: the frame is a 160x48 SUB-PIXEL grid (2x2 sub-cells per character
cell, which is square on a terminal). Each sub-pixel is thresholded with an
ordered 4x4 Bayer matrix, then the resulting 2x2 pattern is mapped to the ONE
Unicode glyph that draws exactly that pattern - all 16 patterns have an exact
glyph (corner blocks, half blocks, ▚▞, three-quarter blocks, full block).
Shade is therefore carried by the DENSITY of the dither, not by painting
coverage blocks. Ink value = DARKNESS: sky is sparse, objects are dense.
"""
import sys, time, math, random

COLS, ROWS = 80, 25
HUD        = 1
FH         = ROWS - HUD
SW, SH     = COLS*2, FH*2
GROUND     = 10
SKY        = SH - GROUND
FIXED      = 1.0/60

# ---------- physics, all in SUB-PIXELS ----------
# Quoted original constants are per-frame at 60fps (gravity 0.5, flap -9) on a
# 512-tall screen with 400 of sky: one flap rises 81px = 0.203 of sky and takes
# 18 frames = 0.30s. Hover costs 2F/g = 0.36 of sky, i.e. 0.60s between flaps.
GRAV_F  = 0.20
APEX_T  = 0.30
FLAP    = 2*GRAV_F*SKY/APEX_T
GRAV    = FLAP/APEX_T
HOVER   = 2.0*FLAP/GRAV          # 0.60s
COOLD   = 0.50                   # < HOVER: hover possible but costs 83% of flaps
MAXVY   = 1.40*SKY
BIRD_X  = 0.278*SW
HW, HH  = 3.9, 3.0               # bird sprite is 8x6 sub-px; hitbox just inside
PIPE_W  = 29                     # 29/160 = 0.181 = original 52/288 screens
SPD0, SPD1 = 0.4167*SW, 0.5600*SW   # original 120px/s on 288 wide
SPC0, SPC1 = 0.625*SW, 0.500*SW     # original 169px on 288 -> 1.7 pipes visible
GAP0, GAP1 = 20.0, 16.0
TAU     = 85.0
APEX    = FLAP*FLAP/(2*GRAV)
SAFE    = (GAP1-2*HH)-APEX       # width of the safe-flap band at the asymptote

assert SAFE > 0, "asymptote is geometrically impossible"
assert COOLD < HOVER and COOLD > 0.30

class Game:
    def __init__(s, seed=None): s.rng = random.Random(seed); s.best = 0; s.reset()
    def reset(s):
        s.y, s.vy, s.pipes = SKY*0.42, 0.0, []
        s.score, s.cool, s.since, s.aim = 0, 0.0, 1e9, 0.0
        s.dead, s.deadT, s.clock, s.wing = False, 0.0, 0.0, 0.0
        s.speed, s.gap, s.space, s.flaps = SPD0, GAP0, SPC0, 0
    def ramp(s):
        k = 1.0 - math.exp(-s.score/TAU)
        s.speed = SPD0+(SPD1-SPD0)*k
        s.gap   = GAP0+(GAP1-GAP0)*k
        s.space = SPC0+(SPC1-SPC0)*k
    def spawn(s):
        top = 4 + s.rng.random()*(SKY-8-s.gap)
        s.pipes.append({"x": float(SW), "top": top, "bot": top+s.gap, "pass": False})
        s.aim = (s.rng.random()*2-1)*(s.gap-2*HH)*0.12
    # Thrust is one-sided: flapping at y puts your apex at y-APEX, so to cross
    # a gate you must enter no higher than top+HH+APEX (else you clip the upper
    # pipe) and no lower than bot-HH. Riding the TOP of that window is a limit
    # cycle whose parabola spans exactly APEX. Aim blends to the next gate early
    # enough to sink/climb to it, since descending costs only an abstained flap.
    def zlo(s, n): return n["top"]+HH+APEX
    def want(s, n):
        z, hi = s.zlo(n), n["bot"]-HH
        if z >= hi: return s.y < 0.5*(n["top"]+n["bot"])
        m = next((p for p in s.pipes if p["x"] > n["x"]+PIPE_W), None)
        if m:
            T   = (m["x"]-n["x"])/s.speed
            tT  = (n["x"]-(BIRD_X+HW))/s.speed
            if tT > T*0.55: z = min(z, s.zlo(m))
            if tT > T*0.30: z = max(z, s.zlo(m))
        if s.y+HH >= SKY-1.0: return True
        return s.y >= z
    def step(s, dt):
        s.clock += dt; s.wing = max(0.0, s.wing-dt*4)
        if s.dead:
            s.deadT += dt
            if s.deadT > 1.4: s.reset()
            return
        s.ramp()
        s.since += s.speed*dt
        if s.since >= s.space: s.since = 0.0; s.spawn()
        s.cool -= dt
        n = next((p for p in s.pipes if p["x"]+PIPE_W > BIRD_X-HW), None)
        if n and s.cool <= 0 and s.want(n):
            s.vy, s.cool, s.wing = -FLAP, COOLD, 1.0; s.flaps += 1
        s.vy = min(s.vy+GRAV*dt, MAXVY); s.y += s.vy*dt
        if s.y < HH: s.y, s.vy = HH, max(s.vy, 0.0)   # ceiling clamps: original
        for p in s.pipes:
            p["x"] -= s.speed*dt
            if not p["pass"] and p["x"]+PIPE_W < BIRD_X-HW:
                p["pass"] = True; s.score += 1
                if s.score > s.best: s.best = s.score
        s.pipes = [p for p in s.pipes if p["x"]+PIPE_W > -PIPE_W]
        if s.y+HH >= SKY: s.die(); return             # only the ground kills
        for p in s.pipes:
            if (BIRD_X+HW > p["x"] and BIRD_X-HW < p["x"]+PIPE_W and
                (s.y-HH < p["top"] or s.y+HH > p["bot"])): s.die(); return
    def die(s): s.dead, s.deadT = True, 0.0

# ---------- framebuffer + painter (sub-pixel, ink = darkness 0..1) ----------
BAYER8 = (
    ( 0,32, 8,40, 2,34,10,42),(48,16,56,24,50,18,58,26),
    (12,44, 4,36,14,46, 6,38),(60,28,52,20,62,30,54,22),
    ( 3,35,11,43, 1,33, 9,41),(51,19,59,27,49,17,57,25),
    (15,47, 7,39,13,45, 5,37),(63,31,55,23,61,29,53,21))
def th(y,x): return BAYER8[y&7][x&7]/64.0
class Scene:
    def __init__(s): s.L=[[0.0]*SW for _ in range(SH)]
    def put(s,y,x,v):
        if 0<=y<SH and 0<=x<SW: s.L[y][x]=v
    def rect(s,x,y,w,h,v):
        for yy in range(int(y),int(y+h)):
            for xx in range(int(x),int(x+w)): s.put(yy,xx,v)
    def clear(s):
        for r in s.L:
            for i in range(SW): r[i]=0.0

def cyl(c,w):
    t=c/float(w-1); return 0.06+0.82*t*t        # lit left, terminator right

def paint(sc, g, flash):
    sc.clear()
    for y in range(SH):                          # sky: mostly bare paper
        f=float(y)/SKY
        v=0.0 if f<0.42 else 0.020+0.115*((f-0.42)/0.58)
        for x in range(SW): sc.L[y][x]=v
    off=g.clock*g.speed*0.16                     # far hills: sparse -> recede
    for i in range(12):
        x=int(((i*34-off)%(SW+34))-17); sc.rect(x,SKY-13,30,13,0.16)
        sc.rect(x+5,SKY-15,20,2,0.14)
        sc.rect(x+11,SKY-17,9,2,0.13)
    off=g.clock*g.speed*0.34                     # near hills: denser, darker
    for i in range(9):
        x=int(((i*40-off)%(SW+40))-20); sc.rect(x,SKY-7,34,7,0.30)
        sc.rect(x+4,SKY-9,24,2,0.26)
        sc.rect(x+13,SKY-11,12,2,0.24)
    off=g.clock*g.speed*0.09                     # clouds: almost bare paper
    for i in range(4):
        x=int(((i*60-off)%(SW+60))-30); y=7+(i%3)*7
        # A cloud is lighter than the sky, so on paper it must be defined by
        # its EDGE: bare interior with a faint ink rim - the engraving idiom.
        for dx in range(26):
            sc.put(y-3,x+6+dx,0.11) if dx<13 else None
            sc.put(y+5,x+3+dx,0.10) if dx<19 else None
            sc.put(y-1,x+dx,0.09) if dx<26 else None
            sc.put(y+4,x+dx,0.09) if dx<26 else None
        for dy in range(0,4):
            sc.put(y+dy,x,0.09); sc.put(y+dy,x+25,0.09)
            for dx in range(1,25): sc.put(y+dy,x+dx,0.015)
    for p in g.pipes:                            # pipes: dense + hard outline
        x=int(round(p["x"]))
        for y0,y1,top in ((0,p["top"],True),(p["bot"],SKY,False)):
            for y in range(int(y0),int(y1)):
                for c in range(-1,PIPE_W+2): sc.put(y,x+c,0.92 if c<0 else cyl(c,PIPE_W))
                sc.put(y,x+PIPE_W+1,0.52)        # cast shadow, one column right
                if (int(y0)+ (9 if top else 0) + y) % 14 == 0:
                    sc.rect(x+8,y,PIPE_W-16,1,0.66)   # rivet band
            cap=int(round((y1-6) if top else y0))     # lip faces the gap
            for y in range(cap,cap+6):
                sc.put(y,x-3,0.94); sc.put(y,x+PIPE_W+3,0.48)
                for c in range(-2,PIPE_W+2): sc.put(y,x+c,cyl(c+2,PIPE_W+4))
            for c in range(-3,PIPE_W+4):
                sc.put(cap,x+c,0.97); sc.put(cap+5,x+c,0.80)
            sc.put(cap+3,x-3,0.94)               # lip shadow on the shaft
    sc.rect(0,SKY,SW,SH,0.40)                    # ground body
    for x in range(SW): sc.put(SKY,x,0.96); sc.put(SKY+1,x,0.66)
    off=int(g.clock*g.speed)%24
    for x in range(-24,SW+24,24):
        sc.rect(x-off,SKY+4,12,SH-SKY-4,0.58); sc.rect(x-off+13,SKY+3,3,2,0.70)
    sc.rect(0,SH-2,SW,2,0.78)
    cx,cy=int(BIRD_X),int(round(g.y))            # bird: 8x6, lit upper-left, outlined
    for dy in range(-3,4):
        for dx in range(-4,5):
            e=(dx/4.0)**2+(dy/3.0)**2
            if e<=1.0:
                sc.put(cy+dy,cx+dx,0.10+0.46*max(0.0,min(1.0,0.42+0.55*(dx/4.0+dy/3.0))))
            elif e<=1.75: sc.put(cy+dy,cx+dx,0.95)
    sc.put(cy-2,cx+2,0.02); sc.put(cy-1,cx+2,0.02); sc.put(cy-2,cx+3,0.98)
    for dy in (-1,0):
        for dx in (4,5,6): sc.put(cy+dy,cx+dx,0.30)
    wy=int(round(1.0-g.wing*2))                  # wing beats
    for dy in range(wy,wy+2):
        for dx in range(-3,1):
            if (dx/3.5)**2+((dy-wy-0.5)/1.4)**2<=1.0: sc.put(cy+dy,cx+dx,0.52)
    if flash>0:
        f=0.92*flash
        for y in range(SH):
            for x in range(SW): sc.L[y][x]=max(sc.L[y][x],f)

# ---------- glyph assembler: 2x2 sub-pixel pattern -> exact Unicode glyph ----------
UNI=[" ","\u2597","\u2596","\u2584","\u259D","\u2590","\u259A","\u259C",
     "\u2598","\u259E","\u258C","\u259F","\u2580","\u2599","\u259B","\u2588"]
DEC=(" ","~","`","a")            # VT100 has ONE shade (0x61 chequerboard); the
                                 # middot and diamond are the only other tones
def cell_glyph(sc,r,c):
    v=0
    for dy in (0,1):
        for dx in (0,1):
            y,x=r*2+dy,c*2+dx
            if sc.L[y][x] > th(y,x):
                v |= 8 if (dy==0 and dx==0) else 4 if dy==0 else 2 if dx==0 else 1
    return v

PAL=("far","near","cloud","pipe","ink","grnd","bird")
FG ={"far":34,"near":36,"cloud":37,"pipe":32,"ink":30,"grnd":33,"bird":93}

class TTY:
    def __init__(s, vt100, stats):
        s.vt100, s.stats, s.prev, s.gmode, s.n = vt100, stats, [""]*FH, None, 0
    def s(s,t):
        s.n+=len(t.encode("latin-1","replace")); sys.stdout.write(t)
    def boot(s):
        if not s.vt100: s.s("\x1b[?1049h\x1b[?25l")   # VT220/xterm: not VT100
        s.s("\x1b[2J")
    def draw(s, sc, hud):
        s.n=0
        b=["\x1b[1H"]
        if s.gmode: b.append("\x1b(B"); s.gmode=None
        b.append(hud[:COLS].ljust(COLS))
        for r in range(FH):
            gl=[cell_glyph(sc,r,c) for c in range(COLS)]
            if s.vt100: line="".join(DEC[0 if v==0 else 1 if v<6 else 2 if v<11 else 3] for v in gl)
            else:       line="".join(UNI[v] for v in gl)
            if line==s.prev[r]: continue
            end=max((i for i,ch in enumerate(line) if ch!=" "), default=-1)
            line=line[:end+1]
            b.append("\x1b[%dH" % (r+1+HUD))
            if s.vt100:
                want = bool(line.strip())
                if want and s.gmode is None: b.append("\x1b(0"); s.gmode=True
                elif not want and s.gmode:   b.append("\x1b(B"); s.gmode=None
            if not s.vt100:
                band=4 if r>=FH-5 else 3 if any((sc.L[x2][c]>0.45) for x2 in (r*2,r*2+1) for c in range(0,SW,4)) else 1
                b.append("\x1b[%dm" % FG["grnd" if band==4 else "pipe" if band==3 else "cloud"])
            b.append(line); b.append("\x1b[K")
            if not s.vt100: b.append("\x1b[0m")
            s.prev[r]=line
        if s.gmode: b.append("\x1b(B"); s.gmode=None
        b.append("\x1b[%dH" % ROWS)
        s.s("".join(b)); sys.stdout.flush()
        if s.stats: sys.stderr.write("frame %dB = %.2fs at 9600 baud\n"%(s.n,s.n/960.0))
    def bye(s):
        s.s("\x1b(B\x1b[0m")
        if not s.vt100: s.s("\x1b[?25h\x1b[?1049l")

def hud(g):
    k=1.0-math.exp(-g.score/TAU)
    return (" FLAPPY-VT100 %3d BEST %3d  GAP %4.1f ZONE %3.1f  %s%s "
            % (g.score,g.best,g.gap,(g.gap-2*HH)-APEX,"#"*int(18*k),"."*(18-int(18*k))))

def selftest(n, seed):
    print("selftest %d games, step %.4fs" % (n,FIXED))
    out=[]
    for i in range(n):
        g=Game(seed+i*7919)
        for _ in range(int(60*400)):
            g.step(FIXED)
            if g.dead: out.append(g.score); break
        else: out.append(None)
    d=sorted(x for x in out if x is not None)
    if not d: print("  nobody ever crashed -> pilot too strong / asymptote too soft"); return
    q=lambda p: d[max(0,min(len(d)-1,int(p*(len(d)-1))))]
    print("  died %d/%d  crash score p10 %d p50 %d p90 %d  range %d..%d"
          % (len(d),n,q(.1),q(.5),q(.9),d[0],d[-1]))
    print("  distinct crash scores %d of %d  |  deaths before pipe 40: %d"
          % (len(set(d)),len(d),sum(1 for x in d if x<40)))
    print("  safe-flap zone at asymptote: %.1f sub-rows (0 = forced death)" % SAFE)

def main():
    a=sys.argv[1:]; vt100="--vt100" in a; stats="--stats" in a
    if "--selftest" in a:
        n=next((int(a[i+1]) for i,x in enumerate(a) if x=="--n"), 20)
        sd=next((int(a[i+1]) for i,x in enumerate(a) if x=="--seed"), 1)
        selftest(n,sd); return
    g,sc=Game(next((int(a[i+1]) for i,x in enumerate(a) if x=="--seed"),None)),Scene()
    nf=next((int(a[i+1]) for i,x in enumerate(a) if x=="--frames"), 0)
    if nf:
        for f in range(nf):
            for _ in range(60): g.step(FIXED)
            paint(sc,g,0.9*max(0.0,1.0-g.deadT/0.4) if g.dead else 0.0)
            t=TTY(vt100,False); rows=[]
            for r in range(FH):
                gl=[cell_glyph(sc,r,c) for c in range(COLS)]
                rows.append("".join(DEC[0 if v==0 else 1 if v<6 else 2 if v<11 else 3]
                                    if vt100 else UNI[v] for v in gl))
            print(hud(g)); print("\n".join(rows)); print()
        return
    t=TTY(vt100,stats); t.boot(); acc,last=0.0,time.time()
    try:
        while True:
            now=time.time(); acc=min(0.25,acc+now-last); last=now
            while acc>=FIXED: g.step(FIXED); acc-=FIXED
            paint(sc,g,0.9*max(0.0,1.0-g.deadT/0.4) if g.dead else 0.0)
            t.draw(sc,hud(g)); time.sleep(0.006)
    except KeyboardInterrupt: pass
    finally: t.bye()

if __name__=="__main__": main()
