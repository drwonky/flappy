# same output bytes as flappy-opencode.py; regenerate, do not edit
AT='.KYYYYYYYWPPWWK..'
AS='beakLo'
AR='pipeLo'
AQ='pipeMid'
AP='pipeHi'
AO='pipeLt'
AD='birdD'
AC='ink'
AB='sandDark'
AA='sand'
A9='grass'
A8='skyD'
A7='pass'
A6=tuple
u='.'
t='skyC'
s='skyB'
r='skyA'
m='grassDark'
l='bot'
k='top'
h='vt100'
g='kwwwwk'
f='kkkkkk'
e=round
d=next
b='pipeO'
a='hillDark'
Z='hill'
T=' '
S=max
Q='cloud'
P=True
O=1.
K=print
J=min
I='x'
H=False
F=enumerate
G=len
E=.0
C=int
B=range
A=None
import sys as i,time as v,math,random
COLS,ROWS=80,25
AE=1
FH=ROWS-AE
SW,SH=COLS*2,FH*2
AU=10
D=SH-AU
U=O/60
GRAV_F=.2
APEX_T=.3
n=2*GRAV_F*D/APEX_T
AF=n/APEX_T
COOLD=.5
AV=1.4*D
j=.278*SW
HW,HTOP,HBOT=8.5,5.,5.
L=29
w,AW=.4167*SW,.56*SW
x,AX=.625*SW,.5*SW
GAP0,GAP1=24.,2e1
AG=85.
y=n*n/(2*AF)
SAFE=GAP1-HTOP-HBOT-y
class Game:
	def __init__(A,seed=A):A.rng=random.Random(seed);A.best=0;A.reset()
	def reset(A):A.y,A.vy,A.pipes=D*.42,E,[];A.score,A.c,A.t,A.ai=0,E,1e9,E;A.dead,A.deadT,A.cl,A.wg=H,E,E,E;A.sp,A.gp,A.spc,A.fl=w,GAP0,x,0
	def ramp(A):B=O-math.exp(-A.score/AG);A.sp=w+(AW-w)*B;A.gp=GAP0+(GAP1-GAP0)*B;A.spc=x+(AX-x)*B
	def spawn(A):B=4+A.rng.random()*(D-8-A.gp);A.pipes+=[{I:float(SW),k:B,l:B+A.gp,A7:H}];A.ai=(A.rng.random()*2-1)*(A.gp-HTOP-HBOT)*.12
	def zlo(A,n):return n[k]+HTOP+y
	def want(B,n):
		C,H=B.zlo(n),n[l]-HBOT
		if C>=H:return B.y<.5*(n[k]+n[l])
		E=d((A for A in B.pipes if A[I]>n[I]+L),A)
		if E:
			F=(E[I]-n[I])/B.sp;G=(n[I]-(j+HW))/B.sp
			if G>F*.55:C=J(C,B.zlo(E))
			if G>F*.3:C=S(C,B.zlo(E))
		if B.y+HBOT>=D-O:return P
		return B.y>=C
	def step(B,dt):
		C=dt;B.cl+=C;B.wg=S(E,B.wg-C*4)
		if B.dead:
			B.deadT+=C
			if B.deadT>1.4:B.reset()
			return
		B.ramp();B.t+=B.sp*C
		if B.t>=B.spc:B.t=E;B.spawn()
		B.c-=C;G=d((A for A in B.pipes if A[I]+L>j-HW),A)
		if G and B.c<=0 and B.want(G):B.vy,B.c,B.wg=-n,COOLD,O;B.fl+=1
		B.vy=J(B.vy+AF*C,AV);B.y+=B.vy*C
		if B.y<HTOP:B.y,B.vy=HTOP,S(B.vy,E)
		for F in B.pipes:
			F[I]-=B.sp*C
			if not F[A7]and F[I]+L<j-HW:
				F[A7]=P;B.score+=1
				if B.score>B.best:B.best=B.score
		B.pipes=[A for A in B.pipes if A[I]+L>-L]
		if B.y+HBOT>=D:B.die();return
		H,K,M=Ah(B)
		for F in B.pipes:
			if Ai(F,H,K,M):B.die();return
	def die(A):A.dead,A.deadT=P,E
AY='6cc5de9adcecc6ecf2e4f6f7eef7fa7fbf4d5f9a3874bf2e4e8f21ded895c3bb6d14200f8ed04a74bf2e5aa81f3d7a121a2419f8e018d9a90ff5f2c0ffffff20242ae8483ab62f26ffffff'
z={B:'#'+AY[6*A:6*A+6]for(A,B)in F((r,s,t,A8,Q,Z,a,A9,m,AA,AB,b,AO,AP,AQ,AR,AC,'birdY',AD,'birdC','eye','pupil','beak',AS,'white'))}
def AZ(h):h=h.lstrip('#');return C(h[0:2],16),C(h[2:4],16),C(h[4:6],16)
R={A:AZ(B)for(A,B)in z.items()}
c=A6(z)
def AH(i):
	if i<16:C=[(0,0,0),(128,0,0),(0,128,0),(128,128,0),(0,0,128),(128,0,128),(0,128,128),(192,192,192),(128,128,128),(255,0,0),(0,255,0),(255,255,0),(0,0,255),(255,0,255),(0,255,255),(255,255,255)];return C[i]
	if i<232:i-=16;A=0,95,135,175,215,255;return A[i//36],A[i//6%6],A[i%6]
	B=8+10*(i-232);return B,B,B
V=[AH(A)for A in B(256)]
W=[AH(A)for A in B(16)]
def Aa(rgb):
	def F(c):c=c/255.;return c/12.92 if c<=.04045 else((c+.055)/1.055)**2.4
	A,B,C=[F(A)for A in rgb];G=(.4124*A+.3576*B+.1805*C)/.95047;H=.2126*A+.7152*B+.0722*C;I=(.0193*A+.1192*B+.9505*C)/1.08883;D=lambda t:t**(O/3.)if t>.008856 else 7.787*t+16./116.;J,E,K=D(G),D(H),D(I);return 116.*E-16.,5e2*(J-E),2e2*(E-K)
AI={}
def X(c):
	B=AI.get(c)
	if B is A:B=AI[c]=Aa(c)
	return B
def dE2(a,b):A,B=X(a),X(b);return(A[0]-B[0])**2+(A[1]-B[1])**2+(A[2]-B[2])**2
A0={}
AJ={}
for N in c:A0[N]=J(B(16),key=lambda i:dE2(R[N],W[i]));AJ[N]=W[A0[N]]
AK={}
COL256={}
for N in c:AK[N]=J(B(256),key=lambda i:dE2(R[N],V[i]));COL256[N]=V[AK[N]]
COL16={A:AJ[A]for A in c}
BG16SET=set(W[:8])
class Scene:
	def __init__(C):C.C=[[(0,0,0)]*SW for A in B(SH)];C.M=[[A]*SW for B in B(SH)]
	def put(A,y,x,c,m):
		if 0<=y<SH and 0<=x<SW:A.C[y][x]=c;A.M[y][x]=m
	def rect(D,x,y,w,h,c,m):
		F,G=C(y),C(y+h);H,I=S(0,C(x)),J(SW,C(x+w))
		for A in B(F,G):
			if not 0<=A<SH:continue
			K=D.C[A];L=D.M[A]
			for E in B(H,I):K[E]=c;L[E]=m
	def clear(A):
		C=0,0,0
		for D in A.C:
			for E in B(SW):D[E]=C
M=3
Y=4
SHAFT=[(0,1,b),(1,3,AO),(4,6,AP),(10,10,AQ),(20,8,AR),(28,1,b)]
CAP_W=L+2*M
def Ab(shaft,over):
	A=[list(A)for A in shaft];A[1][1]+=over;A[-2][1]+=over;B=[];C=0
	for(F,D,E)in A:B+=[(C,D,E)];C+=D
	return A6(B)
LIP=Ab(SHAFT,M)
def paint(sc,g,flash,COL):
	f=flash;F=COL;E=sc;E.clear();A2=[R[r],R[s],R[t],R[A8]];V=[r,r,s,s,t,t,A8];p=-(-D//G(V))
	for K in B(D):
		L=J(G(V)-1,K//p);h=V[L];T=F[h];U=E.C[K];q=E.M[K]
		for A in B(SW):U[A]=T;q[A]=h
	N=g.cl*g.sp*.16
	for L in B(12):A=C((L*34-N)%(SW+34)-17);E.rect(A,D-13,30,13,F[a],a);E.rect(A+5,D-15,20,2,F[a],a);E.rect(A+11,D-17,9,2,F[a],a)
	N=g.cl*g.sp*.34
	for L in B(9):A=C((L*40-N)%(SW+40)-20);E.rect(A,D-7,34,7,F[Z],Z);E.rect(A+4,D-9,24,2,F[Z],Z);E.rect(A+13,D-11,12,2,F[Z],Z)
	N=g.cl*g.sp*.09
	for L in B(4):A=C((L*60-N)%(SW+60)-30);K=7+L%3*7;E.rect(A,K,26,5,F[Q],Q);E.rect(A+6,K-3,13,3,F[Q],Q);E.rect(A+11,K-5,9,2,F[Q],Q);E.rect(A-4,K+5,30,2,F[Q],Q)
	for W in g.pipes:
		A=C(e(W[I]))
		for(u,v,i)in((0,W[k],P),(W[l],D,H)):
			j,X=C(u),C(v);O=X-Y if i else j;w,x=(j,O)if i else(O+Y,X)
			for(c,n,y,z)in((w,x,SHAFT,0),(O,O+Y,LIP,-M)):
				for(A0,A1,o)in y:
					if n>c:E.rect(A+z+A0,c,A1,n-c,F[o],o)
			if O<X:E.rect(A-M,O,CAP_W,1,F[b],b);E.rect(A-M,O+Y-1,CAP_W,1,F[b],b)
	E.rect(0,D,SW,2,F[A9],A9);E.rect(0,D+2,SW,1,F[m],m);E.rect(0,D+3,SW,SH-D-3,F[AA],AA);N=C(g.cl*g.sp)%13
	for A in B(-13,SW+13,13):E.rect(A-N,D+5,7,SH-D-5,F[AB],AB);E.rect(A-N+7,D+3,3,2,F[m],m)
	Ak(E,g,F)
	if f>0:
		d=255,255,255;S=f
		for K in B(SH):
			U=E.C[K]
			for A in B(SW):T=U[A];U[A]=C(T[0]*(1-S)+d[0]*S),C(T[1]*(1-S)+d[1]*S),C(T[2]*(1-S)+d[2]*S)
BIRD_BODY='....KKKKKKKK.....','..KKYYYYYYWWWWK..',AT,AT,'.KDDYYYYYCCCCWRRK','KDDDDDDYYCCCWWRRK','KDDDDDDYCCCCCCOOK','.KDDDDDCCCCCCOOOK','..KKDDDDCCCCKK...','....KKKKKKK......'
WING_UP=(1,1,f),(2,1,g),(3,1,g),(4,1,f)
WING_MID=(4,1,f),(5,1,g),(6,1,g),(7,1,f)
WING_DOWN=(6,3,f),(7,3,g),(8,3,g),(9,3,f)
Ac={'K':AC,'Y':'birdY','D':AD,'C':'birdC','W':'eye','P':'pupil','R':'beak','O':AS,'k':AC,'w':AD}
BIRD_W,BIRD_H=17,10
def Ad(pose):
	A=[list(A)for A in BIRD_BODY]
	for(B,C,E)in pose:
		for(D,G)in F(E):
			if 0<=B<BIRD_H and 0<=C+D<BIRD_W:A[B][C+D]=G
	return A
def Ae(rows):
	D=[]
	for E in B(BIRD_H):C=[A for A in B(BIRD_W)if rows[E][A]!=u];D+=[(C[0],C[-1])if C else A]
	return D
Af=.6,.18,A
o=[]
for(Ap,Ag)in F((WING_UP,WING_MID,WING_DOWN)):p=Ad(Ag);o+=[(p,Ae(p))]
def AL(g):
	C=g.wg
	for(D,B)in F(Af):
		if B is A or C>B:return o[D]
	return o[-1]
AM=BIRD_H//2
def Ah(g):return C(e(g.y))-AM,AL(g)[1],C(e(j))-BIRD_W//2
def Ai(p,y0,runs,x0):
	D=C(e(p[I]));F,G=C(p[k]),C(p[l])
	for O in B(BIRD_H):
		J=runs[O]
		if J is A:continue
		E=y0+O
		if F<=E<G:continue
		if E<F and E>=F-Y:K,N=D-M,D+L+M
		elif E>=G and E<G+Y:K,N=D-M,D+L+M
		else:K,N=D,D+L
		if x0+J[0]<N and x0+J[1]>=K:return P
	return H
for(Aq,(p,Aj))in F(o):
	for AN in B(BIRD_H):
		if Aj[AN]is A:continue
		Ar=[A for A in B(BIRD_W)if p[AN][A]!=u]
def Ak(sc,g,COL):
	G=C(e(j))-BIRD_W//2;H=C(e(g.y))-AM;I=AL(g)[0]
	for A in B(BIRD_H):
		J=H+A
		for D in B(BIRD_W):
			E=I[A][D]
			if E==u:continue
			F=Ac[E];sc.put(J,G+D,COL[F],F)
q=' ▗▖▄▝▐▞▟▘▚▌▙▀▜▛█'
SHADE={'░':.25,'▒':.5,'▓':.75}
A1={C:A6(16*(A>>3-B&1)for B in B(4))for(A,C)in F(q)}
A1.update({A:(0,0,0,0)for A in SHADE})
Al=set(q)
QUADS_RICH={A:B for(A,B)in F(q)}
SET_RICH=' █▀▄▌▐▘▗▖▝▙▟▛▜▚▞░▒▓'
SET_C16=' █▀▄▌▐░▒▓'
QUADS_C16={A:q[A]for A in[0,3,5,10,12,15]}
def _mix(fg,bg,t):return C(fg[0]*t+bg[0]*(1-t)),C(fg[1]*t+bg[1]*(1-t)),C(fg[2]*t+bg[2]*(1-t))
def quantise(cell,bg_ok,glyphs,quads,cache):
	d=glyphs;Y=cache;W='█';R=bg_ok;N=cell;e=Y.get(N)
	if e is not A:return e
	I=[]
	for K in N:
		if K not in I:I+=[K]
	if G(I)==2:
		f,Z=I;a=0
		for(g,K)in F(N):
			if K==Z:a|=(8,4,2,1)[g]
		for(D,B,h)in((Z,f,a),(f,Z,15^a)):
			if not R(B):continue
			C=quads.get(h)
			if C is A:continue
			O=(C,D,B,E)if C not in(T,W)else(W,D,A,E)if C==W else(T,A,B,E);Y[N]=O;return O
	S=[X(A)for A in N];P=[A]
	def Q(e,g,fg,bg):
		if P[0]is A or e<P[0][0]:P[0]=e,g,fg,bg
	for K in I:
		L=X(K);H=E
		for M in S:H+=(L[0]-M[0])**2+(L[1]-M[1])**2+(L[2]-M[2])**2
		H/=4.
		if R(K):Q(H,T,A,K)
		Q(H,W,K,A)
	for D in I:
		b=X(D);U=[(b[0]-A[0])**2+(b[1]-A[1])**2+(b[2]-A[2])**2 for A in S]
		for B in I:
			if B==D or not R(B):continue
			c=X(B);V=[(c[0]-A[0])**2+(c[1]-A[1])**2+(c[2]-A[2])**2 for A in S]
			for C in d:
				if C not in Al:continue
				J=A1[C]
				if J==(0,0,0,0)or J==(16,16,16,16):continue
				H=(J[0]*U[0]+(16-J[0])*V[0]+J[1]*U[1]+(16-J[1])*V[1]+J[2]*U[2]+(16-J[2])*V[2]+J[3]*U[3]+(16-J[3])*V[3])/64.;Q(H,C,D,B)
	for(C,i)in SHADE.items():
		if C not in d:continue
		for D in I:
			for B in I:
				if B==D or not R(B):continue
				L=X(_mix(D,B,i));H=E
				for M in S:H+=(L[0]-M[0])**2+(L[1]-M[1])**2+(L[2]-M[2])**2
				Q(H/4.,C,D,B)
	if P[0]is A:Q(E,T,A,I[0])
	H,C,D,B=P[0];O=C,D,B,H;Y[N]=O;return O
def render(sc,bg_ok,glyphs,quads,cache):
	C=[]
	for D in B(FH):
		E,F=sc.C[D*2],sc.C[D*2+1];G=[]
		for A in B(COLS):H=E[2*A],E[2*A+1],F[2*A],F[2*A+1];I,J,K,L=quantise(H,bg_ok,glyphs,quads,cache);G+=[(I,J,K)]
		C+=[G]
	return C
def A2(palette):
	D=palette;H={B:A for(A,B)in F(D)};E={}
	def C(c):
		C=H.get(c)
		if C is not A:return C
		C=E.get(c)
		if C is A:C=E[c]=J(B(G(D)),key=lambda j:dE2(c,D[j]))
		return C
	return C
def A3(rows,idx):
	B=[]
	for F in rows:
		C=[]
		for(G,D,E)in F:C+=[(G,A if D is A else idx(D),A if E is A else idx(E))]
		B+=[C]
	return B
A4=(T,E,H),('~',.14,H),('q',.34,H),('a',.55,H),('`',.75,H),(T,O,P)
MONO_INK={A:C(B)/1e2 for(A,B)in zip(c,'3 5 7 10 0 45 60 50 68 30 48 100 42 52 62 78 100 48 62 22 5 95 55 72 0'.split())}
BAYER4=(0,8,2,10),(12,4,14,6),(3,11,1,9),(15,7,13,5)
def A5(sc):
	F=[];H=G(A4)
	for I in B(FH):
		K=[]
		for L in B(COLS):
			A=E
			for O in(0,1):
				for P in(0,1):A+=MONO_INK.get(sc.M[I*2+O][L*2+P],.5)
			A/=4.;M=A*(H-1);N=C(M);Q=M-N;R=(BAYER4[I*2&3][L*2&3]+.5)/16.;D=N+(1 if Q>=R else 0);D=S(0,J(H-1,D));T,V,U=A4[D];K+=[(T,U)]
		F+=[K]
	return F
class TTY:
	def __init__(B,mode,stats):B.mode,B.stats=mode,stats;B.pv=[A]*FH;B.gm=A;B.F=A;B.Bg=A;B.rv=H;B.n=0;B.NW=0
	def s(A,t):B='replace';A.n+=G(t.encode('latin-1',B));A.NW+=G(t.encode('utf-8',B));i.stdout.write(t)
	def boot(A):
		if A.mode!=h:A.s('\x1b[?1049h\x1b[?25l')
		A.s('\x1b[2J')
	def report(A):i.stderr.write('frame %dB as counted / %dB on the wire = %.2fs at 9600 baud\n'%(A.n,A.NW,A.NW/96e1))
	def bye(A):
		A.s('\x1b[0m\x1b[27m\x1b(B')
		if A.mode!=h:A.s('\x1b[?25h\x1b[?1049l')
	def draw(C,rows,hud):
		Z='\x1b[49m';Y='\x1b[%dm';X='\x1b[39m';W='\x1b[%dH';V='\x1b[0m';U='\x1b[27m';Q='\x1b(B';C.n=0;C.NW=0;J=C.mode==h;R=C.mode=='rich';D=['\x1b[1H']
		if C.gm:D+=[Q];C.gm=A
		D+=[U if J else V];C.F=C.Bg=A;C.rv=H;D+=[hud[:COLS].ljust(COLS)]
		for O in B(FH):
			E=rows[O]
			if C.pv[O]==E:continue
			F=G(E)-1
			while F>=0 and E[F][0]==T and(not E[F][1]if J else E[F][2]is A):F-=1
			D+=[W%(O+1+AE)]
			if J:
				S=any(E[A][0]!=T or E[A][1]for A in B(F+1))
				if S and C.gm is A:D+=['\x1b(0'];C.gm=P
				elif not S and C.gm:D+=[Q];C.gm=A
			K=0
			while K<=F:
				M=E[K][1]if J else(E[K][1],E[K][2])
				if J:
					if M!=C.rv:D+=['\x1b[7m'if M else U];C.rv=M
				elif M!=(C.F,C.Bg):
					I,N=M
					if I!=C.F:
						if R:D+=['\x1b[38;5;%dm'%I if I is not A else X]
						else:D+=[Y%(90+I-8 if I>=8 else 30+I)if I is not A else X]
					if N!=C.Bg:
						if R:D+=['\x1b[48;5;%dm'%N if N is not A else Z]
						else:D+=[Y%(40+N)if N is not A else Z]
					C.F,C.Bg=I,N
				L=K
				while L<=F and(E[L][1]if J else(E[L][1],E[L][2]))==M:L+=1
				D+=[''.join(E[A][0]for A in B(K,L))];K=L
			if J:D+=['\x1b[27m\x1b[0m\x1b[K'];C.rv=H
			else:
				if C.F is not A or C.Bg is not A:D+=[V];C.F=C.Bg=A
				D+=['\x1b[K']
			C.pv[O]=E
		if C.gm:D+=[Q];C.gm=A
		D+=[W%ROWS];C.s(''.join(D));i.stdout.flush()
		if C.stats:C.report()
	draw_vt=draw
def hud(g):
	B=O-math.exp(-g.score/AG);A='     '
	if g.score>=40:A=' PLAT'
	elif g.score>=30:A=' GOLD'
	elif g.score>=20:A=' SLVR'
	elif g.score>=10:A=' BRNZ'
	return' FLAPPY-OPENCODE %3d BEST %3d%s GAP %4.1f ZONE %4.1f %s%s '%(g.score,g.best,A,g.gp,g.gp-HTOP-HBOT-y,'#'*C(18*B),u*(18-C(18*B)))
def Am(n,seed):
	K('selftest %d games, step %.4fs'%(n,U));E=[]
	for I in B(n):
		F=Game(seed+I*7919)
		for L in B(C(24000)):
			F.step(U)
			if F.dead:E+=[F.score];break
		else:E+=[A]
	D=sorted(B for B in E if B is not A)
	if not D:K('  nobody ever crashed -> pilot too strong / asymptote too soft');return
	H=lambda p:D[S(0,J(G(D)-1,C(p*(G(D)-1))))];K('  died %d/%d  crash score p10 %d p50 %d p90 %d  range %d..%d'%(G(D),n,H(.1),H(.5),H(.9),D[0],D[-1]));K('  distinct crash scores %d of %d  |  deaths before pipe 40: %d'%(G(set(D)),G(D),sum(1 for A in D if A<40)));K('  safe-flap zone at asymptote: %.1f sub-rows (0 = forced death)'%SAFE)
def An():
	F='rgb';K("material -> nearest palette entry.  dE is CIE76 colour distance (a hair's breadth is ~2.3, a noticeable mismatch is >10).");K('%-10s %-9s %5s %-16s %7s %5s %-16s %7s'%('material','hex','256',F,'dE','16',F,'dE'))
	for A in c:
		if A=='white':continue
		C=R[A];D=J(B(256),key=lambda i:dE2(C,V[i]));E=A0[A];K('%-10s %-9s %5d %-16s %7.1f %5d %-16s %7.1f'%(A,z[A],D,str(V[D]),dE2(C,V[D])**.5,E,str(W[E]),dE2(C,W[E])**.5))
def Ao():
	j='--seed';g='c16';D=i.argv[1:];L=h if'--vt100'in D else g if'--c16'in D else'rich';k='--stats'in D
	if'--selftest'in D:l=d((C(D[A+1])for(A,B)in F(D)if B=='--n'),20);m=d((C(D[A+1])for(A,B)in F(D)if B==j),1);Am(l,m);return
	if'--palette'in D:An();return
	H=Game(d((C(D[A+1])for(A,B)in F(D)if B==j),A));I=Scene()
	if L==g:Q,R,T,X,Y=COL16,lambda c:c in BG16SET,SET_C16,QUADS_C16,A2(W)
	else:Q,R,T,X,Y=COL256,lambda c:P,SET_RICH,QUADS_RICH,A2(V)
	Z={};b=d((C(D[A+1])for(A,B)in F(D)if B=='--frames'),0)
	if b:
		for n in B(b):
			for o in B(60):H.step(U)
			paint(I,H,.9*S(E,O-H.deadT/.4)if H.dead else E,Q)
			if L==h:a=A5(I);c=[''.join(A for(A,B)in A)for A in a]
			else:a=A3(render(I,R,T,X,Z),Y);c=[''.join(A for(A,B,B)in A)for A in a]
			K(hud(H));K('\n'.join(c));K()
		i.stderr.write('cache entries %d\n'%G(Z));return
	M=TTY(L,k);M.boot();N,e=E,v.time()
	try:
		while P:
			f=v.time();N=J(.25,N+f-e);e=f
			while N>=U:H.step(U);N-=U
			paint(I,H,.9*S(E,O-H.deadT/.4)if H.dead else E,Q)
			if L==h:M.draw_vt(A5(I),hud(H))
			else:M.draw(A3(render(I,R,T,X,Z),Y),hud(H))
			v.sleep(.006)
	except KeyboardInterrupt:0
	finally:M.bye()
if __name__=='__main__':Ao()
ANSI16=W
CAP_H=Y
CAP_X=M
FIXED=U
make_mapper=A2
MATS=c
PAL256=V
PIPE_W=L
QUADCOUNT=A1
RGB=R
to_indices=A3
vt_frame=A5
VT_LADDER=A4
SKY=D