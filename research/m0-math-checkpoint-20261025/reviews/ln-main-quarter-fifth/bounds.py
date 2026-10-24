"""Review-local rational algebra, with no producer imports or writes."""
from fractions import Fraction as F
S=1<<70
A=F(106497,16384)

def bounds(min_den):
 h=F(1,min_den-1);assert F(1,min_den)+A/S<h
 square=1+F(1,1<<16)
 cube=F(35,64)+h*square
 # t/2^43 is h minus a nonnegative truncation below2^-43.
 minus4=1+63*h+(S*h**3+cube)/(1<<43)+h*cube
 plus4=h*cube
 minus5=1+h*minus4+(S*h**4+plus4)/(1<<43)
 plus5=h*plus4
 N=A*h/(1-h);R=S*h**6/(6*(1-h));third=cube/3+F(1,3)
 common=[(-F(1,2),F(1,2)),(-N,N),(-F(1),square/2),(-third,third),(-plus4/4,minus4/4),(F(0),R)]
 out={}
 for negative in [False,True]:
  terms=common+[(-plus5/5,minus5/5) if negative else (-minus5/5,plus5/5)]
  out['negative' if negative else 'positive']=(-sum(x[0] for x in terms),sum(x[1] for x in terms))
 assert S*h**5+plus5<65536 and S*h**3+cube<1<<38 and (S*h**3+cube)/64<1<<32
 seeded=F(1,min_den)+A/S
 assert S*seeded<1<<59 and S*seeded*seeded+square<1<<48
 return dict(h=h,nonlinear=N,remainder=R,cube=cube,fourth_lower=minus4,fourth_upper=plus4,fifth_lower=minus5,fifth_upper=plus5,**out)

def emitted(den,negative):
 L=F(17,8) if negative else F(9,4)
 U=([F(19,4),F(9,2)] if negative else [F(9,2),F(17,4)])[int(den>=2081)] if den<3585 else (F(17,8) if negative else F(2))
 return L,U

def actual(den,negative):
 return bounds(3585 if den>=3585 else 2081 if den>=2081 else 2049)['negative' if negative else 'positive']

def remainders(fourth,fifth):
 r4=fourth-4*((fourth+2)//4)
 r5=fifth-5*((fifth+2)//5)
 return r4,r5

def bias(fourth,fifth,negative):
 r4,r5=remainders(fourth,fifth)
 return F(r4,4)+(F(r5,5) if negative else -F(r5,5))

def error_interval(sign,n,den,residue,negative,fourth,fifth):
 L,U=actual(den,negative);b=bias(fourth,fifth,negative)
 if sign:L,U=U,L;b=-b
 oriented=-residue if negative!=sign else residue
 return -L+b-F(oriented,den)-F(n,2),U+b-F(oriented,den)

def predicate(distance,above,sign,n,den,residue,negative,fourth,fifth):
 L,U=emitted(den,negative);b=bias(fourth,fifth,negative)
 if sign:L,U=U,L;b=-b
 oriented=-residue if negative!=sign else residue
 # Interval arithmetic form independent of the implementation factor40.
 lower=-L+b-F(oriented,den)-F(n,2)
 upper=U+b-F(oriented,den)
 return upper<=distance if above else lower>=-distance
