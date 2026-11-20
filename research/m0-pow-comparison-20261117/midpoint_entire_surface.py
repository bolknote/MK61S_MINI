#!/usr/bin/env python3
"""Certify pow midpoint rectangles using an entire surface parametrization."""
import argparse
from fractions import Fraction
from functools import cache
import gzip
import json
from math import ceil, comb, isqrt
from pathlib import Path
import subprocess
from time import perf_counter, process_time

from midpoint_grid import FixedInterval, add, use_flint_products
from midpoint_surface_rotated import (Q, Series, checked_transform, excludes_residues, exponents,
                                      integer_interval, reduce_lattice,
                                      require, sample_blocks)
from midpoint_scale_grid import GAP



def interval_fraction(grid, value):
    return grid.rational(value.numerator, value.denominator)


def absolute(span):
    require(not span[0] <= 0 <= span[1], 'logarithmic rectangle crosses zero')
    return span if span[0] > 0 else (-span[1], -span[0])


def sign_of(span):
    return 1 if span[0] > 0 else -1


def divide_integer(interval, n):
    return interval[0]//n, -(-interval[1]//n)


def exp_near_zero(grid, interval):
    require(max(map(abs, interval)) < grid.unit//2, 'exponential center is too far away')
    term = total = grid.rational(1)
    n = 0
    while max(map(abs, term)) > 1:
        n += 1
        term = divide_integer(grid.multiply(term, interval), n)
        total = add(total, term)
    # The real term is bounded by one unit. All following ratios are < 1/2.
    return total[0]-1, total[1]+1


def exp_upper(value):
    require(0 <= value <= 128, 'exponential magnitude too large for the proof radius')
    return Fraction(1)/(1-value) if value <= Fraction(1, 2) else 1 << ceil(2*value)


def decode_block(block):
    require(isinstance(block, (list, tuple)) and len(block) in (5, 6)
            and all(type(v) is int for v in block), 'invalid block')
    ex, bx, em, bm, wx = block[:5]
    wm = block[-1]
    require(-1022 <= ex <= 1023 and -1022 <= em <= 1023
            and 4 <= wx <= 52 and 4 <= wm <= 52
            and 0 <= bx < 1 << (52-wx) and 0 <= bm < 1 << (52-wm),
            'block is outside normal binades')
    return ex,bx,em,bm,wx,wm


def encoding_spans(block):
    ex,bx,em,bm,wx,wm = decode_block(block)
    x = ((ex+1023) << 52)+(bx << wx)
    m = ((em+1023) << 52)+(bm << wm)
    return (x,x+(1 << wx)), (m,m+(1 << wm))


def contains_box(block, x, m, chart):
    xb,mb = encoding_spans(block)
    if not xb[0] <= x[0] < x[1] <= xb[1] or not m[0] < m[1]:
        return False
    if chart != 'diagonal':
        return mb[0] <= m[0] < m[1] <= mb[1]
    x_center,m_center = sum(xb)//2,sum(mb)//2
    half = m_center-mb[0]
    # The certificate controls differences of mantissa indices. Opposite
    # corners are the extrema of (m-m_center)-(x-x_center).
    return (-half <= m[0]-m_center-(x[1]-1-x_center)
            and m[1]-1-m_center-(x[0]-x_center) < half)


class Entire:
    """Enclose the image of the discrete midpoint test on [-1,1]^2."""

    max_scaled_radius = 16

    def __init__(self, block, degree, work_bits, shift=52, shear=0):
        ex,bx,em,bm,wx,wm = decode_block(block)
        require(type(degree) is int and 1 <= degree <= 32
                and type(work_bits) is int and 16 <= work_bits <= 768
                and type(shift) is int and -10 <= shift <= 116
                and type(shear) in (int,bool) and 0 <= shear <= 8, 'invalid proof parameters')
        self.degree = degree
        grid = self.grid = FixedInterval(work_bits+56*degree+96)
        self.work_bits = work_bits
        hx, hm = 1 << (wx-1), 1 << (wm-1)
        self.x_center = a = Q+(2*bx+1)*hx
        b = 2*(Q+(2*bm+1)*hm)+1
        self.eta = Fraction(hx, a-hx)
        ln2 = grid.log(2, 1)
        unit = grid.unit

        def log(a, d, e):
            return add(grid.scale(ln2, e), grid.log(a, d))

        q = Fraction(2)**shift
        lx = log(a, Q, ex)
        lm = log(b, 2*Q, em)
        sign = 1 if (lx[0] > 0) == (lm[0] > 0) else -1
        proj_center = grid.multiply(interval_fraction(grid, q),
                                    grid.divide(absolute(lm), absolute(lx)))
        p0 = sum(proj_center)//(2*unit)
        xlo, xhi = absolute((log(a-hx, Q, ex)[0], log(a+hx-1, Q, ex)[1]))
        mlo, mhi = absolute((log(b-2*hm, 2*Q, em)[0], log(b+2*(hm-1), 2*Q, em)[1]))
        guard = 1 << max(0, grid.precision-GAP)
        require(mlo > guard, 'midpoint logarithm is inside the guard')
        theta = add(grid.multiply(interval_fraction(grid, Fraction(sign*p0)/q), lx),
                    grid.scale(lm, -1))
        # p0*(1+ratio*u+...) approximates q*abs(log(m0)/log(x)).
        # Its product with log(x) has small pure-u coefficients.
        ratio = -self.eta/Fraction(sum(lx),2*unit)
        p_poly = tuple(p0*ratio**i for i in range(shear+1))
        self.y_coefficients = p_poly[1:]
        self.y_slope = self.y_coefficients[0] if shear else Fraction(0)
        exp_x = [grid.multiply(add(interval_fraction(grid,p_poly[i-1]*self.eta),
                                   grid.multiply(lx,interval_fraction(grid,p_poly[i]))),
                               interval_fraction(grid,Fraction(sign)/q)) for i in range(1,shear+1)]
        exp_x.append(interval_fraction(grid,p_poly[-1]*self.eta*sign/q))
        self.exp_x = tuple(exp_x)
        if shear:
            target = absolute(lm)
            variation = Fraction(max(mhi-target[0],target[1]-mlo)+guard,unit)
            margin = variation+Fraction(max(map(abs,theta))+
                                        sum(max(map(abs,v)) for v in self.exp_x),unit)
            self.y_half = ceil(q*margin/Fraction(xlo,unit))
        else:
            projection = grid.multiply(interval_fraction(grid,q),
                                       grid.divide((mlo-guard,mhi+guard),(xlo,xhi)))
            self.y_half = ceil(Fraction(max(abs(v-p0*unit) for v in projection),unit))
        h = self.y_half
        require(h > 0, 'empty projection')
        self.beta = grid.multiply(grid.rational(b, 2), exp_near_zero(grid, theta))
        self.constant = add(self.beta, grid.rational(-b, 2))
        self.exp_y = grid.multiply(interval_fraction(grid, Fraction(sign*h)/q), lx)
        self.exp_xy = self.eta*sign*h/q
        self.linear = (grid.multiply(self.beta, self.exp_x[0]),
                       grid.multiply(self.beta, self.exp_y))
        self.vertical = Fraction(1, 1 << (GAP-54))

    def bounds(self, transform, rx, ry):
        g = self.grid.unit
        tx = rx*self.eta
        higher = rx*ry*abs(self.exp_xy)+sum(Fraction(max(map(abs,v))*rx**i,g)
                                           for i,v in enumerate(self.exp_x[1:],2))
        tm = Fraction(rx*max(map(abs,self.exp_x[0]))+ry*max(map(abs,self.exp_y)),g)+higher
        dx = self.x_center*tx**2*exp_upper(tx)/2
        dy = sum(abs(v)*rx**i for i,v in enumerate(self.y_coefficients[1:],2))
        dm = Fraction(self.beta[1],g)*(higher+tm**2*exp_upper(tm)/2)
        ax = self.x_center*self.eta
        mx, my = self.linear
        constant = Fraction(max(map(abs,self.constant)),g)
        return tuple(abs(c)*constant + rx*max(abs(a*ax+b*self.y_slope+c*Fraction(v,g)) for v in mx)
                     + ry*max(abs(b*self.y_half+c*Fraction(v,g)) for v in my)
                     + abs(a)*dx+abs(b)*dy+abs(c)*dm for a,b,c in transform)

    def choose_terms(self, transform, tensor=False):
        candidates = []
        for sx in range(1,54):
            rx = 1 << sx
            if rx*self.eta > self.max_scaled_radius:
                break
            for sy in range(1,54) if tensor else (sx,):
                ry = 1 << sy
                if rx*ry*abs(self.exp_xy) > 16:
                    break
                try:
                    cap = ceil(max(self.bounds(transform,rx,ry)))+self.degree
                except ValueError:
                    continue
                power = cap**self.degree
                target = power.bit_length()+self.work_bits+3
                if tensor:
                    terms = tuple(max(2,-(-target//shift)) for shift in (sx,sy))
                    candidates.append((terms[0]*terms[1],(sx,sy),terms))
                else:
                    terms = max(self.degree+1, -(-target//sx))
                    while power*(2*terms+4) > 1 << (sx*terms-self.work_bits):
                        terms += 1
                    candidates.append((terms,sx,terms))
        require(bool(candidates), 'no suitable complex disk')
        _,shifts,terms = min(candidates)
        return shifts,terms

    def tail(self, transform, shifts, terms):
        tensor = isinstance(terms,(list,tuple))
        if tensor:
            require(isinstance(shifts,(list,tuple)) and len(shifts) == len(terms) == 2
                    and all(type(v) is int and 1 <= v <= 53 for v in shifts)
                    and all(type(v) is int and 2 <= v <= 256 for v in terms),'invalid truncation')
        else:
            require(type(shifts) is int and type(terms) is int and 1 <= shifts <= 53
                    and 2 <= terms <= 256, 'invalid truncation')
        sx,sy = shifts if tensor else (shifts,shifts)
        rx,ry = 1 << sx,1 << sy
        require(rx*self.eta <= self.max_scaled_radius and rx*ry*abs(self.exp_xy) <= 16,
                'complex radius exceeds the supported scaling')
        cap = ceil(max(self.bounds(transform,rx,ry)))+self.degree
        if tensor:
            remainder = sum(Fraction(4*cap**self.degree,1 << (s*n)) for s,n in zip(shifts,terms))
        else:
            remainder = Fraction(cap**self.degree*(2*terms+4),1 << (sx*terms))
        velocity = max(abs(row[2]) for row in transform)*self.vertical
        real = ceil(max(self.bounds(transform,1,1))+velocity)+self.degree
        return remainder+self.degree*velocity*real**(self.degree-1)

    def adapt(self):
        from flint import fmpz_mat
        unit = self.grid.unit
        weight = 1 << 24
        ax = self.x_center*self.eta
        xm = Fraction(sum(self.linear[0]),2*unit)
        ym = Fraction(sum(self.linear[1]),2*unit)
        nonlinear = self.bounds(((0,0,1),),1,1)[0]-abs(xm)-abs(ym)
        matrix = [[max(1,int(ax*weight)),0,0],[int(self.y_slope*weight),self.y_half*weight,0],
                  [int(xm*weight),int(ym*weight),ceil(max(1,nonlinear)*weight)]]
        _, transform = fmpz_mat(matrix).lll(transform=True,delta=.99)
        return checked_transform([[int(transform[i,j]) for j in range(3)] for i in range(3)])


class MantissaChart(Entire):
    """Use an affine base mantissa and let the midpoint center track it."""

    max_scaled_radius = Fraction(1, 2)

    def __init__(self, block, degree, work_bits, shift, diagonal=False):
        ex,bx,em,bm,wx,wm = decode_block(block)
        require(type(degree) is int and 1 <= degree <= 32
                and type(work_bits) is int and 16 <= work_bits <= 768
                and type(shift) is int and -10 <= shift <= 116, 'invalid proof parameters')
        self.degree = degree
        self.work_bits = work_bits
        grid = self.grid = FixedInterval(work_bits+56*degree+96)
        unit = grid.unit
        ln2 = grid.log(2, 1)
        self.x_half = hx = 1 << (wx-1)
        hm = 1 << (wm-1)
        self.x_center = a = Q+(2*bx+1)*hx
        b = 2*(Q+(2*bm+1)*hm)+1
        self.eta = Fraction(hx,a)

        def log(a, d, e):
            return add(grid.scale(ln2,e),grid.log(a,d))

        self.lx = lx = log(a,Q,ex)
        lm = log(b,2*Q,em)
        sign = 1 if (lx[0] > 0) == (lm[0] > 0) else -1
        q = Fraction(2)**shift
        proj = grid.multiply(interval_fraction(grid,q),grid.divide(absolute(lm),absolute(lx)))
        p0 = sum(proj)//(2*unit)
        x_span = log(a-hx,Q,ex)[0], log(a+hx-1,Q,ex)[1]
        m_low,m_high = b-2*hm,b+2*(hm-1)
        if diagonal:
            m_low -= 2*hx
            m_high += 2*(hx-1)
        require(2*Q <= m_low <= m_high < 4*Q,'midpoint band crosses a binade')
        m_span = log(m_low,2*Q,em)[0],log(m_high,2*Q,em)[1]
        guard = 1 << max(0,grid.precision-GAP)
        require(absolute(m_span)[0] > guard, 'midpoint logarithm is inside the guard')
        theta = add(grid.multiply(interval_fraction(grid,sign*p0/q),lx),grid.scale(lm,-1))
        if diagonal:
            # B=b+2*(A-a)+2*T, |T|<=hm. Bound log((B/b)/(A/a))
            # directly so movement along the band does not inflate it.
            radius = Fraction(abs(2*a-b)*hx+2*a*hm,b*(a-hx))
            require(radius < 1,'diagonal span reaches the logarithmic pole')
            margin = Fraction(max(map(abs,theta))+guard,unit)+radius/(1-radius)
        else:
            dx = add(x_span,grid.scale(lx,-1))
            dm = add(m_span,grid.scale(lm,-1))
            residual = add(add(dm,grid.scale(dx,-1)),grid.scale(theta,-1))
            margin = Fraction(max(map(abs,residual))+guard,unit)
        self.y_half = ceil(q*margin/Fraction(absolute(x_span)[0],unit))
        require(self.y_half > 0,'empty projection')

        # L(u)=lx+log(1+eta*u). For p_c=s*q+(p0-s*q)*lx/L(u),
        # s*p_c*L(u)/q = s*p0*lx/q+log(1+eta*u) identically.
        self.alpha = p0-sign*q
        self.rate = sign*self.y_half/q
        self.exp_xy = self.eta*self.rate
        self.c0 = grid.multiply(interval_fraction(grid,self.rate),lx)
        self.beta = grid.multiply(grid.rational(b,2),exp_near_zero(grid,theta))
        self.constant = add(self.beta,grid.rational(-b,2))
        self.linear = (grid.multiply(self.beta,interval_fraction(grid,self.eta)),
                       grid.multiply(self.beta,self.c0))
        d1 = grid.divide(interval_fraction(grid,-self.alpha*self.eta*sign_of(lx)),absolute(lx))
        self.y_slope = Fraction(sum(d1),2*unit)
        self.y_slope_error = Fraction(d1[1]-d1[0],2*unit)
        self.vertical = Fraction(1,1 << (GAP-54))

    def bounds(self, transform, rx, ry):
        unit = self.grid.unit
        r = rx*self.eta
        require(0 <= r <= self.max_scaled_radius,'mantissa radius reaches the logarithmic pole')
        delta = r/(1-r)
        floor = Fraction(absolute(self.lx)[0],unit)
        require(floor > delta,'mantissa radius reaches a zero of the denominator')
        p_error = (rx*self.y_slope_error + abs(self.alpha)*
                   (r*r/(2*(1-r)*floor)+delta*delta/(floor*(floor-delta))))
        error_rate = ry*abs(self.rate)*delta
        z = ry*Fraction(max(map(abs,self.c0)),unit)+error_rate
        m_error = Fraction(self.beta[1],unit)*((1+r)*z*z*exp_upper(z)/2+error_rate+r*z)
        mx,my = self.linear
        constant = Fraction(max(map(abs,self.constant)),unit)
        ax = self.x_center*self.eta
        return tuple(abs(c)*constant + rx*max(abs(a*ax+b*self.y_slope+c*Fraction(v,unit)) for v in mx)
                     + ry*max(abs(b*self.y_half+c*Fraction(v,unit)) for v in my)
                     + abs(b)*p_error+abs(c)*m_error for a,b,c in transform)


def taylor_exp(grid, coefficients, terms):
    terms_list = [grid.rational(1)]
    for j in range(1,terms):
        v = (0,0)
        for i,coef in enumerate(coefficients[:j],1):
            v = add(v,grid.scale(grid.multiply(coef,terms_list[j-i]),i))
        terms_list.append(divide_integer(v,j))
    return terms_list


def mantissa_coordinates(geometry, series):
    grid = geometry.grid
    nx,ny = series.x_terms,series.m_terms
    lx = geometry.lx
    log = [(0,0)]+[interval_fraction(grid,(-1)**(i+1)*geometry.eta**i/i) for i in range(1,nx)]
    fixed_rate = interval_fraction(grid,geometry.rate)
    rate = [geometry.c0]+[grid.multiply(fixed_rate,v) for v in log[1:]]
    inv_sign = sign_of(lx)
    abs_lx = absolute(lx)
    alpha = interval_fraction(grid,geometry.alpha)
    delta_p = [(0,0)]
    for i in range(1,nx):
        c = grid.multiply(alpha,log[i])
        for j in range(1,i):
            c = add(c,grid.multiply(log[j],delta_p[i-j]))
        delta_p.append(grid.divide(grid.scale(c,-inv_sign),abs_lx))

    # Expand exp(v*rate(u)) one coefficient of v at a time.
    exp_v = [[grid.rational(1)]+[(0,0)]*(nx-1)]
    for j in range(1,ny):
        prev = exp_v[-1]
        row = []
        for i in range(nx):
            c = (0,0)
            for k in range(i+1):
                c = add(c,grid.multiply(prev[i-k],rate[k]))
            row.append(divide_integer(c,j))
        exp_v.append(row)
    scaled_eta = interval_fraction(grid,geometry.eta)
    base = [(0,0)]*len(series.indices)
    exponent = base.copy()
    base[series.locations[1,0]] = grid.rational(geometry.x_half)
    exponent[series.locations[0,1]] = grid.rational(geometry.y_half)
    for i in range(1,nx):
        exponent[series.locations[i,0]] = delta_p[i]
    midpoint = []
    for i,j in series.indices:
        c = exp_v[j][i]
        if i:
            c = add(c,grid.multiply(scaled_eta,exp_v[j][i-1]))
        midpoint.append(grid.multiply(c,geometry.beta) if (i,j) != (0,0) else geometry.constant)
    return base,exponent,midpoint


def basis(geometry, transform, terms):
    grid = geometry.grid
    series = Series(terms, grid)
    if isinstance(geometry,MantissaChart):
        base,exponent,midpoint = mantissa_coordinates(geometry,series)
        linear = [[add(add(grid.scale(x,a),grid.scale(y,b)),grid.scale(m,c))
                   for x,y,m in zip(base,exponent,midpoint)] for a,b,c in transform]
        return series.newton_basis(linear,geometry.degree)
    origin = series.locations[0,0]
    at_y = series.locations[0,1]
    linear = []
    nx,ny = series.x_terms,series.m_terms
    base = taylor_exp(grid,(interval_fraction(grid,geometry.eta),),nx)
    exp_x = taylor_exp(grid,geometry.exp_x,nx)
    exp_y = taylor_exp(grid,(geometry.exp_y,),ny)
    exp_xy = taylor_exp(grid,(interval_fraction(grid,geometry.exp_xy),),min(nx,ny))
    midpoint = []
    for i,j in series.indices:
        coefficient = (0,0)
        for k in range(min(i,j)+1):
            product = grid.multiply(grid.multiply(exp_x[i-k],exp_y[j-k]),exp_xy[k])
            coefficient = add(coefficient,product)
        midpoint.append(grid.multiply(coefficient,geometry.beta))
    midpoint[origin] = geometry.constant
    for a,b,c in transform:
        coord = [grid.scale(v,c) for v in midpoint]
        for i in range(1,nx):
            ix = series.locations[i,0]
            coord[ix] = add(coord[ix],grid.scale(base[i],a*geometry.x_center))
        for i,value in enumerate(geometry.y_coefficients[:nx-1],1):
            ix = series.locations[i,0]
            coord[ix] = add(coord[ix],interval_fraction(grid,b*value))
        coord[at_y] = add(coord[at_y],grid.rational(b*geometry.y_half))
        linear.append(coord)
    return series.newton_basis(linear, geometry.degree)


@cache
def chebyshev_weights(terms):
    # T_k is the polynomial cos(k*acos(x)), with bound one on [-1,1].
    # Entries are the expansion of x^i multiplied by 2**(terms-1).
    return tuple(tuple((k,comb(i,(i-k)//2) << (terms-1-i+bool(k)))
                       for k in range(i%2,i+1,2)) for i in range(terms))


def chebyshev_matrix(terms):
    from flint import fmpz_mat
    table = [[0]*terms for _ in range(terms)]
    for i,row in enumerate(chebyshev_weights(terms)):
        for j,value in row:
            table[i][j] = value
    weights = fmpz_mat(table)
    return weights.transpose(),weights


def chebyshev_rows(cols, terms, unit, scale):
    from flint import fmpz_mat
    layout = Series(terms,None)
    nx,ny = layout.x_terms,layout.m_terms
    left,_ = chebyshev_matrix(nx)
    _,right = chebyshev_matrix(ny)
    indices = layout.indices
    denominator = 2*unit << (nx+ny-2)
    rows = []
    for column in cols:
        table = [[0]*ny for _ in range(nx)]
        for (i,j),(lo,hi) in zip(indices,column):
            table[i][j] = lo+hi
        cheb = left*fmpz_mat(table)*right
        rows.append([int(cheb[i,j])*scale//denominator for i,j in indices[1:]])
    return rows


@cache
def mesh_weights(terms, cells):
    rows = []
    for step in range(cells+1):
        x = 2*step-cells
        values = [1,x]
        for i in range(2,terms):
            values.append(2*x*values[-1]-cells**2*values[-2])
        rows.append(tuple(value*cells**(terms-1-i) for i,value in enumerate(values)))
    return rows


def linear_interval(values, weights):
    lo = hi = 0
    for (a,b),w in zip(values,weights):
        if w < 0:
            a,b = b,a
        lo += a*w
        hi += b*w
    return lo,hi


def chebyshev_bounds(poly, columns, tail, terms, cells=0):
    active = [(coefficient,column) for coefficient,column in zip(poly,columns) if coefficient]
    layout = Series(terms,None)
    nx,ny = layout.x_terms,layout.m_terms
    x_weights,y_weights = chebyshev_weights(nx),chebyshev_weights(ny)
    indices = layout.indices
    exact = {pair:[0,0] for pair in indices}
    derivatives = 0
    for n,(j,k) in enumerate(indices):
        lo = hi = 0
        for coefficient,column in active:
            a,b = column[n]
            if coefficient < 0:
                a,b = b,a
            lo += coefficient*a
            hi += coefficient*b
        if cells:
            derivatives += max(abs(lo),abs(hi))*(j*(j-1)+k*(k-1))
        for u,uweight in x_weights[j]:
            for v,vweight in y_weights[k]:
                weight = uweight*vweight
                end = exact[u,v]
                end[0] += lo*weight
                end[1] += hi*weight
    denominator = 1 << (nx+ny-2)
    error = denominator*tail*sum(map(abs,poly[1:]))
    center_lo,center_hi = exact[0,0]
    norm = sum(max(map(abs,pair)) for index,pair in exact.items() if index != (0,0))
    lo,hi = (center_lo-error-norm)//denominator, -(-(center_hi+error+norm)//denominator)
    if cells and lo < hi:
        row_table = [[exact.get((i,j),(0,0)) for i in range(nx)] for j in range(ny)]
        xweights,yweights = mesh_weights(nx,cells),mesh_weights(ny,cells)
        floor,ceiling = None,None
        for rx in xweights:
            partial = [linear_interval(row,rx) for row in row_table]
            for ry in yweights:
                a,b = linear_interval(partial,ry)
                floor = a if floor is None else min(floor,a)
                ceiling = b if ceiling is None else max(ceiling,b)
        mesh_denominator = denominator*cells**(nx+ny-2)
        # Linear interpolation on a segment of length 2/cells has error
        # <= max|f''|/(2*cells**2). Apply in each direction; the other
        # interpolation is a convex combination and cannot amplify error.
        pad = -(-derivatives//(2*cells**2))+error//denominator
        lo = max(lo,floor//mesh_denominator-pad)
        hi = min(hi,-(-ceiling//mesh_denominator)+pad)
    return lo,hi


@cache
def binomial_modulo(degree, prime):
    require(prime > degree and prime <= 127 and
            not any(prime%d == 0 for d in range(2,isqrt(prime)+1)), 'invalid prime modulus')
    return tuple(tuple(comb(x,k)%prime for k in range(degree+1)) for x in range(prime))


def exclude_bands(degree, indexed_polys, prime):
    """Return the indices of the polynomials proving that the bands cannot meet."""
    table = binomial_modulo(degree,prime)
    choices = []
    for index,(poly,lo,hi) in enumerate(indexed_polys):
        if hi < lo:
            return [index]
        if hi-lo+1 < prime:
            allowed = sum(1 << (v%prime) for v in range(lo,hi+1))
            terms = [(x,y,z,c%prime) for (x,y,z),c in zip(exponents(degree,3),poly) if c%prime]
            choices.append((hi-lo,index,allowed,terms))
    if not choices:
        return None
    # Collapse one Newton coordinate once per residue and re-use the
    # collapsed rows for all choices of the other two residues.
    choices.sort()
    used = set()
    for cx in table:
        first = []
        for _,index,allowed,terms in choices:
            partial = [[0]*(degree+1) for _ in range(degree+1)]
            for x,y,z,c in terms:
                partial[z][y] += cx[x]*c
            first.append((index,allowed,partial))
        for cy in table:
            filtered = range(prime)
            for index,allowed,partial in first:
                coefs = [(z,sum(a*b for a,b in zip(row,cy))%prime) for z,row in enumerate(partial)]
                active = [(z,c) for z,c in coefs if c]
                survivors = [k for k in filtered if allowed &
                             (1 << (sum(table[k][z]*c for z,c in active)%prime))]
                if len(survivors) != len(filtered):
                    used.add(index)
                if not survivors:
                    break
                filtered = survivors
            else:
                return None
    return sorted(used)


def verify(row):
    fields = {'block','degree','work_bits','q_shift','shear','transform','radius_shift','terms','polynomials'}
    require(__debug__ and isinstance(row,dict) and fields <= row.keys(),
            'invalid entire-surface certificate')
    geom = geometry(row['block'],row['degree'],row['work_bits'],row['q_shift'],row['shear'],row.get('chart'))
    transform = checked_transform(row['transform'])
    rank = len(exponents(geom.degree,3))
    polynomials = row['polynomials']
    require(isinstance(polynomials,list) and 0 < len(polynomials) <= rank and
            all(isinstance(p,list) and len(p) == rank and any(p) and
                all(type(v) is int and abs(v).bit_length() <= 2048 for v in p)
                for p in polynomials), 'invalid polynomials')
    cells = row.get('mesh',0)
    require(type(cells) is int and cells in (0,8,16,32), 'unsupported verification mesh')
    tail = ceil(geom.tail(transform,row['radius_shift'],row['terms'])*geom.grid.unit)
    columns = basis(geom,transform,row['terms'])
    intervals = [integer_interval(chebyshev_bounds(p,columns,tail,row['terms'],cells),geom.grid.unit)
                 for p in polynomials]
    if any(lo > hi for lo,hi in intervals):
        return
    if 'prime' in row:
        require(type(row['prime']) is int and exclude_bands(geom.degree,
                [(poly,lo,hi) for poly,(lo,hi) in zip(polynomials,intervals)],row['prime'])
                is not None,'polynomial residue bands have a common point')
        return
    require(all(v == (0,0) for v in intervals) and
            excludes_residues(geom.degree,polynomials) is not None, 'integer solutions not excluded')


def reduce(lattice, delta, flatter):
    rank = len(lattice)
    columns = len(lattice[0])
    if not flatter:
        reduced,backend = reduce_lattice(lattice,delta)
        return [[int(reduced[i,j]) for j in range(columns)] for i in range(rank)],backend
    encoded = '[\n'+'\n'.join('['+' '.join(map(str,row))+']' for row in lattice)+'\n]\n'
    result = subprocess.run([flatter,'-delta',str(delta)],input=encoded,text=True,
                            capture_output=True,check=True)
    rows = (line.strip(' [\n\r\t') for line in result.stdout.split(']'))
    reduced = [[int(v) for v in line.split()] for line in rows if line]
    require(len(reduced) == rank and all(len(row) == columns for row in reduced),
            'unexpected reducer dimensions')
    return reduced,'flatter'


def geometry(block, degree, work_bits, shift, shear, chart):
    if chart is None:
        return Entire(block,degree,work_bits,shift,shear)
    require(chart in ('mantissa','diagonal') and shear == 0,'invalid surface chart')
    return MantissaChart(block,degree,work_bits,shift,chart == 'diagonal')


def generate(block, degree, work_bits, delta, shift=52, shear=4,
             bands=False, tensor=False, mesh=0, flatter=None, chart=None):
    geom = geometry(block,degree,work_bits,shift,shear,chart)
    transform = geom.adapt()
    radius, terms = geom.choose_terms(transform,tensor)
    start = process_time()
    cols = basis(geom,transform,terms)
    expansion = process_time()-start
    unit = geom.grid.unit
    scale = 1 << work_bits
    rank = len(cols)-1
    tail = ceil(geom.tail(transform,radius,terms)*unit)
    rows = chebyshev_rows(cols[1:],terms,unit,scale)
    # Remove coordinates below the lattice's working grid. The rational
    # checker always retains and bounds their original intervals.
    used = [i for i,column in enumerate(zip(*rows)) if max(map(abs,column)) > 1]
    size = len(used)
    penalty = size+2
    lattice = [[row[j] for j in used]+[penalty*(i==j) for j in range(rank)]
               for i,row in enumerate(rows)]
    start = process_time()
    started = perf_counter()
    reduced, backend = reduce(lattice,delta,flatter)
    reduction = process_time()-start
    reduction_wall = perf_counter()-started
    estimates = sorted((sum(map(abs,row[:size])),i) for i,row in enumerate(reduced))
    selected = None
    small = []
    bounded = []
    prime = None
    for approx,i in estimates:
        if approx >= (64 if bands else 1)*scale or len(bounded) >= 32:
            break
        polynomial = [0]+[v//penalty for v in reduced[i][size:]]
        exact = chebyshev_bounds(polynomial,cols,tail,terms,mesh)
        lo,hi = integer_interval(exact,unit)
        if lo > hi:
            selected = [polynomial]
            break
        if lo == hi:
            polynomial[0] -= lo
            small.append(polynomial)
            lo = hi = 0
        if bands and hi-lo+1 < 127:
            bounded.append((polynomial,lo,hi))
    if selected is None and small:
        selected = excludes_residues(degree,small)
    if selected is None and bands:
        for trial in (17,31,47,67,97,127):
            if trial <= degree or sum(hi-lo+1 < trial for _,lo,hi in bounded) < 2:
                continue
            indices = exclude_bands(degree,bounded,trial)
            if indices:
                selected = [bounded[i][0] for i in indices]
                prime = trial
                break
    result = dict(block=block,degree=degree,work_bits=work_bits,q_shift=shift,
                  transform=transform,radius_shift=radius,terms=terms,shear=shear)
    if chart is not None:
        result['chart'] = chart
    if mesh:
        result['mesh'] = mesh
    if selected:
        result['polynomials'] = selected
        if prime is not None:
            result['prime'] = prime
        verify(result)
    return dict(result=result, expansion_s=expansion, reduction_s=reduction,
                reduction_wall_s=reduction_wall,
                smallest_bits=estimates[0][0].bit_length()-1-work_bits,
                backend=backend, small=len(small), rank=rank, columns=size,
                widths=[hi-lo+1 for _,lo,hi in bounded])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--width',type=int,default=20)
    parser.add_argument('--midpoint-width',type=int)
    parser.add_argument('--degree',type=int,default=6)
    parser.add_argument('--work',type=int,default=128)
    parser.add_argument('--seed',type=int,default=2040)
    parser.add_argument('--delta',type=float,default=.92)
    parser.add_argument('--inverse',action='store_true')
    parser.add_argument('--q-shift',type=int,default=52)
    parser.add_argument('--shear',type=int,default=4)
    charts = parser.add_mutually_exclusive_group()
    charts.add_argument('--mantissa-chart',dest='chart',action='store_const',const='mantissa')
    charts.add_argument('--diagonal-chart',dest='chart',action='store_const',const='diagonal')
    parser.add_argument('--bands',action='store_true')
    parser.add_argument('--tensor',action='store_true')
    parser.add_argument('--mesh',type=int,choices=(0,8,16,32),default=0)
    parser.add_argument('--flatter',type=str)
    parser.add_argument('--verify',type=Path)
    parser.add_argument('--flint-products',action='store_true')
    parser.add_argument('--block',type=int,nargs=6,metavar=('EX','BX','EM','BM','WX','WM'))
    args = parser.parse_args()
    require(__debug__, 'enable interval assertions')
    if args.flint_products or not args.verify:
        use_flint_products()
    if args.verify:
        if args.verify.suffix == '.gz':
            with gzip.open(args.verify,'rt',encoding='ascii') as stream:
                document = json.load(stream)
        else:
            document = json.loads(args.verify.read_text())
        require(isinstance(document,dict), 'expected a certificate object')
        verify(document.get('result',document))
        print('VERIFIED_BLOCK')
        return 0
    block = args.block or sample_blocks(args.width,1,args.seed,args.inverse,args.midpoint_width)[0]
    report = generate(block,args.degree,args.work,args.delta,args.q_shift,
                      0 if args.chart else args.shear,args.bands,args.tensor,args.mesh,args.flatter,args.chart)
    print(json.dumps(report),flush=True)
    return 0 if 'polynomials' in report['result'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
