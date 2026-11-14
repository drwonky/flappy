#!/usr/bin/env python3
"""flappy-opencode - self-playing Flappy Bird for an 80x25 terminal.

  python3 flappy-opencode.py             rich: full glyph set + 256-colour SGR
  python3 flappy-opencode.py --c16       Linux kernel console: 16 colours, CP437 glyphs
  python3 flappy-opencode.py --vt100     strict DEC Special Graphics, mono, no colour
  python3 flappy-opencode.py --frames 5  print 5 frames as text, no tty
  python3 flappy-opencode.py --selftest  headless games -> crash statistics
  python3 flappy-opencode.py --palette   material -> palette error report
  --seed N   --stats (bytes/frame in BOTH conventions, for 9600-baud curiosity)

RENDERING.  The scene is painted in the ORIGINAL's RGB palette on a 160x48
sub-pixel grid (2x2 sub-cells per character cell, which is square on a
terminal).  Each cell is then quantised to the single best (glyph, fg, bg) the
terminal can show, scoring candidates by summed CIELAB error over an 8x8 fine
sample of the cell.

That is a different model from flappy-vt100.py, whose shade lived in ink
DENSITY (sparse ink on bare paper) because it only ever had one colour per
cell.  Here every cell carries TWO colours - the glyph's foreground half and
its background half - so colour resolution is a full 160x48 and shade can be
carried by actual tone instead of by how much paper is left showing.

GLYPHS.  The search covers the semigraphics set, not one family: the 16
quadrant glyphs, which reproduce any 2x2 two-colour field with ZERO error; the
half and vertical blocks; and the three shade characters, which blend ink over
paper at a fixed rate and are what antialiased edges land on.  The Unicode
eighth-blocks are deliberately NOT offered - see the note in GLYPHS for why
they can never win against a 2x2 sub-pixel scene.

COLOUR FIDELITY is measured, not asserted: --palette reports the CIE76 distance
from each original material to each palette, and the renderer's mean rendered
error sits within ~0.2 dE of that palette floor (rich: 8.9 against a floor of
8.7).  The remaining error is the palette's, not the renderer's.

SCORING IS ON ONE SCALE, AND THAT WAS A BUG ONCE.  Every candidate - quadrant
glyph, half block, flat fill, shade blend - is scored as the MEAN squared CIE76
error over the 64 fine samples of a cell.  Flat fills and constant-rate blends
paint one colour everywhere, so their mean is just the mean of the cell's four
sub-pixel errors; a coverage glyph sums all 64.  Dividing both by 16 made
flat/shade look 16x better than they are and let them beat a strictly better
quadrant glyph.  check-opencode.py cross-checks quantise() against an
independently written exhaustive search over hand-written rectangle geometry,
which is what caught it.

FALLBACKS ARE NOT COSMETIC:
  --c16   drops the ten quadrant glyphs the console's CP437 font does not have
          (it has only space, full block, and the four half/vertical blocks),
          and restricts the BACKGROUND half of a cell to the eight non-bright
          colours, because console_codes(4) says the kernel "shoehorns" 48;5;n
          into 8 basic colours.  Foregrounds may be bright (90..97), backgrounds
          may not.  Emitting an absent glyph is a correctness bug, not a look
          bug, so the zero-error fast path is filtered per mode.
  --vt100 drops colour and blocks entirely.  DEC Special Graphics has exactly
          ONE shade - the 0x61 chequerboard - so the tone ladder is built from
          what the set actually has (' ' < '·' < '-' < chequerboard < '◆') plus
          SGR 7 reverse video, ordered-dithered on the cell grid.

PHYSICS start from flappy-vt100.py, and the thrust, gravity, speed and pipe
width are still its.  What moved is the hitbox and the gap it needs: the hitbox
is now the drawn sprite, not a smaller box beside it.  --selftest therefore
prints BETTER crash statistics than flappy-vt100.py does (the honest box is
bigger, and the pilot's safe-flap zone is unchanged at 2.4 sub-rows); the gate
is that the zone stays positive and no seeded game dies before pipe 40.
"""
import sys, time, math, random

COLS, ROWS = 80, 25
HUD        = 1
FH         = ROWS - HUD
SW, SH     = COLS*2, FH*2
GROUND     = 10
SKY        = SH - GROUND
FIXED      = 1.0/60

# ---------- physics, all in SUB-PIXELS (seeded from flappy-vt100.py) ----------
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
# The hitbox IS the drawn sprite, and the collision test below walks the sprite's
# own ink rows -- not a box invented separately from the art.  It used to be
# 7.8x6.0 while the drawn bird was 17x10, and ONE number served as the clearance
# BOTH above and below the physics centre while draw_bird anchored the sprite by
# its INK BOTTOM: all the forgiveness sat above the centre, so the bird visibly
# entered the UPPER pipe while the game still called it alive (measured: 5.7% of
# live frames, 99.8% of them the upper pipe).  An honest box is 4 sub-rows
# taller than the old one, so the gap had to grow to keep it flyable -- exactly
# what the reference did when it drew its own bird 2x (its comment: "floor raised
# from 96: the bird is 16 tall now").  Asserted against BIRD_W/BIRD_H below.
HW, HTOP, HBOT = 8.5, 5.0, 5.0
PIPE_W  = 29                     # 29/160 = 0.181 = original 52/288 screens
SPD0, SPD1 = 0.4167*SW, 0.5600*SW   # original 120px/s on 288 wide
SPC0, SPC1 = 0.625*SW, 0.500*SW     # original 169px on 288 -> 1.7 pipes visible
GAP0, GAP1 = 24.0, 20.0          # raised from 20/16: see the hitbox note above
TAU     = 85.0
APEX    = FLAP*FLAP/(2*GRAV)
SAFE    = (GAP1-HTOP-HBOT)-APEX  # width of the safe-flap band at the asymptote

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
        s.aim = (s.rng.random()*2-1)*(s.gap-HTOP-HBOT)*0.12
    # Thrust is one-sided: flapping at y puts your apex at y-APEX, so to cross
    # a gate you must enter no higher than top+HTOP+APEX (else you clip the upper
    # pipe) and no lower than bot-HBOT. Riding the TOP of that window is a limit
    # cycle whose parabola spans exactly APEX. Aim blends to the next gate early
    # enough to sink/climb to it, since descending costs only an abstained flap.
    def zlo(s, n): return n["top"]+HTOP+APEX
    def want(s, n):
        z, hi = s.zlo(n), n["bot"]-HBOT
        if z >= hi: return s.y < 0.5*(n["top"]+n["bot"])
        m = next((p for p in s.pipes if p["x"] > n["x"]+PIPE_W), None)
        if m:
            T   = (m["x"]-n["x"])/s.speed
            tT  = (n["x"]-(BIRD_X+HW))/s.speed
            if tT > T*0.55: z = min(z, s.zlo(m))
            if tT > T*0.30: z = max(z, s.zlo(m))
        if s.y+HBOT >= SKY-1.0: return True
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
        if s.y < HTOP: s.y, s.vy = HTOP, max(s.vy, 0.0)   # ceiling clamps: original
        for p in s.pipes:
            p["x"] -= s.speed*dt
            if not p["pass"] and p["x"]+PIPE_W < BIRD_X-HW:
                p["pass"] = True; s.score += 1
                if s.score > s.best: s.best = s.score
        s.pipes = [p for p in s.pipes if p["x"]+PIPE_W > -PIPE_W]
        if s.y+HBOT >= SKY: s.die(); return           # only the ground kills
        y0, runs, x0 = bird_ink(s)                    # the sprite's own ink
        for p in s.pipes:
            if ink_hits_pipe(p, y0, runs, x0): s.die(); return
    def die(s): s.dead, s.deadT = True, 0.0

# ---------- the original's palette ----------
HEX = {
 "skyA":"#6cc5de","skyB":"#9adcec","skyC":"#c6ecf2","skyD":"#e4f6f7",
 "cloud":"#eef7fa","hill":"#7fbf4d","hillDark":"#5f9a38",
 "grass":"#74bf2e","grassDark":"#4e8f21","sand":"#ded895","sandDark":"#c3bb6d",
 "pipeO":"#14200f","pipeLt":"#8ed04a","pipeHi":"#74bf2e","pipeMid":"#5aa81f",
 "pipeLo":"#3d7a12","ink":"#1a2419",
 "birdY":"#f8e018","birdD":"#d9a90f","birdC":"#f5f2c0",
 "eye":"#ffffff","pupil":"#20242a","beak":"#e8483a","beakLo":"#b62f26",
 "white":"#ffffff",
}
def hx(h): h=h.lstrip('#'); return (int(h[0:2],16),int(h[2:4],16),int(h[4:6],16))
RGB = {k:hx(v) for k,v in HEX.items()}
MATS = tuple(HEX)

# ---------- palette tables ----------
def x256(i):
    """rgb of an xterm-256 index."""
    if i<16:
        base=[(0,0,0),(128,0,0),(0,128,0),(128,128,0),(0,0,128),(128,0,128),
              (0,128,128),(192,192,192),(128,128,128),(255,0,0),(0,255,0),
              (255,255,0),(0,0,255),(255,0,255),(0,255,255),(255,255,255)]
        return base[i]
    if i<232:
        i-=16; lv=(0,95,135,175,215,255)
        return (lv[i//36], lv[(i//6)%6], lv[i%6])
    v=8+10*(i-232); return (v,v,v)
PAL256=[x256(i) for i in range(256)]
ANSI16=[x256(i) for i in range(16)]

def _lab(rgb):
    def lin(c):
        c=c/255.0
        return c/12.92 if c<=0.04045 else ((c+0.055)/1.055)**2.4
    r,g,b=[lin(c) for c in rgb]
    X=(0.4124*r+0.3576*g+0.1805*b)/0.95047
    Y=0.2126*r+0.7152*g+0.0722*b
    Z=(0.0193*r+0.1192*g+0.9505*b)/1.08883
    f=lambda t: t**(1.0/3.0) if t>0.008856 else 7.787*t+16.0/116.0
    fx,fy,fz=f(X),f(Y),f(Z)
    return (116.0*fy-16.0, 500.0*(fx-fy), 200.0*(fy-fz))
_LAB={}
def lab(c):
    v=_LAB.get(c)
    if v is None: v=_LAB[c]=_lab(c)
    return v
def dE2(a,b):
    x,y=lab(a),lab(b)
    return (x[0]-y[0])**2+(x[1]-y[1])**2+(x[2]-y[2])**2

# Per-mode colour lookups.  In --c16 the SCENE is painted with the 16 console
# colours, not with the true colours and then projected: projecting after the
# fact would let the quantiser pick a background the console cannot show.
IDX16={}
MAT16={}
for _m in MATS:
    IDX16[_m]=min(range(16), key=lambda i: dE2(RGB[_m], ANSI16[i]))
    MAT16[_m]=ANSI16[IDX16[_m]]
# In rich mode the SCENE is painted with colours the terminal can show exactly,
# not with the true colours projected afterwards.  Same choice as --c16 and for
# the same reason: if the target is already representable, the quantiser's job
# is only to place it, and the cell error is then the palette's own floor and
# nothing worse.  The authentic colours are kept for the mono ladder and for
# --palette, which reports that floor.
IDX256={}
COL256={}
for _m in MATS:
    IDX256[_m]=min(range(256), key=lambda i: dE2(RGB[_m], PAL256[i]))
    COL256[_m]=PAL256[IDX256[_m]]
COL16={m:MAT16[m] for m in MATS}
IDX_OF={c:i for i,c in enumerate(PAL256)}
ANSI_IDX={c:i for i,c in enumerate(ANSI16)}
BG16SET=set(ANSI16[:8])           # backgrounds: the eight non-bright colours

# ---------- framebuffer: one RGB per sub-pixel, plus a material tag ----------
class Scene:
    def __init__(s):
        s.C=[[(0,0,0)]*SW for _ in range(SH)]
        s.M=[[None]*SW for _ in range(SH)]
    def put(s,y,x,c,m):
        if 0<=y<SH and 0<=x<SW: s.C[y][x]=c; s.M[y][x]=m
    def rect(s,x,y,w,h,c,m):
        y0,y1=int(y),int(y+h); x0,x1=max(0,int(x)),min(SW,int(x+w))
        for yy in range(y0,y1):
            if not (0<=yy<SH): continue
            row=s.C[yy]; rowM=s.M[yy]
            for xx in range(x0,x1): row[xx]=c; rowM[xx]=m
    def clear(s):
        black=(0,0,0)
        for r in s.C:
            for i in range(SW): r[i]=black

# ---------- scene geometry (from flappy-vt100.py, now in the original's palette)
# Horizontal scale is the original's: pipe 29/160 = 52/288.  The field is
# 160x48 square sub-pixels, a 3.3:1 aspect against the original's 0.7:1, so
# VERTICAL proportions cannot be copied from a portrait screen; these heights
# were already re-tuned for this field by the code this was seeded from.
CAP_X = 3       # original lip overhang is 6 of a 52 shaft -> 3 of our 29
CAP_H = 4       # lip depth in sub-rows
SHAFT=[(0,1,"pipeO"),(1,3,"pipeLt"),(4,6,"pipeHi"),(10,10,"pipeMid"),
       (20,8,"pipeLo"),(28,1,"pipeO")]                       # 52-wide bands -> 29
CAP_W = PIPE_W + 2*CAP_X          # the lip's full width, incl. both overhangs

# The lip is NOT a second hand-authored band list.  In the ORIGINAL the lip is
# the shaft's own bands, widened by the overhang: the left overhang continues
# the catch-light ("left bands match the shaft exactly") and the right overhang
# continues the shadow ("the overhang lands in the shadow - that IS the turn").
# Reference bands over a 64-wide lip: 1,12,11,18,20,1,1.  Derived, not typed,
# because a hand-typed LIP covered 31 sub-columns while the lip's dark rules
# are drawn CAP_W = 35 wide, so the lip's right 4 sub-columns got no body fill
# and its right edge visibly did not line up.
def _lip(shaft, over):
    bands=[list(t) for t in shaft]
    bands[1][1]  += over          # left catch-light swallows the left overhang
    bands[-2][1] += over          # right shadow swallows the right overhang
    out=[]; off=0
    for _ox,bw,mn in bands:       # re-flow offsets so the bands tile with no gaps
        out.append((off,bw,mn)); off+=bw
    return tuple(out)
LIP=_lip(SHAFT,CAP_X)

def _tile_ok(bands, want, label):
    off=0
    for ox,bw,_n in bands:
        if ox!=off: return "%s: gap/overlap at sub-col %d (expected %d)" % (label,ox,off)
        off+=bw
    return None if off==want else "%s: bands cover %d, geometry wants %d" % (label,off,want)
_bad=(_tile_ok(SHAFT,PIPE_W,"SHAFT"), _tile_ok(LIP,CAP_W,"LIP"))
assert not any(_bad), _bad
# the rules that cap the lip must be drawn exactly as wide as the lip's bands
assert CAP_W == PIPE_W + 2*CAP_X

def paint(sc, g, flash, COL):
    sc.clear()
    bands=[RGB["skyA"],RGB["skyB"],RGB["skyC"],RGB["skyD"]]
    idx=["skyA","skyA","skyB","skyB","skyC","skyC","skyD"]
    bh=-(-SKY//len(idx))
    for y in range(SKY):
        i=min(len(idx)-1, y//bh); m=idx[i]; c=COL[m]
        row=sc.C[y]; rowM=sc.M[y]
        for x in range(SW): row[x]=c; rowM[x]=m
    off=g.clock*g.speed*0.16                     # far skyline
    for i in range(12):
        x=int(((i*34-off)%(SW+34))-17)
        sc.rect(x,SKY-13,30,13,COL["hillDark"],"hillDark")
        sc.rect(x+5,SKY-15,20,2,COL["hillDark"],"hillDark")
        sc.rect(x+11,SKY-17,9,2,COL["hillDark"],"hillDark")
    off=g.clock*g.speed*0.34                     # near skyline
    for i in range(9):
        x=int(((i*40-off)%(SW+40))-20)
        sc.rect(x,SKY-7,34,7,COL["hill"],"hill")
        sc.rect(x+4,SKY-9,24,2,COL["hill"],"hill")
        sc.rect(x+13,SKY-11,12,2,COL["hill"],"hill")
    off=g.clock*g.speed*0.09                     # clouds: flat, as the original
    for i in range(4):
        x=int(((i*60-off)%(SW+60))-30); y=7+(i%3)*7
        sc.rect(x,y,26,5,COL["cloud"],"cloud")
        sc.rect(x+6,y-3,13,3,COL["cloud"],"cloud")
        sc.rect(x+11,y-5,9,2,COL["cloud"],"cloud")
        sc.rect(x-4,y+5,30,2,COL["cloud"],"cloud")
    for p in g.pipes:                            # pipes: banded shaft + banded lip
        x=int(round(p["x"]))
        for y0,y1,top in ((0,p["top"],True),(p["bot"],SKY,False)):
            a,b=int(y0),int(y1)
            lip=(b-CAP_H) if top else a
            s0,s1=(a,lip) if top else (lip+CAP_H,b)
            for m0,m1,bands2,dx in ((s0,s1,SHAFT,0),(lip,lip+CAP_H,LIP,-CAP_X)):
                for ox,bw,mn in bands2:
                    if m1>m0: sc.rect(x+dx+ox, m0, bw, m1-m0, COL[mn], mn)
            if lip<b:                            # the lip's dark rules, top+bottom
                sc.rect(x-CAP_X, lip, CAP_W, 1, COL["pipeO"], "pipeO")
                sc.rect(x-CAP_X, lip+CAP_H-1, CAP_W, 1, COL["pipeO"], "pipeO")
    sc.rect(0,SKY,SW,2,COL["grass"],"grass")     # ground: grass, seam, sand, stripes
    sc.rect(0,SKY+2,SW,1,COL["grassDark"],"grassDark")
    sc.rect(0,SKY+3,SW,SH-SKY-3,COL["sand"],"sand")
    off=int(g.clock*g.speed)%13
    for x in range(-13,SW+13,13):
        sc.rect(x-off,SKY+5,7,SH-SKY-5,COL["sandDark"],"sandDark")
        sc.rect(x-off+7,SKY+3,3,2,COL["grassDark"],"grassDark")
    draw_bird(sc,g,COL)
    if flash>0:                                  # death flash: blend to white
        w=(255,255,255); f=flash
        for y in range(SH):
            row=sc.C[y]
            for x in range(SW):
                c=row[x]
                row[x]=(int(c[0]*(1-f)+w[0]*f), int(c[1]*(1-f)+w[1]*f),
                        int(c[2]*(1-f)+w[2]*f))

# ---------- the bird, authored in the original's colours ----------
# The reference art is a 17x12 sprite drawn 2x (34x24) against a 52-wide shaft,
# so its ink box is 0.65 of the shaft.  Our shaft is 29 wide, so the body is
# authored ~15 wide with the beak reaching col 16: 17/29 = 0.59, up from the
# 8/29 = 0.28 that flappy-vt100.py drew.  That undersize, not the shading, was
# why the bird never read as the original's.
#   K ink outline   Y body   D shade   C breast   W eye white   P pupil
#   R beak         O beak lower     (wings: k outline, w fill)
# Every FEATURE (eye, pupil, beak) is at least 2 sub-pixels wide AND tall.
# A 1-sub-pixel feature can land alone in a cell that already holds two other
# colours, and a two-colour glyph cannot render three colours: the quantiser is
# then forced to drop the feature.  That is why the pupil measured 36.8 dE
# before - not the palette's fault (its floor is 4.7), the art's.
BIRD_BODY=(
    "....KKKKKKKK.....",
    "..KKYYYYYYWWWWK..",
    ".KYYYYYYYWPPWWK..",
    ".KYYYYYYYWPPWWK..",
    ".KDDYYYYYCCCCWRRK",
    "KDDDDDDYYCCCWWRRK",
    "KDDDDDDYCCCCCCOOK",
    ".KDDDDDCCCCCCOOOK",
    "..KKDDDDCCCCKK...",
    "....KKKKKKK......",
)
# three wing poses, as (row, col, pattern) overlays; the original's four flap
# frames differ ONLY in the wing, and two of its four are byte-identical, so
# three poses is what the source art actually contains.
# Each pose is a ring of ink outline with a shade-coloured interior, placed over
# the body: raised (just after a flap), mid, and lowered (gliding).
WING_UP  =((1,1,"kkkkkk"),(2,1,"kwwwwk"),(3,1,"kwwwwk"),(4,1,"kkkkkk"))
WING_MID =((4,1,"kkkkkk"),(5,1,"kwwwwk"),(6,1,"kwwwwk"),(7,1,"kkkkkk"))
WING_DOWN=((6,3,"kkkkkk"),(7,3,"kwwwwk"),(8,3,"kwwwwk"),(9,3,"kkkkkk"))
BCOL={"K":"ink","Y":"birdY","D":"birdD","C":"birdC","W":"eye","P":"pupil",
      "R":"beak","O":"beakLo","k":"ink","w":"birdD"}
BIRD_W, BIRD_H = 17, 10
assert all(len(r)==BIRD_W for r in BIRD_BODY), "sprite rows must be BIRD_W wide"
assert all(len(p)==6 for _,_,p in WING_UP+WING_MID+WING_DOWN), \
       "wing pattern rows must all be 6 wide"
assert all(0<=r<BIRD_H and 0<=c+6<=BIRD_W for r,c,_ in WING_UP+WING_MID+WING_DOWN), \
       "wing overlays must stay inside the sprite box"
# a typo'd sprite character must not survive to runtime
assert not {ch for r in BIRD_BODY for ch in r} - set(".") - set(BCOL), \
       "BIRD_BODY uses a character with no colour: %s" % (
        {ch for r in BIRD_BODY for ch in r} - set(".") - set(BCOL))
# each named feature must be at least 2 sub-px tall somewhere, or a cell that
# also contains two other colours will be forced to drop it
def _feature_heights(body):
    h={}
    for ch in set("".join(body))-{"."}:
        best=cur=0
        rows=[ch in r for r in body]
        # longest vertical run within any single column
        for c in range(BIRD_W):
            cur=0
            for r in range(BIRD_H):
                cur = cur+1 if body[r][c]==ch else 0
                best=max(best,cur)
        h[ch]=best
    return h
_FEAT=_feature_heights(BIRD_BODY)
_MINFEAT={"P":2,"W":2,"R":2,"O":2}
assert all(_FEAT[k]>=v for k,v in _MINFEAT.items()), \
       "features too thin for a 2-colour cell: %s" % {k:v for k,v in _FEAT.items()
                                                       if k in _MINFEAT and v<_MINFEAT[k]}

def _pose_rows(pose):
    """body with a wing pose composited over it, exactly as it will be painted."""
    rows=[list(r) for r in BIRD_BODY]
    for (r,c,pat) in pose:
        for i,ch in enumerate(pat):
            if 0<=r<BIRD_H and 0<=c+i<BIRD_W: rows[r][c+i]=ch
    return rows

def _ink_runs(rows):
    """per sprite row, the sub-columns holding ink as (first, last) - or None.
    The contiguity assert below is what lets a row be ONE interval, which is what
    makes the collision test exactly pixel-exact rather than a bounding guess."""
    out=[]
    for r in range(BIRD_H):
        cs=[c for c in range(BIRD_W) if rows[r][c]!="."]
        out.append((cs[0],cs[-1]) if cs else None)
    return out

# The wing phase has exactly three values, so the sprite is one of three known
# shapes.  Both are rasterised ONCE here and shared by the renderer and the
# collision test: the shape that kills the bird is literally the same data the
# picture is drawn from, and no step pays to re-derive it.
POSE_AT   = (0.60, 0.18, None)     # g.wing above each threshold picks that pose
POSE_TABLE = []
for _i, _pose in enumerate((WING_UP, WING_MID, WING_DOWN)):
    _rows = _pose_rows(_pose)
    POSE_TABLE.append((_rows, _ink_runs(_rows)))

def pose_of(g):
    ph = g.wing
    for i, th in enumerate(POSE_AT):
        if th is None or ph > th: return POSE_TABLE[i]
    return POSE_TABLE[-1]

BIRD_Y0 = BIRD_H//2               # ink top sits this far above the physics centre

def bird_ink(g):
    """(ink top row, ink first/last column per row, ink left column) exactly as
    draw_bird paints them.  Collision reads THIS, so the shape that kills the
    bird can never again be a different shape from the one the viewer sees."""
    return int(round(g.y))-BIRD_Y0, pose_of(g)[1], int(round(BIRD_X))-(BIRD_W//2)

def ink_hits_pipe(p, y0, runs, x0):
    """Does any INK pixel of the drawn bird land on a drawn pixel of pipe p?
    Mirrors paint() exactly: pipe rows are int() truncations of p["top"]/
    p["bot"], pipe columns are int(round(p["x"])), and the lip band overhangs
    the shaft by CAP_X for CAP_H rows at the mouth of each pipe."""
    px    = int(round(p["x"]))
    top, bot = int(p["top"]), int(p["bot"])
    for r in range(BIRD_H):
        run = runs[r]
        if run is None: continue
        yy = y0+r
        if top <= yy < bot: continue            # inside the drawn gap: all air
        if yy < top and yy >= top-CAP_H:        # the upper lip overhangs
            pl, pr = px-CAP_X, px+PIPE_W+CAP_X
        elif yy >= bot and yy < bot+CAP_H:      # and the lower one
            pl, pr = px-CAP_X, px+PIPE_W+CAP_X
        else:
            pl, pr = px, px+PIPE_W
        if x0+run[0] < pr and x0+run[1] >= pl: return True
    return False

# The hitbox is the sprite, so it may not be authored independently of it.
assert (HW, HTOP, HBOT) == (BIRD_W/2.0, BIRD_H/2.0, BIRD_H/2.0), \
       "hitbox %s must be the drawn sprite 17x10, not a separate invention" % (
        (HW, HTOP, HBOT),)
# one interval per row is what makes ink_hits_pipe exact rather than
# conservative: it checks the interval, so a row with a clear sub-pixel inside
# it would report a hit that the viewer cannot see.  Checked on the very data
# the collision test walks, so the assert cannot drift from it.
for _t, (_rows, _runs) in enumerate(POSE_TABLE):
    for _r in range(BIRD_H):
        if _runs[_r] is None: continue
        _cs=[c for c in range(BIRD_W) if _rows[_r][c]!="."]
        assert _runs[_r]==(_cs[0],_cs[-1]) and _cs[-1]-_cs[0]+1==len(_cs), \
               "sprite row %d of pose %d has a gap of clear sub-pixels: " \
               "ink_hits_pipe would treat it as solid" % (_r,_t)

def draw_bird(sc, g, COL):
    x0 = int(round(BIRD_X)) - (BIRD_W//2)
    y0 = int(round(g.y)) - BIRD_Y0
    rows = pose_of(g)[0]
    for r in range(BIRD_H):
        yy=y0+r
        for c0 in range(BIRD_W):
            ch=rows[r][c0]
            if ch==".": continue
            m=BCOL[ch]
            sc.put(yy, x0+c0, COL[m], m)

# ---------- glyph inventory: coverage masks over an 8x8 fine grid ----------
# A glyph's mask says how much of each fine sample the FOREGROUND paints; the
# background shows through the rest.  The grid spans the WHOLE cell: sample
# (py,px) sits at ((py+0.5)/N, (px+0.5)/N), so py=0 is the top of the cell and
# py=N-1 the bottom.  Every coverage glyph here is a hard-edged rectangle or
# union of them, so a mask is binary and the error for a candidate decomposes
# into a per-quadrant count - see QUADCOUNT below.
N=8
def _mask(fn):
    # fn takes (x,y) with x horizontal and y vertical; the loop runs py (row)
    # outer, px (column) inner, so the argument order here matters.
    return [1.0 if fn((px+0.5)/N,(py+0.5)/N) else 0.0
            for py in range(N) for px in range(N)]
def _q(ul,ur,ll,lr):
    return lambda x,y: (ul if (y<0.5 and x<0.5) else ur if (y<0.5 and x>=0.5)
                        else ll if (y>=0.5 and x<0.5) else lr)
GLYPHS={
 " ":    lambda x,y: False,
 "\u2588":lambda x,y: True,
 # half and vertical blocks.  The predicate says where the FOREGROUND is:
 # U+2580 is the UPPER half block, so its foreground is the top half.
 "\u2580":_q(1,1,0,0), "\u2584":_q(0,0,1,1),
 "\u258c":_q(1,0,1,0), "\u2590":_q(0,1,0,1),
 # the 16 quadrant glyphs: each reproduces one 2x2 two-colour field EXACTLY
 "\u2598":_q(1,0,0,0), "\u2597":_q(0,0,0,1), "\u2596":_q(0,0,1,0), "\u259d":_q(0,1,0,0),
 "\u2599":_q(1,0,1,1), "\u259f":_q(0,1,1,1), "\u259b":_q(1,1,1,0), "\u259c":_q(1,1,0,1),
 "\u259a":_q(1,0,0,1), "\u259e":_q(0,1,1,0),
 # NO eighth-blocks (U+2581-2587, U+2594, U+258F-258B), even though they are
 # Unicode and look like they belong in a finer-grained renderer.  They exist
 # to draw a stroke THINNER than half a cell.  But this scene is painted as
 # exactly 2x2 sub-pixels per character cell, so its thinnest possible feature
 # is one sub-pixel = one quadrant, which a quadrant glyph reproduces EXACTLY.
 # A sub-half-cell stroke cannot occur here, so an eighth-block can never be the
 # best candidate: measured over 76,800 cells, including the death-flash frames
 # that do create 3-colour cells, every one of them was chosen 0 times.  They
 # were removed rather than carried as dead weight the header would over-claim.
}
MASK={g:_mask(f) for g,f in GLYPHS.items()}
# the three shade characters are NOT coverage: they paint fg over bg at a fixed
# rate, so every sample of the cell shows the same blended colour.
SHADE={"\u2591":0.25, "\u2592":0.50, "\u2593":0.75}

# Which sub-pixel of the 2x2 cell each fine sample belongs to (TL,TR,BL,BR)
SUBPIX=[(py//4)*2+(px//4) for py in range(N) for px in range(N)]
# how many of each glyph's 64 samples land in each of the 4 sub-pixels
def _qc(g):
    q=[0,0,0,0]
    for i,mk in enumerate(MASK[g]):
        if mk: q[SUBPIX[i]]+=1
    return tuple(q)
QUADCOUNT={g:_qc(g) for g in GLYPHS}
QUADCOUNT.update({g:(0,0,0,0) for g in SHADE})
COVERAGE=set(GLYPHS)

# quadrant glyph chosen by which quadrants carry the FG colour, DERIVED from the
# masks so the table can never disagree with them.
# bit order matches cell_glyph: 8=top-left, 4=top-right, 2=bottom-left, 1=bottom-right
QBIT=[8,4,2,1]
QUAD={}
for _g in ("\u2598","\u2597","\u2596","\u259d","\u2599","\u259f","\u259b","\u259c",
           "\u259a","\u259e","\u258c","\u2590","\u2580","\u2584"):
    _q=QUADCOUNT[_g]
    _b=0
    for _i in range(4):
        if _q[_i]==16: _b |= QBIT[_i]
        elif _q[_i]!=0: raise AssertionError("%s is not a quadrant glyph"%_g)
    if _b in QUAD: raise AssertionError("duplicate quadrant mapping at %d"%_b)
    QUAD[_b]=_g
QUAD[0]=" "; QUAD[15]="\u2588"
assert len(QUAD)==16, "expected all 16 quadrant patterns, got %d"%len(QUAD)

# Capability levels.  CP437 has ONLY these block glyphs in the Linux console's
# font: the ten quadrant glyphs and every eighth-block are absent there, which
# is why --c16 cannot use them even though they are Unicode.
CP437=(" ","\u2588","\u2580","\u2584","\u258c","\u2590")
SET_RICH=tuple(GLYPHS)+tuple(SHADE)
SET_C16=CP437+tuple(SHADE)
# The zero-error fast path must be restricted to glyphs the terminal HAS.  Of
# the sixteen quadrant patterns, CP437 only carries six; the console draws its
# replacement character for the rest, which is far worse than an approximate
# glyph.  So the quadrant table is filtered per mode.
QUADS_RICH=dict(QUAD)
QUADS_C16={b:g for b,g in QUAD.items() if g in CP437}

# ---------- quantiser: 2x2 colour field -> one (glyph, fg, bg) ----------
def _mix(fg,bg,t):
    return (int(fg[0]*t+bg[0]*(1-t)), int(fg[1]*t+bg[1]*(1-t)),
            int(fg[2]*t+bg[2]*(1-t)))

def quantise(cell, bg_ok, glyphs, quads, cache):
    """cell: 4 rgb tuples, row-major (TL,TR,BL,BR) -> (glyph, fg, bg, err)."""
    hit=cache.get(cell)
    if hit is not None: return hit
    cols=[]
    for c in cell:
        if c not in cols: cols.append(c)
    # FAST PATH.  A quadrant glyph reproduces any two-colour 2x2 field with
    # ZERO error, and most cells in this scene are exactly that.  Try both
    # orientations, since a background may be disallowed (--c16).
    #
    # This path is gated on the glyph being AVAILABLE.  --c16 only has six of
    # the sixteen patterns in the console's font (space, full block, and the
    # four half/vertical blocks); the other ten are valid Unicode but the
    # console draws a replacement character for them, which is worse than a
    # slightly wrong two-tone glyph.  Emitting an unavailable glyph is a
    # correctness bug, not a look bug, so QUADS is per-mode, not global.
    if len(cols)==2:
        lo,hi=cols
        bits=0
        for j,c in enumerate(cell):
            if c==hi: bits |= (8,4,2,1)[j]
        for fg,bg,b in ((hi,lo,bits),(lo,hi,15^bits)):
            if not bg_ok(bg): continue
            g=quads.get(b)
            if g is None: continue
            out=(g,fg,bg,0.0) if g not in (" ","\u2588") else \
                (("\u2588",fg,None,0.0) if g=="\u2588" else (" ",None,bg,0.0))
            cache[cell]=out
            return out
    tgt=[lab(c) for c in cell]
    best=[None]
    def consider(e,g,fg,bg):
        if best[0] is None or e<best[0][0]: best[0]=(e,g,fg,bg)
    # SCORING MUST BE ON ONE SCALE.  Every candidate is scored as the MEAN
    # squared CIE76 error over the 64 fine samples of the cell.  A flat fill
    # and a constant-rate shade blend paint the same colour everywhere, so
    # their mean equals the mean of the cell's four sub-pixel errors (each
    # sub-pixel contributes 16 identical samples).  A coverage glyph scores
    # its sum over all 64 samples.  Earlier this divided all three by 16,
    # which made flat/shade candidates look 16x better than they are and let
    # them beat a strictly better quadrant glyph - an independent exhaustive
    # search caught it, so the divisors are now per-family on purpose.
    for c in cols:                                  # flat fills
        l=lab(c); e=0.0
        for t in tgt: e+=(l[0]-t[0])**2+(l[1]-t[1])**2+(l[2]-t[2])**2
        e/=4.0
        if bg_ok(c): consider(e," ",None,c)
        consider(e,"\u2588",c,None)
    # Coverage glyphs.  Coverage is binary, so a candidate's error is a sum over
    # the four sub-pixels of (samples painted with fg)*err_fg + the rest*err_bg.
    for fg in cols:
        lfg=lab(fg)
        efg=[(lfg[0]-t[0])**2+(lfg[1]-t[1])**2+(lfg[2]-t[2])**2 for t in tgt]
        for bg in cols:
            if bg==fg or not bg_ok(bg): continue
            lbg=lab(bg)
            ebg=[(lbg[0]-t[0])**2+(lbg[1]-t[1])**2+(lbg[2]-t[2])**2 for t in tgt]
            for g in glyphs:
                if g not in COVERAGE: continue
                q=QUADCOUNT[g]
                if q==(0,0,0,0) or q==(16,16,16,16): continue   # flat, scored above
                e=(q[0]*efg[0]+(16-q[0])*ebg[0] + q[1]*efg[1]+(16-q[1])*ebg[1]
                   + q[2]*efg[2]+(16-q[2])*ebg[2] + q[3]*efg[3]+(16-q[3])*ebg[3])/64.0
                consider(e,g,fg,bg)
    for g,tl in SHADE.items():                      # constant-rate blends
        if g not in glyphs: continue
        for fg in cols:
            for bg in cols:
                if bg==fg or not bg_ok(bg): continue
                l=lab(_mix(fg,bg,tl)); e=0.0
                for t in tgt: e+=(l[0]-t[0])**2+(l[1]-t[1])**2+(l[2]-t[2])**2
                consider(e/4.0,g,fg,bg)
    if best[0] is None: consider(0.0," ",None,cols[0])
    e,g,fg,bg=best[0]
    out=(g,fg,bg,e)
    cache[cell]=out
    return out

def render(sc, bg_ok, glyphs, quads, cache):
    rows=[]
    for r in range(FH):
        ca,cb=sc.C[r*2],sc.C[r*2+1]
        out=[]
        for c in range(COLS):
            cell=(ca[2*c],ca[2*c+1],cb[2*c],cb[2*c+1])
            g,fg,bg,_=quantise(cell,bg_ok,glyphs,quads,cache)
            out.append((g,fg,bg))
        rows.append(out)
    return rows

# rgb -> SGR index.  Most colours are already exact palette entries, but the
# death flash blends the whole field toward white and produces colours that are
# not, so fall back to nearest.  Cached: the scene uses a few dozen colours.
def make_mapper(palette):
    exact={c:i for i,c in enumerate(palette)}
    near={}
    def one(c):
        i=exact.get(c)
        if i is not None: return i
        i=near.get(c)
        if i is None:
            i=near[c]=min(range(len(palette)), key=lambda j: dE2(c,palette[j]))
        return i
    return one
def to_indices(rows, idx):
    out=[]
    for row in rows:
        line=[]
        for g,fg,bg in row:
            line.append((g, None if fg is None else idx(fg),
                            None if bg is None else idx(bg)))
        out.append(line)
    return out

# ---------- strict VT100: DEC Special Graphics, mono, no blocks ----------
# DEC has exactly ONE shade, the 0x61 chequerboard; a light '░' and a heavy
# '▓' are NOT in the set (they are the same code there).  So the tone ladder is
# built from what the set really has, plus SGR 7 reverse video, which a real
# VT100 does implement:
#     space  <  '·'(0x7e)  <  '-'(0x71)  <  chequerboard(0x61)  <  '◆'(0x60)  <  solid
# Luminance alone cannot tell a green pipe from a cyan sky, and a YELLOW bird is
# nearly invisible by luminance, so mono assigns ink by MATERIAL ROLE: sky is
# faintly dithered paper, cloud is bare paper (the engraving idiom - a cloud is
# defined by being lighter than the sky around it), and the bird's body sits at
# mid-tone against its own ink outline.
VT_LADDER=((" ",0.00,False),("~",0.14,False),("q",0.34,False),
           ("a",0.55,False),("`",0.75,False),(" ",1.00,True))
MONO_INK={"skyA":0.03,"skyB":0.05,"skyC":0.07,"skyD":0.10,   # keys must match the
                                                       # painter's material names
          "cloud":0.00,"hill":0.45,"hillDark":0.60,
          "grass":0.50,"grassDark":0.68,"sand":0.30,"sandDark":0.48,
          "pipeO":1.00,"pipeLt":0.42,"pipeHi":0.52,"pipeMid":0.62,"pipeLo":0.78,
          "ink":1.00,"birdY":0.48,"birdD":0.62,"birdC":0.22,"eye":0.05,
          "pupil":0.95,"beak":0.55,"beakLo":0.72,"white":0.00}
# Every material the painter can emit needs a mono ink level, or an untagged
# cell silently falls to a default and the picture gets holes in it.
_HOLES=[k for k in MATS if k not in MONO_INK]
assert not _HOLES, "MONO_INK missing materials: %s" % _HOLES
BAYER4=((0,8,2,10),(12,4,14,6),(3,11,1,9),(15,7,13,5))
def vt_frame(sc):
    rows=[]
    L=len(VT_LADDER)
    for r in range(FH):
        line=[]
        for c in range(COLS):
            ink=0.0
            for dy in (0,1):
                for dx in (0,1):
                    ink+=MONO_INK.get(sc.M[r*2+dy][c*2+dx],0.5)
            ink/=4.0
            tgt=ink*(L-1)
            base=int(tgt); frac=tgt-base
            k=(BAYER4[(r*2)&3][(c*2)&3]+0.5)/16.0
            lvl=base+(1 if frac>=k else 0)
            lvl=max(0,min(L-1,lvl))
            ch,_,rev=VT_LADDER[lvl]
            line.append((ch,rev))
        rows.append(line)
    return rows

# ---------- terminal output ----------
class TTY:
    def __init__(s, mode, stats):
        s.mode, s.stats = mode, stats
        s.prev=[None]*FH
        s.gmode=None; s.fg=None; s.bg=None; s.rev=False
        s.n=0; s.nw=0
    def s(s,t):
        s.n+=len(t.encode("latin-1","replace")); s.nw+=len(t.encode("utf-8","replace"))
        sys.stdout.write(t)
    def boot(s):
        # alt-screen and hide-cursor are VT220/xterm extensions, not VT100
        if s.mode!="vt100": s.s("\x1b[?1049h\x1b[?25l")
        s.s("\x1b[2J")
    def draw(s, rows, hud):
        s.n=0; s.nw=0
        b=["\x1b[1H"]
        if s.gmode: b.append("\x1b(B"); s.gmode=None
        b.append("\x1b[0m"); s.fg=s.bg=None; s.rev=False
        b.append(hud[:COLS].ljust(COLS))
        for r in range(FH):
            row=rows[r]
            if s.prev[r]==row: continue
            end=len(row)-1
            while end>=0 and row[end][0]==" " and row[end][2] is None: end-=1
            b.append("\x1b[%dH"%(r+1+HUD))
            i=0
            while i<=end:
                g,fg,bg=row[i]
                if fg!=s.fg or bg!=s.bg:
                    # INCREMENTAL SGR.  A naive writer resets and re-emits both
                    # colours on every change, which costs ~16 bytes each time;
                    # since the attribute state carries across cells, only the
                    # half that actually changed needs sending.  This is most of
                    # the byte budget, so it is worth the bookkeeping.
                    seq=[]
                    if s.mode=="rich":
                        if fg!=s.fg:
                            seq.append("\x1b[38;5;%dm"%fg if fg is not None else "\x1b[39m")
                        if bg!=s.bg:
                            seq.append("\x1b[48;5;%dm"%bg if bg is not None else "\x1b[49m")
                    else:
                        if fg!=s.fg:
                            seq.append("\x1b[%dm"%(90+fg-8 if fg>=8 else 30+fg)
                                       if fg is not None else "\x1b[39m")
                        if bg!=s.bg:
                            seq.append("\x1b[%dm"%(40+bg)
                                       if bg is not None else "\x1b[49m")
                    b.append("".join(seq)); s.fg,s.bg=fg,bg
                j=i
                while j<=end and row[j][1]==fg and row[j][2]==bg: j+=1
                b.append("".join(row[k][0] for k in range(i,j)))
                i=j
            # ERASE TO EOL must run with DEFAULT attributes.  An xterm-family
            # terminal fills EL with the CURRENT background colour, so if the
            # row's last run left a coloured background active, every column
            # past the field gets painted that colour: on a terminal wider than
            # 80 the last cell's colour visibly ran to the window edge.  The
            # field is exactly COLS wide, so what lies beyond it must be the
            # terminal's own background.
            if s.fg is not None or s.bg is not None:
                b.append("\x1b[0m"); s.fg=s.bg=None
            b.append("\x1b[K")
            s.prev[r]=row
        b.append("\x1b[%dH"%ROWS)
        s.s("".join(b)); sys.stdout.flush()
        if s.stats: s.report()
    def draw_vt(s, rows, hud):
        s.n=0; s.nw=0
        b=["\x1b[1H"]
        if s.gmode: b.append("\x1b(B"); s.gmode=None
        b.append("\x1b[27m"); s.rev=False
        b.append(hud[:COLS].ljust(COLS))
        for r in range(FH):
            row=rows[r]
            if s.prev[r]==row: continue
            end=len(row)-1
            while end>=0 and row[end][0]==" " and not row[end][1]: end-=1
            b.append("\x1b[%dH"%(r+1+HUD))
            want=any(row[k][0]!=" " or row[k][1] for k in range(end+1))
            if want and s.gmode is None: b.append("\x1b(0"); s.gmode=True
            elif not want and s.gmode: b.append("\x1b(B"); s.gmode=None
            i=0
            while i<=end:
                rev=row[i][1]
                j=i
                while j<=end and row[j][1]==rev: j+=1
                if rev!=s.rev:
                    b.append("\x1b[7m" if rev else "\x1b[27m"); s.rev=rev
                b.append("".join(row[k][0] for k in range(i,j)))
                i=j
            # Same reason as in draw(): EL fills with the CURRENT attribute, and
            # here that attribute is reverse video, which would smear the tail
            # of the line white rather than a colour.  Measured, mono never
            # actually smeared - its rightmost field column is always blank
            # paper - so this is what holds the invariant, not what fixed a
            # symptom.  SGR 7 must be dropped here, not just SGR 0 later.
            b.append("\x1b[27m\x1b[0m\x1b[K"); s.rev=False
            s.prev[r]=row
        if s.gmode: b.append("\x1b(B"); s.gmode=None
        b.append("\x1b[%dH"%ROWS)
        s.s("".join(b)); sys.stdout.flush()
        if s.stats: s.report()
    def report(s):
        sys.stderr.write("frame %dB as counted / %dB on the wire = %.2fs at 9600 baud\n"
                         %(s.n,s.nw,s.nw/960.0))
    def bye(s):
        s.s("\x1b[0m\x1b[27m\x1b(B")
        if s.mode!="vt100": s.s("\x1b[?25h\x1b[?1049l")

def hud(g):
    k=1.0-math.exp(-g.score/TAU)
    med="     "
    if   g.score>=40: med=" PLAT"
    elif g.score>=30: med=" GOLD"
    elif g.score>=20: med=" SLVR"
    elif g.score>=10: med=" BRNZ"
    return (" FLAPPY-OPENCODE %3d BEST %3d%s GAP %4.1f ZONE %4.1f %s%s "
            %(g.score,g.best,med,g.gap,(g.gap-HTOP-HBOT)-APEX,
              "#"*int(18*k),"."*(18-int(18*k))))

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

def report_palette():
    print("material -> nearest palette entry.  dE is CIE76 colour distance "
          "(a hair's breadth is ~2.3, a noticeable mismatch is >10).")
    print("%-10s %-9s %5s %-16s %7s %5s %-16s %7s"
          %("material","hex","256","rgb","dE","16","rgb","dE"))
    for m in MATS:
        if m=="white": continue
        c=RGB[m]
        i256=min(range(256),key=lambda i:dE2(c,PAL256[i]))
        i16=IDX16[m]
        print("%-10s %-9s %5d %-16s %7.1f %5d %-16s %7.1f"
              %(m,HEX[m],i256,str(PAL256[i256]),dE2(c,PAL256[i256])**0.5,
                i16,str(ANSI16[i16]),dE2(c,ANSI16[i16])**0.5))

def main():
    a=sys.argv[1:]
    mode="vt100" if "--vt100" in a else "c16" if "--c16" in a else "rich"
    stats="--stats" in a
    if "--selftest" in a:
        n=next((int(a[i+1]) for i,x in enumerate(a) if x=="--n"), 20)
        sd=next((int(a[i+1]) for i,x in enumerate(a) if x=="--seed"), 1)
        selftest(n,sd); return
    if "--palette" in a: report_palette(); return
    g=Game(next((int(a[i+1]) for i,x in enumerate(a) if x=="--seed"),None))
    sc=Scene()
    if mode=="c16":
        COL,bg_ok,glyphs,quads,idx=(COL16,(lambda c:c in BG16SET),SET_C16,
                                    QUADS_C16,make_mapper(ANSI16))
    else:
        COL,bg_ok,glyphs,quads,idx=(COL256,(lambda c:True),SET_RICH,
                                    QUADS_RICH,make_mapper(PAL256))
    cache={}
    nf=next((int(a[i+1]) for i,x in enumerate(a) if x=="--frames"), 0)
    if nf:
        for f in range(nf):
            for _ in range(60): g.step(FIXED)
            paint(sc,g,0.9*max(0.0,1.0-g.deadT/0.4) if g.dead else 0.0,COL)
            if mode=="vt100":
                rows=vt_frame(sc)
                body=["".join(ch for ch,_ in r) for r in rows]
            else:
                rows=to_indices(render(sc,bg_ok,glyphs,quads,cache),idx)
                body=["".join(ch for ch,_,_ in r) for r in rows]
            print(hud(g)); print("\n".join(body)); print()
        sys.stderr.write("cache entries %d\n" % len(cache))
        return
    t=TTY(mode,stats); t.boot(); acc,last=0.0,time.time()
    try:
        while True:
            now=time.time(); acc=min(0.25,acc+now-last); last=now
            while acc>=FIXED: g.step(FIXED); acc-=FIXED
            paint(sc,g,0.9*max(0.0,1.0-g.deadT/0.4) if g.dead else 0.0,COL)
            if mode=="vt100": t.draw_vt(vt_frame(sc),hud(g))
            else: t.draw(to_indices(render(sc,bg_ok,glyphs,quads,cache),idx),hud(g))
            time.sleep(0.006)
    except KeyboardInterrupt: pass
    finally: t.bye()

if __name__=="__main__": main()
