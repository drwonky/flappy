#!/usr/bin/env python3
"""flappy-linux-poof - self-playing Flappy Bird for an 80x25 terminal,
whose bird explodes into tumbling pieces inside a puff of smoke on a crash.

  python3 flappy-linux-poof.py             Linux console: 16 colours, CP437 blocks
  python3 flappy-linux-poof.py --vt100     strict DEC Special Graphics, mono
  python3 flappy-linux-poof.py --frames 5  print 5 frames (ANSI), no tty
  python3 flappy-linux-poof.py --selftest  headless games -> crash statistics
  --seed N   --stats (bytes/frame, for 9600-baud curiosity)

RENDERING: the scene is painted on a 160x48 SUB-PIXEL grid (2x2 per
character cell). Every material is AUTHORED as a console tone - one
(glyph, fg, bg) the Linux console can show: 16 foregrounds (bold = bright),
8 backgrounds, and only glyphs in its CP437 font -
   ' ' / '█'          solid bg / solid fg
   '░' '▒' '▓'        fg over bg at 1/4, 1/2, 3/4, related hues only
   '▀' '▄' '▌' '▐'    two solid tones split in one cell (pipe edges land on
                      half-columns)
A cell is resolved from the tones of its four sub-pixels, never from their
averaged colour: one tone -> that tone, two solid tones split in halves ->
a half block, otherwise the majority (ties to the darker). Scenery is placed
on the cell grid and pipe gate edges on even sub-rows, so shapes are stable
as they scroll. The bird is in exact VGA colours on cell-aligned square
pixels, so every one of its cells is an exact '▀' pair.
--vt100 has no colour and no blocks: sky is blank paper and everything else
is inked by darkness using space, '·', the chequerboard and reverse video.
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
# COLLISION IS PIXEL PERFECT: the bird dies exactly when a pixel it DRAWS
# touches a pixel a pipe DRAWS (lips included) or the ground line. The old
# 7.8x6 hitbox was sized for an 8x6 sprite; the sprite became 22x7 (square
# pixels) and the hitbox never followed, so the beak and tail sailed through
# pipe lips. Both sides now come from the same geometry as the renderer.
BIRD_COL0 = 2*(int(BIRD_X/2)-4)  # sprite's left sub-column: cell aligned
BT, BB  = 3, 3                   # sprite rows above / below round(y)
PIPE_W  = 29                     # 29/160 = 0.181 = original 52/288 screens
LIPL, LIPR, LIP_H = 3, 4, 4      # lip overhang left / right, lip height
SPD0, SPD1 = 0.4167*SW, 0.5600*SW   # original 120px/s on 288 wide
SPC0, SPC1 = 0.625*SW, 0.500*SW     # original 169px on 288 -> 1.7 pipes visible
GAP0, GAP1 = 21.0, 17.0        # +1: the true (drawn) bird is 7 rows, not 6
TAU     = 85.0
APEX    = FLAP*FLAP/(2*GRAV)
BH      = BT+BB+1                # drawn bird height
SAFE    = (GAP1-BH)-APEX         # width of the safe-flap band at the asymptote

assert SAFE > 0, "asymptote is geometrically impossible"
assert COOLD < HOVER and COOLD > 0.30

class Game:
    def __init__(s, seed=None):
        s.rng = random.Random(seed); s.best = 0; s.dist = 0.0
        # the explosion has its OWN generator: drawing debris must never shift
        # the pipe sequence, so --selftest stays identical to flappy-linux.py
        s.fx = random.Random(None if seed is None else seed ^ 0x5EED)
        s.reset()
    def reset(s):
        s.y, s.vy, s.pipes = SKY*0.42, 0.0, []
        s.score, s.cool, s.since, s.aim = 0, 0.0, 1e9, 0.0
        s.dead, s.deadT, s.clock, s.wing = False, 0.0, 0.0, 0.0
        s.parts, s.boom = [], (0.0, 0.0)
        s.speed, s.gap, s.space, s.flaps = SPD0, GAP0, SPC0, 0
    def ramp(s):
        k = 1.0 - math.exp(-s.score/TAU)
        s.speed = SPD0+(SPD1-SPD0)*k
        s.gap   = GAP0+(GAP1-GAP0)*k
        s.space = SPC0+(SPC1-SPC0)*k
    def spawn(s):
        top = 4 + s.rng.random()*(SKY-8-s.gap)
        s.pipes.append({"x": float(SW), "top": top, "bot": top+s.gap, "pass": False})
        s.aim = (s.rng.random()*2-1)*(s.gap-BH)*0.12
    # Thrust is one-sided: flapping at y puts your apex at y-APEX, so to cross
    # a gate you must enter no higher than top+BT+APEX (else you clip the upper
    # pipe) and no lower than bot-BB. Gates are judged as DRAWN (gate()). Riding the TOP of that window is a limit
    # cycle whose parabola spans exactly APEX. Aim blends to the next gate early
    # enough to sink/climb to it, since descending costs only an abstained flap.
    def zlo(s, n): return gate(n)[0]+BT+0.5+APEX
    def want(s, n):
        t, b = gate(n)
        z, hi = s.zlo(n), b-BB-1.0
        if z >= hi: return s.y < 0.5*(t+b)
        m = next((p for p in s.pipes if p["x"] > n["x"]+PIPE_W), None)
        if m:
            T   = (m["x"]-n["x"])/s.speed
            tT  = (pipe_x(n)-LIPL-(BIRD_COL0+BIRD_WS))/s.speed
            if tT > T*0.55: z = min(z, s.zlo(m))
            if tT > T*0.30: z = max(z, s.zlo(m))
            # committed to this gate: if the next one is LOWER, ride as low as
            # this gate allows. The real bird plus the lip span most of the
            # pipe spacing, so waiting until this gate is cleared leaves too
            # little room to sink to the next one.
            elif s.zlo(m) > z: z = min(s.zlo(m), hi-1.5)
        if s.y+BB+1 >= SKY-1.0: return True
        return s.y >= z
    def step(s, dt):
        s.clock += dt; s.wing = max(0.0, s.wing-dt*4)
        if s.dead:
            s.deadT += dt
            s.debris(dt)
            if s.deadT > DEAD_T: s.reset()
            return
        s.ramp()
        s.since += s.speed*dt
        s.dist  += s.speed*dt        # scroll distance: drawing only, never reset
        if s.since >= s.space: s.since = 0.0; s.spawn()
        s.cool -= dt
        n = next((p for p in s.pipes if pipe_x(p)+PIPE_W+LIPR > BIRD_COL0), None)
        if n and s.cool <= 0 and s.want(n):
            s.vy, s.cool, s.wing = -FLAP, COOLD, 1.0; s.flaps += 1
        s.vy = min(s.vy+GRAV*dt, MAXVY); s.y += s.vy*dt
        if s.y < BT: s.y, s.vy = BT, max(s.vy, 0.0)   # ceiling clamps: original
        for p in s.pipes:
            p["x"] -= s.speed*dt
            if not p["pass"] and pipe_x(p)+PIPE_W+LIPR <= BIRD_COL0:
                p["pass"] = True; s.score += 1
                if s.score > s.best: s.best = s.score
        s.pipes = [p for p in s.pipes if p["x"]+PIPE_W > -PIPE_W]
        if s.hits(): s.die(); return
    def hits(s):
        """True iff a drawn bird pixel touches a drawn pipe pixel or the ground."""
        r0 = int(round(s.y))-BT                    # exactly as draw_bird places it
        if r0+BH > SKY: return True                # bottom row on the ground line
        for p in s.pipes:
            x = pipe_x(p)
            if x-LIPL >= BIRD_COL0+BIRD_WS or x+PIPE_W+LIPR <= BIRD_COL0: continue
            for x0,x1,y0,y1 in pipe_rects(p):
                for dy,(a,b) in enumerate(BIRD_SPANS):
                    if y0 <= r0+dy < y1 and BIRD_COL0+a < x1 and BIRD_COL0+b > x0:
                        return True
        return False
    def die(s):
        s.dead, s.deadT = True, 0.0
        s.explode()
    # ---- the explosion: the bird's own cells become the debris ----
    def explode(s):
        col0,row0,rows=bird_rows(s)
        cx,cy=col0+11.0,row0+3.5                   # sprite centre, sub-pixels
        s.boom=(cx,cy); s.parts=[]
        for x in range(max(len(r) for r in rows)):
            for y in range(0,len(rows),2):         # two sprite rows = one cell
                top=rows[y][x]   if x<len(rows[y]) else "."
                bot=rows[y+1][x] if y+1<len(rows) and x<len(rows[y+1]) else "."
                if top=="." and bot==".": continue
                px,py=col0+2*x,row0+y
                dx,dy=(px+1-cx)*0.5,(py+1-cy)  # square units: a sub-col is half
                d=math.hypot(dx,dy) or 1.0
                a=math.atan2(dy,dx)+s.fx.uniform(-0.5,0.5)
                v=s.fx.uniform(22,58)*(0.6+0.4*min(1.0,d/4.0))
                s.parts.append({"x":float(px),"y":float(py),
                    "vx":2.0*v*math.cos(a), "vy":v*math.sin(a)-s.fx.uniform(25,50),
                    "ch":max((top,bot),key=lambda c: -1 if c=="." else BCOL[c]),
                    "life":s.fx.uniform(0.9,DEAD_T-0.15)})
    def debris(s, dt):
        for p in s.parts:
            p["vy"]=min(p["vy"]+GRAV*0.8*dt, MAXVY)
            p["x"]+=p["vx"]*dt; p["y"]+=p["vy"]*dt
            if p["y"]+2>=SKY:                      # land on the grass and bounce
                p["y"]=SKY-2.0
                p["vy"]*=-0.35; p["vx"]*=0.55
                if abs(p["vy"])<6: p["vy"]=0.0
        s.parts=[p for p in s.parts if s.deadT<p["life"] and -4<p["x"]<SW+4]

# ---------- pipe geometry: ONE definition, used by the painter and collision ----------
# x snaps to an even sub-column and the gate's top edge to an even sub-row; the
# bottom edge is top + the gap rounded to even, so snapping can never narrow a
# gate below its design width.
def pipe_x(p): return 2*int(round(p["x"]/2))
def gate(p):
    t = 2*int(round(p["top"]/2))
    return t, t+2*int(math.floor((p["bot"]-p["top"])/2+0.5))
def pipe_rects(p):
    """(x0, x1, y0, y1), half-open, of everything a pipe paints."""
    x=pipe_x(p); t,b=gate(p)
    return ((x,x+PIPE_W,0,t), (x-LIPL,x+PIPE_W+LIPR,t-LIP_H,t),
            (x,x+PIPE_W,b,SKY), (x-LIPL,x+PIPE_W+LIPR,b,b+LIP_H))

# ---------- console palette: what the Linux console can actually show ----------
# 16 foreground colours (8 + bold) and 8 backgrounds. Only glyphs present in the
# console's CP437 font are used: blank, full/half blocks and the three shade
# characters, which blend fg over bg at 1/4, 1/2, 3/4.
VGA=[(0,0,0),(170,0,0),(0,170,0),(170,85,0),(0,0,170),(170,0,170),(0,170,170),(170,170,170),
     (85,85,85),(255,85,85),(85,255,85),(255,255,85),(85,85,255),(255,85,255),(85,255,255),(255,255,255)]
def _lin(c): return tuple((v/255.0)**2.2 for v in c)
def _srgb(l): return tuple(255.0*(v**(1/2.2)) for v in l)
VLIN=[_lin(c) for c in VGA]
def mix(a, b, t):
    return (a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t, a[2]+(b[2]-a[2])*t)
def err(a,b):
    dr,dg,db=a[0]-b[0],a[1]-b[1],a[2]-b[2]
    rm=(a[0]+b[0])*0.5                            # "redmean" perceptual distance
    return (2+rm/256)*dr*dr+4*dg*dg+(2+(255-rm)/256)*db*db
SHADES={"░":0.25,"▒":0.5,"▓":0.75}

# A TONE is one (glyph, fg, bg) cell appearance. Every material in the scene is
# AUTHORED as a tone and painted with that tone's displayed RGB, so each
# sub-pixel maps back to its tone exactly. Cells are never averaged: averaging
# is what turned boundaries and gradients into arbitrary fg/bg combinations
# (grey over green, cyan over black) that changed from cell to cell - speckle.
TONE={}
def T(gl, f=None, b=None):
    """displayed rgb of a tone, registered so the quantiser can recover it."""
    if gl=="█" and f<8: gl,f,b=" ",None,f      # dark solids are a plain bg
    if gl==" ":   rgb=VGA[b]
    elif gl=="█": rgb=VGA[f]
    else:
        t=SHADES[gl]
        rgb=_srgb(tuple(VLIN[f][k]*t+VLIN[b][k]*(1-t) for k in range(3)))
    TONE.setdefault(rgb,(gl,f,b))
    return tuple(rgb)              # a fresh object: --vt100 tells scenery by identity

# Fallback for colours that are not authored tones (the death flash): the best
# single tone, with shade pairs limited to fg/bg that belong together.
FLAT=[]                                           # (rgb, glyph, fg, bg, texture penalty)
for b in range(8): FLAT.append((VGA[b]," ",None,b,0))
for f in range(8,16): FLAT.append((VGA[f],"█",f,None,0))
NEIGH={(2,6),(6,2),(4,6),(6,4),(2,3),(3,2),(1,3),(3,1),(1,5),(5,1),(4,5),(5,4)}
def harmonious(f,b):
    h=f&7
    return b==0 or b==7 or h==b or f in (7,8,15) or (h,b) in NEIGH
for f in range(16):
    for b in range(8):
        if f==b or (f==8 and b==0) or not harmonious(f,b): continue
        for gch,t,pen in (("░",0.25,1.0),("▒",0.5,1.6),("▓",0.75,1.0)):
            l=tuple(VLIN[f][k]*t+VLIN[b][k]*(1-t) for k in range(3))
            FLAT.append((_srgb(l),gch,f,b,pen*err(VGA[f],VGA[b])*0.002))
_flat={}
def best_flat(c):
    c=(int(c[0])&~3,int(c[1])&~3,int(c[2])&~3)
    r=_flat.get(c)
    if r is None:
        r=min(FLAT,key=lambda e: err(e[0],c)+e[4]); _flat[c]=r
    return r
def tone(c):
    t=TONE.get(c)
    if t is None: t=TONE[c]=best_flat(c)[1:4]
    return t

# ---------- materials, authored as console tones ----------
# Shade pairs are same-hue or neighbouring-hue so blends read as tone, not noise.
SKY_TOP  = T("░",14,6)                           # sky gradient, top to horizon:
SKY_HI   = T("▒",14,6)                           # lightening toward the ground
SKY_MID  = T("█",14)                             # bright cyan, SOLID: the bird is
SKY_LO   = T("▓",14,7)                           # black-outlined, so it splits
                                                 # cleanly against it
CLOUD, CLOUD_SH = T("█",15), T("▓",15,7)
FAR, FAR_HI     = T("▒",10,6), T("▓",10,6)       # far ridge: hazy blue-green
BUSH, BUSH_HI, BUSH_LO = T("░",10,2), T("▒",10,2), T(" ",None,2)
P_OUT, P_LT, P_HI = T(" ",None,0), T("▓",10,7), T("█",10)
P_MID, P_LO, P_DK = T("▓",10,2), T(" ",None,2), T("▓",2,0)
G_LINE, GRASS1, GRASS2, GRASS_LO = T(" ",None,0), T("█",10), T("▓",10,2), T("▓",2,0)
DIRT, DIRT_LO  = T("▒",11,7), T("▒",11,3)

def skyrow(y):
    f=y/float(SKY)
    if f<0.10: return SKY_TOP
    if f<0.22: return SKY_HI
    if f<0.84: return SKY_MID
    return SKY_LO
SKYROW = [skyrow(y) for y in range(SH)]

# ---------- framebuffer + painter (sub-pixel RGB) ----------
# A sub-pixel is half a column by half a row. Character cells are 1:2, so a
# sub-pixel is itself 1:2 (tall): two sub-columns side by side make a square.
class Scene:
    def __init__(s): s.L=[[SKY_HI]*SW for _ in range(SH)]
    def put(s,y,x,c):
        if 0<=y<SH and 0<=x<SW: s.L[y][x]=c
    def rect(s,x,y,w,h,c):
        x0,x1=max(0,int(x)),min(SW,int(x+w))
        if x1<=x0: return
        for yy in range(max(0,int(y)),min(SH,int(y+h))):
            r=s.L[yy]
            for xx in range(x0,x1): r[xx]=c
    def blob(s,cx,cy,rx,ry,c,shade=None,hi=None):
        # ellipse in SQUARE units: rx in sub-cols (x2 for aspect), ry in sub-rows
        for yy in range(int(cy-ry)-1,int(cy+ry)+2):
            for xx in range(int(cx-rx)-1,int(cx+rx)+2):
                dx,dy=(xx+0.5-cx)/rx,(yy+0.5-cy)/ry
                e=dx*dx+dy*dy
                if e<=1.0:
                    col=c
                    if shade and dy>0.45: col=shade
                    elif hi and dy<-0.55 and dx<0.2: col=hi
                    s.put(yy,xx,col)
    def clear(s):
        for y in range(SH): s.L[y]=[SKYROW[y]]*SW

def layer(dist, k, n, gap):
    """Positions of n repeating scenery items. The wrap period is exactly n*gap,
    so spacing stays even across the wrap, and every x is snapped to an EVEN
    sub-column: each item then lands on the cell grid identically every frame
    and only moves in whole cells. Fractional placement re-sampled each shape
    every frame, so one-sub-pixel details blinked in and out as it scrolled."""
    per=n*gap; off=dist*k
    return [2*int(math.floor((((i*gap-off)%per)-gap)/2.0)) for i in range(n)]

def paint(sc, g, flash):
    sc.clear()
    for i,x in enumerate(layer(g.dist,0.07,5,44)):         # clouds: furthest, slowest
        y=6+(i*5)%13
        for (dx,dy,rx,ry) in ((0,1,9,3),(8,-1,9,4),(17,1,8,3),(5,2,14,2.5)):
            sc.blob(x+12+dx,y+dy,rx,ry,CLOUD,shade=CLOUD_SH)
    for i,x in enumerate(layer(g.dist,0.16,8,26)):         # far ridge: hazy
        sc.blob(x+12,SKY,16,7+(i*5)%6,FAR,hi=FAR_HI)
    for i,x in enumerate(layer(g.dist,0.34,10,19)):        # near bushes: saturated
        sc.blob(x+10,SKY+1,12,4+(i*3)%3,BUSH,shade=BUSH_LO,hi=BUSH_HI)
    for p in g.pipes:                            # pipes: lit cylinder, dark outline
        # ONE integer edge per gate, used by shaft and lip alike (the shaft used
        # to stop at int(top) while the lip sat at round(top-5), leaving a stub
        # of shaft past the lip). Edges snap to EVEN sub-rows, so the lip is
        # exactly two cell rows and each thin rule shares its cell with lip body
        # only. The lip body is SOLID colours, so rule + body is an exact half
        # block; a shaded body cannot split and would swallow the rule's cell.
        # x snaps to an EVEN sub-column too. Wherever a lip's side edge meets
        # its rule, one cell holds 3 rule + 1 body sub-pixels, which no glyph
        # can show; at half-column positions that corner flipped between a
        # black cell and a half bar every step. Cell-aligned, with the lip
        # spanning odd..even sub-columns (overhang 3 left, 4 right), every
        # pipe cell is an exact split at every position.
        x=pipe_x(p); t,b=gate(p)
        shaft=[P_OUT]+[pipe_shade(c,PIPE_W-2) for c in range(PIPE_W-2)]+[P_OUT]
        lip=[P_OUT]+[lip_shade(c,PIPE_W+LIPL+LIPR-2) for c in range(PIPE_W+LIPL+LIPR-2)]+[P_OUT]
        for y0,y1,cap in ((0,t,t-LIP_H),(b,SKY,b)):
            for y in range(max(0,y0),min(SH,y1)):
                r=sc.L[y]
                for c,col in enumerate(shaft):
                    if 0<=x+c<SW: r[x+c]=col
            for y in range(cap,cap+LIP_H):
                if not 0<=y<SKY: continue
                r=sc.L[y]
                rule=y==cap or y==cap+LIP_H-1
                for c,col in enumerate(lip):
                    xx=x-LIPL+c
                    if 0<=xx<SW: r[xx]=P_OUT if rule else col
    sc.rect(0,SKY,SW,1,G_LINE)                   # ground: grass band + dirt
    off=int(g.dist)
    sc.rect(0,SKY+1,SW,1,GRASS1)                 # solid, so the dark line above
    for y in range(SKY+2,SKY+4):                 # always splits cleanly off it
        r=sc.L[y]
        for x in range(SW):
            r[x]=GRASS1 if ((x+off)%12)<6 else GRASS2
    sc.rect(0,SKY+4,SW,1,GRASS_LO)
    sc.rect(0,SKY+5,SW,SH-SKY-5,DIRT)
    offc=off//2                                  # dirt specks: whole cells, so
    for cy in range((SKY+6)//2,FH):              # none can fall between them
        for cx in range(-1,COLS+1):
            if ((cx+offc)*7+cy*13)%23==0:
                sc.rect(2*cx-(off&1),2*cy,2,2,DIRT_LO)
    if not g.dead: draw_bird(sc,g)
    if flash>0:
        f=min(1.0,flash)
        for y in range(SH):
            sc.L[y]=[mix(c,(255,255,255),f) for c in sc.L[y]]
    if g.dead: draw_poof(sc,g)

DEAD_T=1.9                       # seconds the explosion plays before restart
def lip_shade(c,w):
    return P_HI if c/float(w-1)<0.66 else P_LO     # solid only: see paint()
def pipe_shade(c,w):
    t=c/float(w-1)
    if t<0.08: return P_MID
    if t<0.16: return P_LT
    if t<0.36: return P_HI
    if t<0.62: return P_MID
    if t<0.84: return P_LO
    return P_DK

# Bird sprite in SQUARE pixels: one column wide, half a row tall, so each
# character cell holds exactly two of them stacked -> one "▀" with fg/bg.
# Colours are VGA indices, so the quantiser reproduces them exactly. Only the
# dark ones (<8) can sit in the background half of a cell, which is why the
# outline, pupil and belly are 0/3/1 and the bright yellow/white are fg-only.
BIRD = ("..KKKKK...",
        ".KYYYYKWK.",
        "KYYYYKWWBK",
        "KYYYYYKKKKK",
        "KYYYYOKRRRK",
        ".KOOOOOKRK.",
        "..KKKKKKK..")
WING = {0: ((1,2),(1,3),(2,1),(2,2),(2,3)),          # raised: the downstroke
        1: ((3,1),(3,2),(3,3),(4,1),(4,2)),          # level
        2: ((4,1),(4,2),(4,3),(5,2),(5,3))}          # lowered: gliding
# per sprite row: the [first, last+1) SUB-columns it inks. Wing poses only
# recolour pixels inside the outline, so this is the same for every frame.
BIRD_SPANS = [(2*min(i for i,c in enumerate(r) if c!="."),
               2*(max(i for i,c in enumerate(r) if c!=".")+1)) for r in BIRD]
BIRD_WS = max(b for a,b in BIRD_SPANS)
assert len(BIRD)==BH and all(c!="." for r in BIRD for c in r[r.index(r.strip(".")[0]):len(r.rstrip("."))]), \
       "sprite rows must be solid between their ends, or BIRD_SPANS over-claims"
assert all(BIRD[y][x]!="." for w in WING.values() for y,x in w), "wing outside the body"
BCOL = {"K":0, "Y":11, "O":3, "W":15, "B":0, "R":9, "w":7}
def bird_rows(g):
    col0 = BIRD_COL0
    row0 = int(round(g.y))-BT
    ph = g.wing
    wf = 0 if ph>0.55 else 1 if ph>0.15 else 2
    if g.vy < -0.2*FLAP: wf = 0 if ph>0.55 else 1
    rows=[list(r) for r in BIRD]
    for (y,x) in WING[wf]: rows[y][x]="w"
    if wf!=0: rows[2][1]=rows[2][2]="Y"
    return col0,row0,rows
def draw_bird(sc,g):
    col0,row0,rows=bird_rows(g)
    for y,r in enumerate(rows):
        for x,ch in enumerate(r):
            if ch==".": continue
            c=VGA[BCOL[ch]]
            sc.put(row0+y,col0+2*x,c); sc.put(row0+y,col0+2*x+1,c)

# The poof: a cartoon cluster of smoke balls that bursts outward from the
# bird, then shrinks and thins away. Smoke is filled in whole cells in
# authored tones (white, shaded underneath, then lighter shades as it fades),
# so it renders exactly. It is also the crash's flash: the old whole-screen
# wash to white muddied every pipe for its first frames. Each piece
# of debris is one cell of the bird, drawn whole in that cell's brightest
# colour (pure outline cells are black: charred bits). A half-coloured piece
# would put two bright colours in one cell against the bright sky, which no
# glyph can show, so whole cells snapped to the grid are what stay exact.
SMOKE=(T("█",15), T("▓",15,7), T("▒",15,7), T("░",15,7))
PUFFS=7; POOF_T=0.62
def draw_poof(sc,g):
    t=g.deadT; cx,cy=g.boom
    if t<POOF_T:
        k=t/POOF_T
        out=2.0+16.0*(1.0-math.exp(-t*9.0))        # how far the balls have flown
        fade=0 if k<0.45 else 1 if k<0.65 else 2 if k<0.82 else 3
        balls=[(cx,cy,(5.0+2.5*k)*(1.0-k*k))]       # central ball
        for i in range(PUFFS):
            a=i*2*math.pi/PUFFS+0.4
            rr=(3.6+1.3*math.sin(i*2.3))*(1.0-k)**0.7*(1.0 if t>0.03 else t/0.03)
            balls.append((cx+2.0*out*math.cos(a), cy+out*0.8*math.sin(a), rr))
        for bx,by,br in balls:
            if br<=0.3: continue
            for ccy in range(max(0,int((by-br)/2)-1),min(FH,int((by+br)/2)+2)):
                if 2*ccy>=SKY: continue
                for ccx in range(max(0,int((bx-2*br)/2)-1),min(COLS,int((bx+2*br)/2)+2)):
                    dx,dy=(2*ccx+1-bx)*0.5,(2*ccy+1-by)
                    if dx*dx+dy*dy<=br*br:
                        f=fade if dy<br*0.4 else min(3,fade+1)   # shaded underside
                        sc.rect(2*ccx,2*ccy,2,2,SMOKE[f])
    for p in g.parts:
        x=2*int(math.floor(p["x"]/2)); y=2*int(math.floor(p["y"]/2))
        sc.rect(x,y,2,2,VGA[BCOL[p["ch"]]])

# ---------- cell quantiser: 2x2 sub-pixels -> (glyph, fg, bg) ----------
# Each sub-pixel is first mapped to its tone; the cell is then resolved WITHOUT
# inventing colours that are in neither of them:
#   one tone            -> that tone
#   two SOLID tones split top/bottom or left/right -> exact half block
#   a solid half over two solid bands -> half block over the darker band
#   anything else       -> the majority tone, ties to the darker one (so
#                          outlines win over what they outline)
# Deterministic per tone pattern, so the same picture always gives the same
# cells, and a shaded region can never break up into speckle.
UP,DN,LF,RT="▀","▄","▌","▐"
def solid(t):
    return t[1] if t[0]=="█" else t[2] if t[0]==" " else None
def _lum(t):
    c=next(k for k,v in TONE.items() if v==t)
    return 0.299*c[0]+0.587*c[1]+0.114*c[2]
_tlum={}
def tlum(t):
    v=_tlum.get(t)
    if v is None: v=_tlum[t]=_lum(t)
    return v
def shade_main(t):
    return t[2] if t[0]=="░" else t[1]           # the colour the shade mostly shows
def split(g1,g2,t1,t2):
    """t1 fills the g1 half, t2 the other. Both solid, or one a DARK solid
    (an outline) beside a shade: the shade then stands in for its main colour.
    Without that, an outline over shaded scenery could not split and showed as
    a whole black cell or nothing, depending on what scrolled past behind it."""
    s1,s2=solid(t1),solid(t2)
    if s1 is None and s2 is not None and s2<8: s1=shade_main(t1)
    if s2 is None and s1 is not None and s1<8: s2=shade_main(t2)
    if s1 is None or s2 is None: return None
    if s2<8: return (g1,s1,s2)
    if s1<8: return (g2,s2,s1)
    return None        # both bright: dimming one drew a dark rim round clouds
def rule_split(ta,tb,tc,td):
    """One half is a single solid tone (a pipe rule or edge) and the other half
    holds two tones (lip bands meeting, or scenery boundaries passing behind).
    Keep the solid half exact and fill the other with the darker of its tones
    that can split against it; otherwise the majority would turn the whole
    cell into rule, and the edge would flick between half and whole cells."""
    for u1,u2,m1,m2,g1,g2 in ((ta,tb,tc,td,UP,DN),(tc,td,ta,tb,DN,UP),
                              (ta,tc,tb,td,LF,RT),(tb,td,ta,tc,RT,LF)):
        if u1!=u2 or solid(u1) is None or m1==m2: continue
        for t in sorted({m1,m2}-{u1},key=tlum):
            r=split(g1,g2,u1,t)
            if r is not None: return r
    return None
_cell={}
def quantise(a,b,c,d):
    ta,tb,tc,td=tone(a),tone(b),tone(c),tone(d)
    key=(ta,tb,tc,td); r=_cell.get(key)
    if r is not None: return r
    if ta==tb==tc==td: r=ta
    else:
        r=None
        if ta==tb and tc==td: r=split(UP,DN,ta,tc)
        elif ta==tc and tb==td: r=split(LF,RT,ta,tb)
        if r is None: r=rule_split(ta,tb,tc,td)
        if r is None:
            n={}
            for t in key: n[t]=n.get(t,0)+1
            r=max(n,key=lambda t:(n[t],-tlum(t)))
    _cell[key]=r
    return r

def cell_rows(sc):
    L=sc.L; out=[]
    for r in range(FH):
        t,u=L[2*r],L[2*r+1]
        out.append([quantise(t[2*c],t[2*c+1],u[2*c],u[2*c+1]) for c in range(COLS)])
    return out

# strict VT100: no colour, no block glyphs. DEC Special Graphics gives the
# 0x61 chequerboard and the centred dot; reverse video (SGR 7) turns a blank
# into a solid cell and a dot into a "nearly solid" one -> 5 tones, ordered-
# dithered between neighbours on the cell grid.
BAYER4=((0,8,2,10),(12,4,14,6),(3,11,1,9),(15,7,13,5))
VT_TONES=((0.0," ",False),(0.12,"~",False),(0.5,"a",False),(0.88,"~",True),(1.0," ",True))
def lum(c): return (0.299*c[0]+0.587*c[1]+0.114*c[2])/255.0
def ink(c,y):
    # Luminance alone can't tell green pipe from cyan sky. In mono the sky is
    # paper (blank) and everything in front of it is inked by its darkness.
    if c is SKYROW[y]: return 0.0
    k=0.12+0.88*(1.0-lum(c))
    return k*0.45 if id(c) in SCENERY else k
# by identity, not value: pipe and ground tones may share a colour with bushes
SCENERY={id(c) for c in (CLOUD,CLOUD_SH,FAR,FAR_HI,BUSH,BUSH_HI,BUSH_LO)}
def vt_rows(sc):
    L=sc.L; out=[]
    for r in range(FH):
        t,u=L[2*r],L[2*r+1]; row=[]
        for c in range(COLS):
            k=(ink(t[2*c],2*r)+ink(t[2*c+1],2*r)+ink(u[2*c],2*r+1)+ink(u[2*c+1],2*r+1))*0.25
            k=max(0.0,min(1.0,k))
            i=0
            while i<len(VT_TONES)-2 and k>VT_TONES[i+1][0]: i+=1
            lo,hi=VT_TONES[i],VT_TONES[i+1]
            f=(k-lo[0])/(hi[0]-lo[0])
            row.append(hi if f>(BAYER4[r&3][c&3]+0.5)/16 else lo)
        out.append(row)
    return out

def sgr(f,b):
    p=["0"]
    if f is not None:
        if f>=8: p.append("1")
        p.append("3%d"%(f&7))
    if b is not None: p.append("4%d"%b)
    return "\x1b[%sm"%";".join(p)

def ansi_line(cells):
    """Emit a row, changing attributes only when the cell actually needs it."""
    o=[]; cf=cb=-1
    for gl,f,b in cells:
        nf = cf if f is None else f               # blank ignores fg, full ignores bg
        nb = cb if b is None else b
        if nf==-1: nf=7
        if nb==-1: nb=0
        if nf!=cf or nb!=cb:
            o.append(sgr(nf,nb)); cf,cb=nf,nb
        o.append(gl)
    o.append("\x1b[0m")
    return "".join(o)

def vt_line(cells):
    o=["\x1b(0"]; rev=False
    for t,ch,rv in cells:
        if rv!=rev: o.append("\x1b[7m" if rv else "\x1b[0m"); rev=rv
        o.append(ch)
    o.append("\x1b[0m\x1b(B")
    return "".join(o)

class TTY:
    def __init__(s, vt100, stats):
        s.vt100, s.stats, s.prev, s.n = vt100, stats, [""]*FH, 0
    def s(s,t):
        s.n+=len(t.encode("utf-8")); sys.stdout.write(t)
    def boot(s):
        if not s.vt100: s.s("\x1b[?1049h\x1b[?25l")   # VT220/xterm/linux, not VT100
        s.s("\x1b[?7l\x1b[0m\x1b[2J")                 # DECAWM off: col 80 is safe
    def draw(s, sc, hud):
        s.n=0
        b=["\x1b[1H", (sgr(None,None) if s.vt100 else sgr(15,4)) + hud[:COLS].ljust(COLS) + "\x1b[0m"]
        rows=vt_rows(sc) if s.vt100 else cell_rows(sc)
        for r,cells in enumerate(rows):
            line=vt_line(cells) if s.vt100 else ansi_line(cells)
            if line==s.prev[r]: continue
            b.append("\x1b[%dH" % (r+1+HUD)); b.append(line)
            s.prev[r]=line
        b.append("\x1b[%dH" % ROWS)
        s.s("".join(b)); sys.stdout.flush()
        if s.stats: sys.stderr.write("frame %dB = %.2fs at 9600 baud\n"%(s.n,s.n/960.0))
    def bye(s):
        s.s("\x1b(B\x1b[0m")
        s.s("\x1b[?7h")
        if not s.vt100: s.s("\x1b[?25h\x1b[?1049l")

def hud(g):
    k=1.0-math.exp(-g.score/TAU)
    return (" FLAPPY-POOF %3d BEST %3d  GAP %4.1f ZONE %3.1f  %s%s "
            % (g.score,g.best,g.gap,(g.gap-BH)-APEX,"#"*int(18*k),"."*(18-int(18*k))))

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
            paint(sc,g,0.0)
            rows=[(vt_line if vt100 else ansi_line)(cl) for cl in (vt_rows if vt100 else cell_rows)(sc)]
            print(hud(g)); print("\n".join(rows)); print()
        return
    t=TTY(vt100,stats); t.boot(); acc,last=0.0,time.time()
    try:
        while True:
            now=time.time(); acc=min(0.25,acc+now-last); last=now
            while acc>=FIXED: g.step(FIXED); acc-=FIXED
            paint(sc,g,0.0)
            t.draw(sc,hud(g)); time.sleep(0.006)
    except KeyboardInterrupt: pass
    finally: t.bye()

if __name__=="__main__": main()
