#!/usr/bin/env python3
"""check-opencode - verification harness for flappy-opencode.py.

Every claim the renderer makes is measured here, so a regression shows up as a
failing line rather than as a subtly worse picture.  Exits non-zero on failure.

The strongest test is 4b: the quantiser's choice is compared against an
INDEPENDENTLY written exhaustive search that samples the cell on a 4x4 grid
(the renderer uses a 64-sample decomposition).  Two different implementations
agreeing on the optimum is evidence; a threshold that could be relaxed is not.
"""
import importlib.util, io, sys, re, time, collections

spec=importlib.util.spec_from_file_location("fo","flappy-opencode.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

FAILS=[]
def check(ok, label, detail=""):
    print("  %-4s %s%s" % ("PASS" if ok else "FAIL", label, ("  - "+detail) if detail else ""))
    if not ok: FAILS.append(label)

class Cap(io.StringIO):
    def flush(self): pass

def pipeline(mode):
    if mode=="c16":
        return (m.COL16,(lambda c:c in m.BG16SET),m.SET_C16,m.QUADS_C16,m.make_mapper(m.ANSI16))
    return (m.COL256,(lambda c:True),m.SET_RICH,m.QUADS_RICH,m.make_mapper(m.PAL256))

def emit(mode, frames=20):
    """run the real output path, return the byte stream it would write"""
    COL,bg_ok,glyphs,quads,idx=pipeline(mode)
    g=m.Game(7); sc=m.Scene(); cache={}; t=m.TTY(mode,False)
    old=sys.stdout; sys.stdout=Cap()
    try:
        t.boot()
        for _ in range(frames):
            for _ in range(60): g.step(m.FIXED)
            m.paint(sc,g,0.9*max(0.0,1.0-g.deadT/0.4) if g.dead else 0.0,COL)
            if mode=="vt100": t.draw_vt(m.vt_frame(sc), m.hud(g))
            else: t.draw(m.to_indices(m.render(sc,bg_ok,glyphs,quads,cache),idx), m.hud(g))
        t.bye()
    finally: data=sys.stdout.getvalue(); sys.stdout=old
    return data

print("\n1. PHYSICS GATE - the game must stay the game it is meant to be")
stats=[]
for i in range(20):
    gg=m.Game(1+i*7919)
    for _ in range(int(60*400)):
        gg.step(m.FIXED)
        if gg.dead: stats.append(gg.score); break
check(len(stats)==20, "all 20 seeded games eventually die", "died %d/20" % len(stats))
check(min(stats)>=40, "no game dies before pipe 40", "earliest death score %d" % min(stats))
check(m.SAFE>0, "asymptote remains geometrically possible", "SAFE=%.1f" % m.SAFE)
# thrust/speed/pipe width are the original's and must not move. GAP and the
# hitbox DID move, deliberately and together: an honest hitbox the size of the
# drawn sprite needs more sky, exactly as the reference raised its floor when it
# drew its bird 2x.
for name,val in [("GRAV_F",0.20),("APEX_T",0.30),("PIPE_W",29),("COOLD",0.50),
                 ("GAP0",24.0),("GAP1",20.0),("HW",8.5),("HTOP",5.0),("HBOT",5.0)]:
    check(abs(getattr(m,name)-val)<1e-9, "physics constant %s as intended" % name, str(val))
check(m.HTOP==m.HBOT, "collision clearance is symmetric about the physics centre",
      "HTOP %.1f HBOT %.1f  (the old single HH put all slack above it)"
      % (m.HTOP,m.HBOT))

print("\n1b. COLLISION HONESTY - what the viewer sees must match what kills")
# The bug this gate exists for: the box was 7.8x6.0 inside a 17x10 sprite and
# all its forgiveness sat ABOVE the centre, so the bird visibly entered the
# upper pipe while still alive - measured at 5.7% of live frames, 99.8% upper.
check((m.HW,m.HTOP,m.HBOT)==(m.BIRD_W/2.0,m.BIRD_H/2.0,m.BIRD_H/2.0),
      "hitbox is the drawn sprite, not a smaller box next to it",
      "box %.1fx%.1f vs sprite %dx%d" % (2*m.HW,m.HTOP+m.HBOT,m.BIRD_W,m.BIRD_H))
# every sprite row must be one ink run, or ink_hits_pipe's per-row interval
# would be conservative rather than exact
for pn,pose in (("WING_UP",m.WING_UP),("WING_MID",m.WING_MID),("WING_DOWN",m.WING_DOWN)):
    ok=True
    for r in range(m.BIRD_H):
        rw=list(m.BIRD_BODY[r])
        for (pr,pc,pat) in pose:
            for i,ch in enumerate(pat): rw[pr+i]=ch
        cs=[c for c in range(m.BIRD_W) if rw[c]!="."]
        if cs and cs[-1]-cs[0]+1!=len(cs): ok=False
    check(ok, "%s: every row is one contiguous ink run (per-row test is exact)" % pn)
# the real oracle: rasterise, then intersect the drawn bird's pixels with the
# drawn pipe's pixels.  Any hit is a frame where the picture contradicts the
# physics, which is the entire complaint this fix answers.
# pipe materials DERIVED from the band lists, never typed.  And the bird's set
# needs no list at all: draw_bird is the only caller of Scene.put, so whatever
# put() is handed IS bird ink.  That matters - a hand-typed bird list left out
# the outline material "ink", which is 2/3 of the sprite's painted pixels, and
# undercounted the overlap this gate exists to catch.
PIPEMAT={mn for _o,_w,mn in list(m.SHAFT)+list(m.LIP)}
S={"pipe":set(),"bird":set()}
_orig_rect,_orig_put=m.Scene.rect,m.Scene.put
def _hook_rect(s,x,y,w,h,c,mtr):
    if mtr in PIPEMAT:
        for yy in range(int(y),int(y+h)):
            if 0<=yy<m.SH:
                for xx in range(max(0,int(x)),min(m.SW,int(x+w))): S["pipe"].add((xx,yy))
    return _orig_rect(s,x,y,w,h,c,mtr)
def _hook_put(s,y,x,c,mtr):
    if 0<=y<m.SH and 0<=x<m.SW: S["bird"].add((x,y))
    return _orig_put(s,y,x,c,mtr)
m.Scene.rect,m.Scene.put=_hook_rect,_hook_put
tot=ov=up=0
worst=0; where=None
for seed in range(1,7):
    g=m.Game(seed); sc=m.Scene()
    for _ in range(int(60*150)):
        g.step(m.FIXED)
        if g.dead: break
        S["pipe"].clear(); S["bird"].clear()
        m.paint(sc,g,0.0,m.COL256)
        tot+=1
        hit=S["bird"]&S["pipe"]
        if not hit: continue
        ov+=1
        if sum(y for _,y in hit)/len(hit)<m.SKY/2: up+=1
        if len(hit)>worst:
            worst=len(hit)
            ys=sorted(y for _,y in hit); xs=sorted(x for x,_ in hit)
            where="x %d..%d y %d..%d" % (xs[0],xs[-1],ys[0],ys[-1])
m.Scene.rect,m.Scene.put=_orig_rect,_orig_put
check(ov==0, "no live frame paints bird ink over pipe ink",
      "%d/%d frames overlap (%d upper), worst %d px at %s" % (ov,tot,up,worst,where))
check(ov==0 and up==0, "upper pipe in particular stays clear", "%d upper-pipe frames" % up)

# the mirror: a hitbox BIGGER than the art kills at a distance, which is the
# same complaint reversed.  Every death must show contact in the painted scene.
# The ground is allowed edge contact rather than a shared pixel: its band starts
# at SKY and the sprite's last ink row is round(y)+BIRD_H/2-1, so a legal ground
# death lands the bottom edge on the grass line with no row in common.
GROUNDMAT={"grass","grassDark"}
S2={"pipe":set(),"ground":set(),"bird":set()}
def _hook_rect2(s,x,y,w,h,c,mtr):
    bk="pipe" if mtr in PIPEMAT else ("ground" if mtr in GROUNDMAT else None)
    if bk:
        for yy in range(int(y),int(y+h)):
            if 0<=yy<m.SH:
                for xx in range(max(0,int(x)),min(m.SW,int(x+w))): S2[bk].add((xx,yy))
    return _orig_rect(s,x,y,w,h,c,mtr)
def _hook_put2(s,y,x,c,mtr):
    if 0<=y<m.SH and 0<=x<m.SW: S2["bird"].add((x,y))
    return _orig_put(s,y,x,c,mtr)
m.Scene.rect,m.Scene.put=_hook_rect2,_hook_put2
dth=pix=edge=phantom=0; pnote=None
for seed in range(1,21):
    g=m.Game(seed); sc=m.Scene()
    for _ in range(int(60*400)):
        g.step(m.FIXED)
        if not g.dead: continue
        dth+=1
        S2["pipe"].clear(); S2["ground"].clear(); S2["bird"].clear()
        m.paint(sc,g,0.0,m.COL256)
        b=S2["bird"]; gt=min(y for _,y in S2["ground"])
        if b&S2["pipe"]: pix+=1
        elif b and (b&S2["ground"] or max(y for _,y in b)+1==gt): edge+=1
        else:
            phantom+=1
            pnote="seed %d y=%.2f ink rows %d..%d vs grass top %d"%(
                seed,g.y,min(y for _,y in b),max(y for _,y in b),gt)
        break
m.Scene.rect,m.Scene.put=_orig_rect,_orig_put
check(dth==20, "20 seeded deaths captured for the contact test", "%d deaths" % dth)
check(phantom==0, "no death happens without visible contact (no kill at a distance)",
      "%d phantom: %s" % (phantom,pnote) if phantom else
      "%d share a pixel with a pipe, %d rest on the ground" % (pix,edge))

print("\n2. GLYPH LEGALITY - each mode may only emit glyphs its terminal has")
CP437_OK=set(" \u2588\u2580\u2584\u258c\u2590\u2591\u2592\u2593")
data=emit("c16")
nonascii=[c for c in set(data) if ord(c)>127]
bad=[c for c in nonascii if c not in CP437_OK]
check(not bad, "--c16 emits only glyphs the Linux console's CP437 font has",
      "illegal: %s" % "".join(bad) if bad else "%d distinct, all in the font" % len(nonascii))
bright=[int(x) for x in re.findall(r'\x1b\[(?:1[01][0-7])m', data)]
check(not bright, "--c16 never sets a bright background (40..47 only)",
      "found 10x codes" if bright else "console_codes(4) shoehorns 48;5;n into 8")
data=emit("vt100")
check(not [c for c in set(data) if ord(c)>127], "--vt100 is 7-bit clean")
# inspect the FIELD itself, not the byte stream: escape-sequence bytes are not glyphs
g=m.Game(7); sc=m.Scene()
field=set()
for _ in range(20):
    for _ in range(60): g.step(m.FIXED)
    m.paint(sc,g,0.0,m.COL256)
    for row in m.vt_frame(sc):
        for ch,_rev in row: field.add(ch)
DEC=set(" `a~q.abcdefghjklmnoprstuvwxyz}{|")     # the real DEC Special Graphics codes
bad=[c for c in field if c not in DEC]
check(not bad, "--vt100 field glyphs all exist in DEC Special Graphics",
      "outside the set: %r" % bad if bad else "uses %s" % "".join(sorted(field)))
esc=set(re.findall(r'\x1b\[[0-9;?]*[A-Za-z]|\x1b\(.', data))
extra=[e.replace("\x1b","ESC") for e in esc
       if e not in ("\x1b[2J","\x1b[0m","\x1b[7m","\x1b[27m","\x1b(0","\x1b(B","\x1b[K")
       and not re.fullmatch(r'\x1b\[[0-9;]*H', e)]
check(not extra, "--vt100 uses only VT100-native escapes", "extras: %s" % extra)

print("\n3. SCREEN GEOMETRY - 80x25, no resize, no graphics protocols")
for mode in ("rich","c16","vt100"):
    data=emit(mode, frames=3)
    check("\x1b[8;" not in data and "\x1bP" not in data and "\x1b]" not in data,
          "--%s never resizes the window or uses Sixel/ReGIS" % mode)
    check(("\x1b[?1049h" in data) == (mode!="vt100"),
          "--%s alt-screen only where the terminal supports it" % mode)
check(m.COLS==80 and m.ROWS==25, "field is 80x25", "%dx%d" % (m.COLS,m.ROWS))

print("\n4a. COLOUR FIDELITY - rendered vs the palette's own floor")
def rendered(g,fg,bg,pal):
    fgc=pal[fg] if fg is not None else None
    bgc=pal[bg] if bg is not None else None
    if g in m.SHADE:
        t=m.SHADE[g]
        return [m._mix(fgc,bgc,t)]*4 if (fgc and bgc) else [fgc or bgc]*4
    q=m.QUADCOUNT.get(g)
    if q is None: return [None]*4
    out=[]
    for quad in range(4):
        n=q[quad]
        if n==16: out.append(fgc)
        elif n==0: out.append(bgc)
        elif fgc and bgc: out.append(m._mix(fgc,bgc,n/16.0))
        else: out.append(fgc or bgc)
    return out
for mode in ("rich","c16"):
    COL,bg_ok,glyphs,quads,idx=pipeline(mode)
    pal=m.ANSI16 if mode=="c16" else m.PAL256
    g=m.Game(7); sc=m.Scene(); cache={}
    for _ in range(20):
        for _ in range(60): g.step(m.FIXED)
        m.paint(sc,g,0.0,COL)
        rows=m.to_indices(m.render(sc,bg_ok,glyphs,quads,cache),idx)
    acc=collections.defaultdict(lambda:[0.0,0,0.0])
    for r in range(m.FH):
        for c in range(m.COLS):
            gr,fg,bg=rows[r][c]
            got=rendered(gr,fg,bg,pal)
            for k in range(4):
                mat=sc.M[r*2+k//2][c*2+k%2]; gotc=got[k]
                if gotc is None or mat not in m.RGB: continue
                acc[mat][0]+=m.dE2(m.RGB[mat],gotc)**0.5; acc[mat][1]+=1
                acc[mat][2]=min(m.dE2(m.RGB[mat],pal[i])**0.5 for i in range(len(pal)))
    rm=[];fm=[]
    for mat in m.MATS:
        if mat=="white" or mat not in acc: continue
        e,cnt,fl=acc[mat]; rm.append(e/cnt); fm.append(fl)
    mean_r=sum(rm)/len(rm); mean_f=sum(fm)/len(fm)
    check(mean_r-mean_f < 3.0, "--%s adds < 3 dE on top of the palette's own error" % mode,
          "rendered %.1f vs floor %.1f" % (mean_r, mean_f))

print("\n4b. OPTIMALITY - quantise() vs an independent exhaustive search")
# The coverage geometry here is hand-written from the Unicode names as explicit
# rectangles in eighths of a cell.  It deliberately does NOT read MASK,
# QUADCOUNT or any GLYPHS predicate from flappy-opencode.py: if the renderer's
# mask table were wrong in a way that made a bad glyph look good, this search
# would disagree with it and the check would fail.
#   (top, bottom, left, right) in eighths; fg covers that rectangle.
GEO={
 " ":    None,
 "\u2588": (0,8,0,8),
 "\u2580": (0,4,0,8),   # UPPER half block
 "\u2584": (4,8,0,8),   # LOWER half block
 "\u258c": (0,8,0,4),   # LEFT half block
 "\u2590": (0,8,4,8),   # RIGHT half block
 "\u2598": (0,4,0,4),   # QUADRANT UPPER LEFT
 "\u259d": (0,4,4,8),   # QUADRANT UPPER RIGHT
 "\u2596": (4,8,0,4),   # QUADRANT LOWER LEFT
 "\u2597": (4,8,4,8),   # QUADRANT LOWER RIGHT
 "\u2599": None,        # unions, spelled out below
 "\u259f": None, "\u259b": None, "\u259c": None, "\u259a": None, "\u259e": None,
}
GEO["\u2599"]=[(0,4,0,4),(4,8,0,8)]          # UL + LL + LR
GEO["\u259f"]=[(0,4,4,8),(4,8,0,8)]          # UR + LL + LR
GEO["\u259b"]=[(0,8,0,4),(0,4,4,8)]          # UL + UR + LL
GEO["\u259c"]=[(0,4,0,4),(0,4,4,8),(4,8,4,8)]   # UL + UR + LR
GEO["\u259a"]=[(0,4,0,4),(4,8,4,8)]          # UL + LR (diagonal)
GEO["\u259e"]=[(0,4,4,8),(4,8,0,4)]          # UR + LL (diagonal)
def geo_cover(gl, py, px):
    """fg coverage at fine sample (py,px) of a 4x4 grid, from GEO only"""
    if gl in m.SHADE: return m.SHADE[gl]
    parts=GEO[gl]
    if parts is None: return 0.0
    if isinstance(parts, tuple): parts=[parts]
    y0,y1=py*2,py*2+2; x0,x1=px*2,px*2+2      # this sample spans 2x2 eighths
    area=0
    for (t,b,l,r) in parts:
        ay=max(0,min(b,y1)-max(t,y0)); ax=max(0,min(r,x1)-max(l,x0))
        area+=ay*ax
    return min(1.0, area/4.0)

def brute(cell, bg_ok, allowed_glyphs):
    cols=[]
    for c in cell:
        if c not in cols: cols.append(c)
    best=None
    for gl in allowed_glyphs:
        shade=gl in m.SHADE
        for fg in cols:
            for bg in cols:
                if gl not in (" ","\u2588") and fg==bg: continue
                if gl!=" " and not bg_ok(bg) and gl!="\u2588" and fg==bg: continue
                if gl==" " and not bg_ok(bg): continue
                if gl=="\u2588": fg,bg=cols[0],None
                elif gl==" ": fg,bg=None,cols[0]
                e=0.0
                for py in range(4):
                    for px in range(4):
                        tgt=cell[(py//2)*2+(px//2)]
                        cov=geo_cover(gl,py,px)
                        if gl==" ": got=bg
                        elif gl=="\u2588": got=fg
                        elif cov>=1.0: got=fg
                        elif cov<=0.0: got=bg
                        else: got=m._mix(fg,bg,cov)
                        e+=m.dE2(got,tgt)
                e/=16.0
                if best is None or e<best[0]: best=(e,gl,fg,bg)
    return best
worse=0; tested=0; cells=set()
for mode in ("rich","c16"):
    COL,bg_ok,glyphs,quads,idx=pipeline(mode)
    g=m.Game(13); sc=m.Scene(); cache={}
    for _ in range(6):
        for _ in range(60): g.step(m.FIXED)
        m.paint(sc,g,0.0,COL)
        for r in range(0,m.FH,3):
            for c in range(0,m.COLS,5):
                cell=(sc.C[r*2][c*2],sc.C[r*2][c*2+1],sc.C[r*2+1][c*2],sc.C[r*2+1][c*2+1])
                if cell in cells: continue
                cells.add(cell)
                _g,_fg,_bg,e=m.quantise(cell,bg_ok,glyphs,quads,cache)
                bb=brute(cell,bg_ok,glyphs)
                tested+=1
                if bb is not None and bb[0] < e - 1e-6:
                    worse+=1
                    if worse<=3:
                        print("     renderer err %.1f  independent optimum %.1f  (%s) renderer chose %r"
                              % (e,bb[0],mode,_g))
check(worse==0, "quantise() is never beaten by an independently derived search",
      "%d cells cross-checked, %d losses" % (tested,worse))

print("\n4c. WHAT THE 16-COLOUR CONSOLE COSTS - reported, not hidden")
COL,bg_ok,glyphs,quads,idx=pipeline("c16")
g=m.Game(7); sc=m.Scene(); cache={}
exact=0; forced=0; err=0.0
for _ in range(20):
    for _ in range(60): g.step(m.FIXED)
    m.paint(sc,g,0.0,COL)
    for r in range(m.FH):
        for c in range(m.COLS):
            cell=(sc.C[r*2][c*2],sc.C[r*2][c*2+1],sc.C[r*2+1][c*2],sc.C[r*2+1][c*2+1])
            if len(set(cell))<2: continue
            _g,_f,_b,e=m.quantise(cell,bg_ok,glyphs,quads,cache)
            if e==0.0: exact+=1
            else: forced+=1; err+=e**0.5
check(exact/(exact+forced) > 0.7, "--c16 renders most two-colour cells EXACTLY",
      "%d exact / %d total, the other %d approximated at mean dE %.1f because CP437 lacks 10 quadrant glyphs"
      % (exact,exact+forced,forced,err/max(1,forced)))

print("\n5. THE TWO-COLOUR CAPABILITY - the whole point of this renderer")
COL,bg_ok,glyphs,quads,idx=pipeline("rich")
g=m.Game(29); sc=m.Scene(); cache={}
for _ in range(600): g.step(m.FIXED)
m.paint(sc,g,0.0,COL)
rows=m.to_indices(m.render(sc,bg_ok,glyphs,quads,cache),idx)
tot=m.COLS*m.FH
both=sum(1 for r in rows for gr,fg,bg in r if fg is not None and bg is not None and fg!=bg)
check(both/tot > 0.10, "cells genuinely carry two colours", "%d/%d cells = %.0f%%" % (both,tot,100*both/tot))
ncol=len({c for r in rows for _,f,b in r for c in (f,b) if c is not None})
check(ncol >= 12, "more than a dozen distinct colours on one screen", "%d colours" % ncol)

print("\n6. BIRD PROPORTIONS - size was the original's real defect")
cols=[c for r in m.BIRD_BODY for c,ch in enumerate(r) if ch!='.']
w=max(cols)-min(cols)+1
check(w/m.PIPE_W > 0.50, "bird is a fair fraction of the pipe shaft",
      "%d/%d = %.2f (original 34/52 = 0.65; flappy-vt100 drew 0.28)" % (w,m.PIPE_W,w/m.PIPE_W))
def maxrun(ch, horiz):
    lines=m.BIRD_BODY if horiz else ["".join(m.BIRD_BODY[r][c] for r in range(m.BIRD_H))
                                     for c in range(m.BIRD_W)]
    best=0
    for line in lines:
        cur=0
        for x in line:
            cur=cur+1 if x==ch else 0
            best=max(best,cur)
    return best
for ch,what in (("P","pupil"),("R","beak"),("W","eye")):
    check(maxrun(ch,False)>=2 and maxrun(ch,True)>=2,
          "%s is >=2 sub-px in both axes (a 1-px feature cannot survive a 2-colour cell)" % what,
          "%dx%d" % (maxrun(ch,True), maxrun(ch,False)))

print("\n7. FRAME BUDGET")
for mode in ("rich","c16","vt100"):
    COL,bg_ok,glyphs,quads,idx=pipeline(mode)
    g=m.Game(7); sc=m.Scene(); cache={}; times=[]
    for _ in range(60):
        for _ in range(60): g.step(m.FIXED)
        m.paint(sc,g,0.0,COL)
        t0=time.time()
        if mode=="vt100": m.vt_frame(sc)
        else: m.to_indices(m.render(sc,bg_ok,glyphs,quads,cache),idx)
        times.append(time.time()-t0)
    times.sort()
    check(times[len(times)//2] < m.FIXED, "--%s builds a frame well under 16.7 ms" % mode,
          "median %.1f ms" % (1000*times[len(times)//2]))

print("\n8. NO DEAD WEIGHT, AND NO GAPS")
# A glyph is justified if it is chosen by SOME mode, or if it is part of the
# complete 16-pattern quadrant set: that completeness is what lets ANY two-
# colour cell be drawn with zero error, so an unused pattern is still load-bearing.
used_by_mode={}
for mode in ("rich","c16"):
    COL,bg_ok,glyphs,quads,idx=pipeline(mode)
    hist=collections.Counter(); g=m.Game(3); sc=m.Scene(); cache={}
    for _ in range(40):
        for _ in range(60): g.step(m.FIXED)
        m.paint(sc,g,0.9*max(0.0,1.0-g.deadT/0.4) if g.dead else 0.0,COL)
        rr=m.render(sc,bg_ok,glyphs,quads,cache)
        for r in range(m.FH):
            for c in range(m.COLS): hist[rr[r][c][0]]+=1
    used_by_mode[mode]=set(hist)
used=set().union(*used_by_mode.values())
offered=set(m.SET_RICH)|set(m.SET_C16)
quad=set("\u2588 ")|set(m.QUADS_RICH.values())
dead=sorted(offered-used-quad)
check(not dead, "no offered glyph is dead weight in every mode (quadrant completeness excepted)",
      "never chosen anywhere: %s" % "".join(dead) if dead else "all %d offered glyphs earn their place" % len(offered))
check(len(m.QUADS_RICH)==16, "the quadrant set is COMPLETE, so any two-colour cell is exact",
      "%d of 16 patterns" % len(m.QUADS_RICH))
check(len(m.QUADS_C16)==6, "--c16's fast path is filtered to the 6 patterns CP437 has",
      "%d patterns" % len(m.QUADS_C16))
# the eighth-blocks were removed because they can never win; assert they are gone
import unicodedata as _ud
banned=[gl for gl in offered if "EIGHTH" in _ud.name(gl)]
check(not banned, "eighth-blocks absent (0 wins over 76,800 cells - dead weight)",
      "present: %s" % "".join(banned) if banned else "0 eighth-blocks offered")

print("9. THE TWO BUGS FROM THE SCREENSHOT")
print("   9a. pipe lip: its bands must tile its full width, symmetrically")
def tiles(bands):
    off=0
    for ox,bw,_ in bands:
        if ox!=off: return None
        off+=bw
    return off
shaft_w=tiles(m.SHAFT); lip_w=tiles(m.LIP)
check(shaft_w==m.PIPE_W, "shaft bands tile PIPE_W exactly", "%d sub-cols" % shaft_w)
check(lip_w==m.CAP_W, "lip bands tile CAP_W exactly (no unfilled right edge)",
      "bands cover %d, CAP_W is %d" % (lip_w,m.CAP_W))
check(m.CAP_W==m.PIPE_W+2*m.CAP_X, "lip width is the shaft plus both overhangs",
      "%d = %d + 2*%d" % (m.CAP_W,m.PIPE_W,m.CAP_X))
def wid(bands,i): return bands[i][1]
check(wid(m.LIP,1)-wid(m.SHAFT,1)==m.CAP_X, "left overhang continues the catch-light",
      "%d -> %d" % (wid(m.SHAFT,1),wid(m.LIP,1)))
check(wid(m.LIP,-2)-wid(m.SHAFT,-2)==m.CAP_X, "right overhang continues the shadow",
      "%d -> %d" % (wid(m.SHAFT,-2),wid(m.LIP,-2)))
g=m.Game(29); sc=m.Scene()
for _ in range(300): g.step(m.FIXED)
m.paint(sc,g,0.0,m.COL256)
p0=min(g.pipes,key=lambda q:q["x"]); x=int(round(p0["x"])); lip=int(p0["top"])-m.CAP_H
filled=sum(1 for c in range(x-m.CAP_X, x-m.CAP_X+m.CAP_W)
           if sc.M[lip+1][c] not in (None,"skyA","skyB","skyC","skyD","cloud"))
check(filled==m.CAP_W, "every sub-column of a lip row is body fill, wall to wall",
      "%d of %d filled" % (filled,m.CAP_W))

print("   9b. a terminal WIDER than 80 columns must show the terminal's own")
print("       background past the field, not the last cell's colour.")
try:
    import pyte
    have=True
except ImportError:
    have=False
check(have, "pyte available (a real terminal emulator to check against)")
if have:
    W=100
    def beyond(mode, apply_fix=True):
        COL,bg_ok,glyphs,quads,idx=pipeline(mode)
        g=m.Game(29); sc=m.Scene(); cache={}; t=m.TTY(mode,False)
        scr=pyte.Screen(W,m.ROWS); stream=pyte.Stream(scr)
        oldr=sys.stdout
        for _ in range(12):
            for _ in range(60): g.step(m.FIXED)
            m.paint(sc,g,0.9 if g.dead else 0.0,COL)
            scr.reset()
            buf=io.StringIO(); sys.stdout=buf
            try:
                if mode=="vt100": t.draw_vt(m.vt_frame(sc), m.hud(g))
                else: t.draw(m.to_indices(m.render(sc,bg_ok,glyphs,quads,cache),idx), m.hud(g))
            finally:
                data=buf.getvalue(); sys.stdout=oldr
            if not apply_fix:
                # Revert the fix in the stream, to prove this check actually
                # bites.  Each mode emits its own tail sequence, so the revert
                # has to match both: colour rows end "0m EL", mono rows end
                # "27m 0m EL" (SGR 7 carries the tone, so it must go too).
                data=data.replace("\x1b[27m\x1b[0m\x1b[K","\x1b[K")
                data=data.replace("\x1b[0m\x1b[K","\x1b[K")
            stream.feed(data)
        dirty=0
        for r in range(m.ROWS):
            for c in range(m.COLS,W):
                cell=scr.buffer[r][c]
                if isinstance(cell,str): continue
                # fg/bg AND reverse all count: --vt100 paints with SGR 7, and EL
                # under reverse video fills the tail with reversed cells, which
                # on a real terminal is a white band, not black.
                if cell.fg!="default" or cell.bg!="default" or cell.reverse: dirty+=1
        return dirty
    for mode in ("rich","c16","vt100"):
        fixed=beyond(mode); broken=beyond(mode, apply_fix=False)
        note = ("clean; the same run with EL unqualified smears %d cells" % broken) if broken \
               else "clean; mono's right edge is always blank paper so it never smeared, " \
                     "the reset is kept anyway to hold the invariant"
        check(fixed==0, "--%s leaves 0 attributed cells past column 79" % mode, note)

print()
if FAILS:
    print("%d CHECK(S) FAILED: %s" % (len(FAILS), "; ".join(FAILS))); sys.exit(1)
print("all checks passed")
