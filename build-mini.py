"""build-mini: turn flappy-opencode.py into a byte-lean twin.

A deterministic source-level transform, not a hand rewrite. Every table that
gets compacted is READ from the original module at build time, so no value can
be mistyped. The result is gated two ways: check-opencode.py (50 checks) and
equiv.py (byte-identical terminal output vs the original, all three modes).
"""
import ast, sys, importlib.util

SRC = "flappy-opencode.py"

# The names check-opencode.py drives off the module. Renaming or removing any of
# them would break the harness, so they are the protected API surface.
PUBLIC = ("ANSI16 BG16SET BIRD_BODY BIRD_H BIRD_W CAP_H CAP_W CAP_X COL16 COL256 "
          "COLS dE2 FH FIXED Game hud LIP make_mapper MATS _mix paint PAL256 "
          "PIPE_W QUADCOUNT QUADS_C16 QUADS_RICH quantise render RGB ROWS SAFE "
          "Scene SHADE SHAFT to_indices TTY vt_frame GRAV_F APEX_T GAP0 GAP1 "
          "HW HTOP HBOT COOLD SET_C16 SET_RICH MONO_INK VT_LADDER BAYER4 "
          "WING_UP WING_MID WING_DOWN "
          # the collision-honesty gate rasterises the scene, so it needs the
          # field's own extents, not just the sprite's
          "SW SH SKY").split()


def load_orig():
    spec = importlib.util.spec_from_file_location("orig", SRC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ---------- 1: strip docstrings (behaviour-neutral) -------------------------
def strip(src):
    t = ast.parse(src)
    for n in ast.walk(t):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            b = n.body
            if (b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant)
                    and isinstance(b[0].value.value, str)):
                n.body = b[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(t))


# ---------- 2: the 16 quadrant glyphs are a 4-bit code, not 16 lambdas ------
# The original rasterises each glyph's lambda over an 8x8 grid, counts the
# sub-pixels per quadrant, and inverts that to get QUAD. That round-trips to one
# character per code, so the whole glyph-geometry subsystem is one 16-char string.
def collapse_glyphs(src, orig):
    qg = "".join(orig.QUAD[b] for b in range(16))
    assert len(qg) == 16 and len(set(qg)) == 16
    for b, g in orig.QUAD.items():
        assert orig.QUADCOUNT[g] == tuple(16 * (b >> (3 - i) & 1) for i in range(4)), g
    sh = list(orig.SHADE.items())
    # quantise() breaks error ties by iteration order, so the glyph sets must
    # keep the original's exact order, not the code order.
    srich = "".join(orig.SET_RICH)
    sc16 = "".join(orig.SET_C16)
    cp = "".join(orig.CP437)
    assert set(srich) == set(qg) | {g for g, _ in sh} and len(srich) == len(set(srich))
    assert sc16 == cp + "".join(g for g, _ in sh)
    block = (
        'QG=%r\n'
        'SHADE={%s}\n'
        'QUADCOUNT={g:tuple(16*(b>>(3-i)&1)for i in range(4))for b,g in enumerate(QG)}\n'
        'QUADCOUNT.update({g:(0,0,0,0)for g in SHADE})\n'
        'COVERAGE=set(QG)\n'
        'QUADS_RICH={b:g for b,g in enumerate(QG)}\n'
        'CP437=%r\n'
        'SET_RICH=%r\n'
        'SET_C16=%r\n'
        'QUADS_C16={b:QG[b]for b in %r}\n'
        % (qg,
           ",".join("%r:%s" % (g, repr(t)) for g, t in sh),
           cp,
           srich,
           sc16,
           sorted(b for b, g in orig.QUAD.items() if g in orig.CP437))
    )
    a = src.index("N = 8")
    b = src.index("def _mix")
    return src[:a] + block + "\n" + src[b:]


# ---------- 3: hex colours as one positional table --------------------------
def apply_flat_hex(src, orig):
    names = list(orig.HEX)
    vals = [orig.HEX[k][1:] for k in names]
    assert all(len(v) == 6 for v in vals)
    t = ast.parse(src)
    for i, n in enumerate(t.body):
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) \
                and n.targets[0].id == "HEX":
            t.body.insert(i, ast.parse('V="%s"' % "".join(vals)).body[0])
            n.value = ast.parse('{k:"#"+V[6*i:6*i+6]for i,k in enumerate(%r)}'
                                % (tuple(names),)).body[0].value
            break
    return ast.unparse(ast.fix_missing_locations(t))


# ---------- 4: mono ink levels, hundredths, positional ----------------------
def apply_flat_ink(src, orig):
    names = [m for m in orig.MATS if m in orig.MONO_INK]
    assert names == list(orig.MATS), "MONO_INK order differs from MATS"
    vals = [int(round(orig.MONO_INK[m] * 100)) for m in names]
    assert all(abs(orig.MONO_INK[m] - v / 100.0) < 1e-9 for m, v in zip(names, vals))
    repl = 'MONO_INK={m:int(v)/100.0 for m,v in zip(MATS,"%s".split())}' % " ".join(str(v) for v in vals)
    t = ast.parse(src)
    for i, n in enumerate(t.body):
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) \
                and n.targets[0].id == "MONO_INK":
            t.body[i] = ast.parse(repl).body[0]
            break
    return ast.unparse(ast.fix_missing_locations(t))


# ---------- 5: shorten instance attributes the harness never touches --------
KEEP = {"dead", "deadT", "score", "best", "pipes", "rng", "step", "reset", "die",
        "key", "spawn", "ramp", "want", "zlo", "flap", "C", "M", "rect", "put",
        "clear", "boot", "draw", "draw_vt", "bye", "report", "mode", "stats",
        "__init__", "__main__", "__name__", "x", "top", "bot", "pass"}
ATTR = {"cool": "c", "since": "t", "aim": "ai", "wing": "wg", "speed": "sp",
        "gap": "gp", "space": "spc", "flaps": "fl", "clock": "cl",
        "prev": "pv", "gmode": "gm", "fg": "F", "bg": "Bg", "rev": "rv", "nw": "NW"}


def rename_attrs(src):
    t = ast.parse(src)
    keys = set()
    for n in ast.walk(t):
        if isinstance(n, ast.Dict):
            for k in n.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.add(k.value)
    at = {k: v for k, v in ATTR.items() if k not in keys and k not in KEEP}

    class R(ast.NodeTransformer):
        def visit_Attribute(self, n):
            self.generic_visit(n)
            if n.attr in at:
                n.attr = at[n.attr]
            return n
    R().visit(t)
    return ast.unparse(ast.fix_missing_locations(t))


# ---------- 6: drop the build-time self-checks ------------------------------
# These asserts re-verify tables this builder just derived from the original
# module, and check-opencode.py re-checks every one independently (sprite
# geometry, band tiling, quadrant completeness, physics constants).
def drop_asserts(src):
    t = ast.parse(src)

    class R(ast.NodeTransformer):
        def visit_Assert(self, n):
            return None
    R().visit(t)
    return ast.unparse(ast.fix_missing_locations(t))


# ---------- 7: remove top-level names nothing references --------------------
# Only names outside PUBLIC may go, and only when nothing loads them -- so a
# false positive would be a NameError, not a silently different picture.
def drop_dead(src):
    for _ in range(8):
        t = ast.parse(src)
        names = []
        for n in t.body:
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
                names.append((n.name, n))
            elif isinstance(n, ast.Assign):
                for tg in n.targets:
                    if isinstance(tg, ast.Name):
                        names.append((tg.id, n))
        used = set()
        for n in ast.walk(t):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                used.add(n.id)
            elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
                used.add(n.value.id)
        doomed = {id(node) for nm, node in names if nm not in PUBLIC and nm not in used}
        if not doomed:
            break
        t.body = [n for n in t.body if id(n) not in doomed]
        src = ast.unparse(ast.fix_missing_locations(t))
    return src


# ---------- 7b: methods nothing calls --------------------------------------
# Same rule as drop_dead, one level down: a method is removed only when no
# attribute lookup anywhere in the module names it.  Game.key() is a manual-
# flap hook the self-playing pilot never uses.
def drop_dead_methods(src):
    for _ in range(6):
        t = ast.parse(src)
        used = {n.attr for n in ast.walk(t) if isinstance(n, ast.Attribute)}
        doomed = []
        for n in ast.walk(t):
            if isinstance(n, ast.ClassDef):
                for f in n.body:
                    if isinstance(f, ast.FunctionDef) and f.name not in used \
                            and not f.name.startswith("__") and f.name not in PUBLIC:
                        doomed.append((n, f))
        if not doomed:
            break
        for cls, f in doomed:
            cls.body = [x for x in cls.body if x is not f]
        src = ast.unparse(ast.fix_missing_locations(t))
    return src


# ---------- 8: one draw path instead of two --------------------------------
# draw() and draw_vt() are the same spine -- reset, HUD line, skip unchanged
# rows, trim the tail, seek, emit runs of equal attributes, EL, remember the
# row -- differing only in how a cell's attributes are keyed and written.
# Merging them keeps one copy of the spine; the byte-identical-output gate is
# what proves the merge did not alter a single emitted byte.
MERGED_DRAW = '''
def draw(s,rows,hud):
 s.n=0;s.NW=0
 mo=s.mode=='vt100';ri=s.mode=='rich'
 b=['\\x1b[1H']
 if s.gm:b.append('\\x1b(B');s.gm=None
 b.append('\\x1b[27m' if mo else '\\x1b[0m')
 s.F=s.Bg=None;s.rv=False
 b.append(hud[:COLS].ljust(COLS))
 for r in range(FH):
  row=rows[r]
  if s.pv[r]==row:continue
  end=len(row)-1
  while end>=0 and row[end][0]==' ' and (not row[end][1] if mo else row[end][2] is None):end-=1
  b.append('\\x1b[%%dH'%%(r+1+HUD))
  if mo:
   w=any(row[q][0]!=' ' or row[q][1] for q in range(end+1))
   if w and s.gm is None:b.append('\\x1b(0');s.gm=True
   elif not w and s.gm:b.append('\\x1b(B');s.gm=None
  i=0
  while i<=end:
   a=row[i][1] if mo else (row[i][1],row[i][2])
   if mo:
    if a!=s.rv:b.append('\\x1b[7m' if a else '\\x1b[27m');s.rv=a
   elif a!=(s.F,s.Bg):
    u,v=a
    if u!=s.F:
     if ri:b.append('\\x1b[38;5;%%dm'%%u if u is not None else '\\x1b[39m')
     else:b.append('\\x1b[%%dm'%%(90+u-8 if u>=8 else 30+u) if u is not None else '\\x1b[39m')
    if v!=s.Bg:
     if ri:b.append('\\x1b[48;5;%%dm'%%v if v is not None else '\\x1b[49m')
     else:b.append('\\x1b[%%dm'%%(40+v) if v is not None else '\\x1b[49m')
    s.F,s.Bg=u,v
   j=i
   while j<=end and (row[j][1] if mo else (row[j][1],row[j][2]))==a:j+=1
   b.append(''.join(row[q][0] for q in range(i,j)))
   i=j
  if mo:b.append('\\x1b[27m\\x1b[0m\\x1b[K');s.rv=False
  else:
   if s.F is not None or s.Bg is not None:b.append('\\x1b[0m');s.F=s.Bg=None
   b.append('\\x1b[K')
  s.pv[r]=row
 if s.gm:b.append('\\x1b(B');s.gm=None
 b.append('\\x1b[%%dH'%%ROWS)
 s.s(''.join(b));sys.stdout.flush()
 if s.stats:s.report()
'''


def merge_draw(src):
    t = ast.parse(src)
    tty = next(n for n in t.body if isinstance(n, ast.ClassDef) and n.name == "TTY")
    have = [f.name for f in tty.body if isinstance(f, ast.FunctionDef)]
    assert "draw" in have and "draw_vt" in have, have
    new = ast.parse(MERGED_DRAW.replace("%%", "%")).body[0]
    keep = [f for f in tty.body
            if not (isinstance(f, ast.FunctionDef) and f.name in ("draw", "draw_vt"))]
    tty.body = keep + [new, ast.parse("draw_vt=draw").body[0]]
    return ast.unparse(ast.fix_missing_locations(t))



# ---------- 8b: x.append(y) -> x+=[y] --------------------------------------
# `append` is an attribute, so python_minifier never renames it, and every call
# site pays for the name.  Augmented assignment against a one-element list does
# the same thing with no name at all.  Only statement-level calls whose target is
# a plain name/attribute are rewritten; anything else is left alone.
def kill_append(src):
    t = ast.parse(src)
    ap = set()
    for n in ast.walk(t):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "append" and len(n.args) == 1 \
                and isinstance(n.func.value, (ast.Name, ast.Attribute)):
            ap.add(id(n))
    for n in ast.walk(t):
        for attr in ("body", "orelse", "finalbody"):
            fl = getattr(n, attr, None)
            if isinstance(fl, list):
                for i, st in enumerate(fl):
                    if isinstance(st, ast.Expr) and id(st.value) in ap:
                        v = st.value
                        fl[i] = ast.AugAssign(target=v.func.value, op=ast.Add(),
                                              value=ast.List(elts=[v.args[0]], ctx=ast.Load()))
    return ast.unparse(ast.fix_missing_locations(t))



# ---------- 9b: pay for the harness API names once, not on every use --------
# The names check-opencode.py reads are long (PAL256, QUADS_C16, ...) and the
# minifier will not shorten a module global it has to keep. So rename them for
# the body and re-expose the original spelling as an alias block at the end.
# The alias block itself costs bytes, so only names whose use count pays for it
# get renamed, and a name that is also bound as a local somewhere is skipped --
# hud is both the HUD function and draw()'s parameter, and an alias would
# rebind that local.
def shorten_api(src):
    t = ast.parse(src)
    top = set()
    for n in t.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            top.add(n.name)
        elif isinstance(n, ast.Assign):
            for tg in n.targets:
                if isinstance(tg, ast.Name):
                    top.add(tg.id)
        elif isinstance(n, ast.AnnAssign) and isinstance(tg := n.target, ast.Name):
            top.add(tg.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                top.add((a.asname or a.name).split(".")[0])

    # names bound anywhere that is NOT a top-level statement
    top_store = set()
    for n in t.body:
        for x in ast.walk(n):
            if isinstance(x, ast.Name) and isinstance(x.ctx, (ast.Store, ast.Del)):
                top_store.add(x.id)
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            top_store.add(n.name)
    local = set()
    def add_target(tg):
        if tg is None:
            return
        if isinstance(tg, (list, tuple)):
            for y in tg:
                add_target(y)
            return
        if isinstance(tg, ast.AST):
            for x in ast.walk(tg):
                if isinstance(x, ast.Name):
                    local.add(x.id)
    for n in ast.walk(t):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            ag = n.args
            for a in list(ag.args) + list(ag.kwonlyargs) + (
                    [ag.vararg] if ag.vararg else []) + ([ag.kwarg] if ag.kwarg else []):
                if a is not None:
                    local.add(a.arg)
        elif isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
            add_target(n.target)
        elif isinstance(n, ast.withitem):
            add_target(n.optional_vars)
        elif isinstance(n, ast.ExceptHandler):
            if n.name:
                local.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                local.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.NamedExpr):
            add_target(n.target)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            local.update(n.names)
    # a top-level Store inside a function body is still a module global, so
    # subtract the top-level assignment targets from `local`
    top_targets = set()
    for n in t.body:
        if isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            tglist = n.targets if isinstance(n, ast.Assign) else [n.target]
            for tg in tglist:
                for x in ast.walk(tg):
                    if isinstance(x, ast.Name):
                        top_targets.add(x.id)
    local -= top_targets

    uses = {}
    for n in ast.walk(t):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in top:
            uses[n.id] = uses.get(n.id, 0) + 1
    use = [nm for nm in PUBLIC if nm in top and nm not in local
           and uses.get(nm, 0) * (len(nm) - 2) > len(nm) + 3]
    if not use:
        return src
    short = {nm: "_%d" % i for i, nm in enumerate(use)}

    class R(ast.NodeTransformer):
        def visit_Name(self, n):
            if n.id in short:
                n.id = short[n.id]
            return n

        def _def(self, n):
            self.generic_visit(n)
            return n

        def visit_FunctionDef(self, n):
            if n.name in short and any(n is x for x in t.body):
                n.name = short[n.name]
            return self._def(n)

        def visit_ClassDef(self, n):
            if n.name in short and any(n is x for x in t.body):
                n.name = short[n.name]
            return self._def(n)
    R().visit(t)
    for nm in use:
        t.body.append(ast.Assign(targets=[ast.Name(id=nm, ctx=ast.Store())],
                                 value=ast.Name(id=short[nm], ctx=ast.Load())))
    return ast.unparse(ast.fix_missing_locations(t))


# ---------- 9: python_minifier, public API protected ------------------------
import python_minifier as P


# H = "# mini: byte-identical output to flappy-opencode.py; regenerate, do not edit\n"
HEADER = "# same output bytes as flappy-opencode.py; regenerate, do not edit\n"


def minify(src):
    return HEADER + P.minify(src, rename_globals=True, preserve_globals=PUBLIC)


def build(verbose=True):
    orig = load_orig()
    src = open(SRC).read()
    # count ON-DISK bytes: block glyphs are 3-byte UTF-8, so len(str) understates
    # the file size the user sees in wc -c.
    B = lambda s: len(s.encode("utf-8"))
    n0 = B(src)
    for name, fn in [
        ("strip docstrings", strip),
        ("quadrant 4-bit table", lambda s: collapse_glyphs(s, orig)),
        ("flat hex table", lambda s: apply_flat_hex(s, orig)),
        ("flat mono-ink table", lambda s: apply_flat_ink(s, orig)),
        ("short instance attributes", rename_attrs),
        ("drop internal self-checks", drop_asserts),
        ("drop dead definitions", drop_dead),
        ("drop dead methods", drop_dead_methods),
        ("merge the two draw paths", merge_draw),
        ("append -> augmented assign", kill_append),
        ("shorten API names", shorten_api),
        ("minify + rename locals", minify),
    ]:
        try:
            out = fn(src)
            ast.parse(out)
        except Exception as e:
            if verbose:
                print("  SKIP %-26s %s" % (name, e), file=sys.stderr)
            continue
        if verbose:
            print("  %-26s %7d -> %7d  (-%d)" % (name, B(src), B(out), B(src) - B(out)))
        src = out
    if verbose:
        print("total: %d -> %d bytes (%.1f%% of original)"
              % (n0, B(src), 100.0 * B(src) / n0))
    return src


if __name__ == "__main__":
    open(sys.argv[1] if len(sys.argv) > 1 else "mini_work.py", "w").write(build())
