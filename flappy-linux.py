#!/usr/bin/env python3
"""flappy-linux - self-playing Flappy Bird for an 80x25 terminal.

  python3 flappy-linux.py             Linux console: 16 colours, CP437 blocks
  python3 flappy-linux.py --vt100     strict DEC Special Graphics, mono
  python3 flappy-linux.py --frames 5  print 5 frames (ANSI), no tty
  python3 flappy-linux.py --selftest  headless games -> crash statistics
  --seed N   --stats (bytes/frame, for 9600-baud curiosity)

RENDERING: the scene is painted in RGB on a 160x48 SUB-PIXEL grid (2x2 per
character cell). Each cell is then quantised to the best (glyph, fg, bg)
the Linux console can actually show: 16 foregrounds (bold = bright), 8
backgrounds, and only glyphs in its CP437 font -
   ' ' / '█'          solid bg / solid fg
   '░' '▒' '▓'        fg over bg at 1/4, 1/2, 3/4: ~300 blended colours
   '▀' '▄' '▌' '▐'    two-colour split, vertical or horizontal (pipe edges
                      land on half-columns)
Shade pairs are restricted to related hues so blends read as tone, not
noise. The bird is authored in exact VGA colours on cell-aligned square
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

# ---------- framebuffer + painter (sub-pixel RGB) ----------
# A sub-pixel is half a column by half a row. Character cells are 1:2, so a
# sub-pixel is itself 1:2 (tall): two sub-columns side by side make a square.
def mix(a, b, t):
    return (a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t, a[2]+(b[2]-a[2])*t)

SKY_HI, SKY_LO = (40,110,200), (110,195,195)
CLOUD, CLOUD_SH = (252,252,252), (206,228,238)
FAR, FAR_HI     = (70,185,150), (100,200,170)
BUSH, BUSH_HI, BUSH_LO = (58,170,62), (96,214,80), (30,112,40)
P_OUT, P_HI, P_MID, P_LO = (26,40,18), (120,236,92), (96,192,48), (40,116,26)
G_LINE, GRASS1, GRASS2, GRASS_LO = (40,36,30), (130,220,70), (88,176,44), (52,120,34)
DIRT, DIRT_LO  = (222,212,150), (196,170,104)

SKY_MID = (0,170,170)                            # VGA cyan: solid, so sprites
def skyrow(y):                                   # split cleanly against it
    f=y/float(SKY)
    if f<0.22: return mix(SKY_HI,SKY_MID,f/0.22)
    if f<0.70: return SKY_MID
    return mix(SKY_MID,SKY_LO,min(1.0,(f-0.70)/0.30))
SKYROW = [skyrow(y) for y in range(SH)]

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

def paint(sc, g, flash):
    sc.clear()
    off=g.clock*g.speed*0.07                     # clouds: furthest, slowest
    for i in range(5):
        x=((i*44-off)%(SW+60))-30; y=6+(i*5)%13
        for (dx,dy,rx,ry) in ((0,1,9,3),(8,-1,9,4),(17,1,8,3),(5,2,14,2.5)):
            sc.blob(x+dx,y+dy,rx,ry,CLOUD,shade=CLOUD_SH)
    off=g.clock*g.speed*0.16                     # far ridge: hazy blue-green
    for i in range(8):
        x=((i*26-off)%(SW+52))-26; h=7+(i*5)%6
        sc.blob(x,SKY,16,h,FAR,hi=FAR_HI)
    off=g.clock*g.speed*0.34                     # near bushes: saturated
    for i in range(10):
        x=((i*19-off)%(SW+38))-19; h=4+(i*3)%3
        sc.blob(x,SKY+1,12,h,BUSH,shade=BUSH_LO,hi=BUSH_HI)
    for p in g.pipes:                            # pipes: lit cylinder, dark outline
        x=int(round(p["x"]))
        shaft=[P_OUT]+[pipe_shade(c,PIPE_W-2) for c in range(PIPE_W-2)]+[P_OUT]
        lip=[P_OUT]+[pipe_shade(c,PIPE_W+4) for c in range(PIPE_W+4)]+[P_OUT]
        for y0,y1,top in ((0,p["top"],True),(p["bot"],SKY,False)):
            for y in range(max(0,int(y0)),min(SH,int(y1))):
                r=sc.L[y]
                for c,col in enumerate(shaft):
                    if 0<=x+c<SW: r[x+c]=col
            cap=int(round((y1-5) if top else y0))
            for y in range(cap,cap+5):
                if not 0<=y<SH: continue
                r=sc.L[y]
                for c,col in enumerate(lip):
                    xx=x-3+c
                    if 0<=xx<SW: r[xx]=P_OUT if y in (cap,cap+4) else col
    sc.rect(0,SKY,SW,1,G_LINE)                   # ground: grass band + dirt
    off=int(g.clock*g.speed)
    for y in range(SKY+1,SKY+4):
        r=sc.L[y]
        for x in range(SW):
            r[x]=GRASS1 if ((x+off+2*(y-SKY))%12)<6 else GRASS2
    sc.rect(0,SKY+4,SW,1,GRASS_LO)
    sc.rect(0,SKY+5,SW,SH-SKY-5,DIRT)
    for y in range(SKY+6,SH,2):
        r=sc.L[y]
        for x in range(SW):
            if ((x+off)*7+y*13)%23==0: r[x]=DIRT_LO
    draw_bird(sc,g)
    if flash>0:
        f=min(1.0,flash)
        for y in range(SH):
            sc.L[y]=[mix(c,(255,255,255),f) for c in sc.L[y]]

def pipe_shade(c,w):
    t=c/float(w-1)
    if t<0.10: return P_MID
    if t<0.32: return P_HI
    if t<0.62: return P_MID
    return mix(P_MID,P_LO,min(1.0,(t-0.62)/0.25))

# Bird sprite in SQUARE pixels: one column wide, half a row tall, so each
# character cell holds exactly two of them stacked -> one "\u2580" with fg/bg.
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
BCOL = {"K":0, "Y":11, "O":3, "W":15, "B":0, "R":9, "w":7}
def draw_bird(sc,g):
    col0 = 2*(int(BIRD_X/2)-4)                    # even sub-col: cell aligned
    row0 = int(round(g.y))-3
    ph = g.wing
    wf = 0 if ph>0.55 else 1 if ph>0.15 else 2
    if g.vy < -0.2*FLAP: wf = 0 if ph>0.55 else 1
    rows=[list(r) for r in BIRD]
    for (y,x) in WING[wf]: rows[y][x]="w"
    if wf!=0: rows[2][1]=rows[2][2]="Y"
    for y,r in enumerate(rows):
        for x,ch in enumerate(r):
            if ch==".": continue
            c=VGA[BCOL[ch]]
            sc.put(row0+y,col0+2*x,c); sc.put(row0+y,col0+2*x+1,c)

# ---------- cell quantiser: 2x2 sub-pixels -> (glyph, fg, bg) ----------
# Linux console / VGA: 16 foreground colours (8 + bold) and 8 backgrounds.
# Only glyphs present in the console's CP437 font are used: full/half blocks
# and the three shade characters, which blend fg over bg at 1/4, 1/2, 3/4.
VGA=[(0,0,0),(170,0,0),(0,170,0),(170,85,0),(0,0,170),(170,0,170),(0,170,170),(170,170,170),
     (85,85,85),(255,85,85),(85,255,85),(255,255,85),(85,85,255),(255,85,255),(85,255,255),(255,255,255)]
def _lin(c): return tuple((v/255.0)**2.2 for v in c)
def _srgb(l): return tuple(255.0*(v**(1/2.2)) for v in l)
VLIN=[_lin(c) for c in VGA]
def err(a,b):
    dr,dg,db=a[0]-b[0],a[1]-b[1],a[2]-b[2]
    rm=(a[0]+b[0])*0.5                            # "redmean" perceptual distance
    return (2+rm/256)*dr*dr+4*dg*dg+(2+(255-rm)/256)*db*db

FLAT=[]                                           # (rgb, glyph, fg, bg, texture penalty)
for b in range(8): FLAT.append((VGA[b]," ",None,b,0))
for f in range(16): FLAT.append((VGA[f],"█",f,None,0))
# Shade pairs are limited to fg/bg that belong together (same hue, a grey,
# or neighbouring hues): green-over-red may average right but reads as noise.
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
_flat,_near16,_near8,_cell={}, {}, {}, {}
def best_flat(c):
    c=(int(c[0])&~3,int(c[1])&~3,int(c[2])&~3)
    r=_flat.get(c)
    if r is None:
        r=min(FLAT,key=lambda e: err(e[0],c)+e[4]); _flat[c]=r
    return r
def near(c,n,cache):
    c=(int(c[0])&~3,int(c[1])&~3,int(c[2])&~3)
    r=cache.get(c)
    if r is None: r=min(range(n),key=lambda i: err(VGA[i],c)); cache[c]=r
    return r
def avg(*cs):
    l=[_lin(c) for c in cs]
    return _srgb(tuple(sum(v[k] for v in l)/len(l) for k in range(3)))

UP,DN,LF,RT="▀","▄","▌","▐"
def quantise(a,b,c,d):
    """a b / c d sub-pixels -> (glyph, fg, bg) minimising summed error.
    Root error (not squared) per sub-pixel: one wrong sub-pixel on a crisp
    edge beats four muddy ones, so corners stay sharp instead of going grey."""
    key=(a,b,c,d); r=_cell.get(key)
    if r is not None: return r
    px=(a,b,c,d)
    fl=best_flat(avg(*px)); best=(sum(math.sqrt(err(fl[0],p)+fl[4]) for p in px),fl[1],fl[2],fl[3])
    if not (a==b==c==d):
        for g1,g2,m1,m2 in ((UP,DN,(a,b),(c,d)),(LF,RT,(a,c),(b,d))):
            p1,p2=avg(*m1),avg(*m2)
            for gl,fgc,bgc,fp,bp in ((g1,p1,p2,m1,m2),(g2,p2,p1,m2,m1)):
                f=near(fgc,16,_near16); bk=near(bgc,8,_near8)
                e=(sum(math.sqrt(err(VGA[f],p)) for p in fp)+
                   sum(math.sqrt(err(VGA[bk],p)) for p in bp))
                if e<best[0]: best=(e,gl,f,bk)
    r=best[1:]
    if len(_cell)>300000: _cell.clear()
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
    return k*0.45 if c in SCENERY else k
SCENERY={CLOUD,CLOUD_SH,FAR,FAR_HI,BUSH,BUSH_HI,BUSH_LO}
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
    return (" FLAPPY-LINUX %3d BEST %3d  GAP %4.1f ZONE %3.1f  %s%s "
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
            rows=[(vt_line if vt100 else ansi_line)(cl) for cl in (vt_rows if vt100 else cell_rows)(sc)]
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
