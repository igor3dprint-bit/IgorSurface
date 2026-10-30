"""License-independent cage topology and progressive limit-surface fitting (cm)."""
import heapq
import math
from collections import defaultdict, deque


def sub(a, b): return tuple(x-y for x,y in zip(a,b))
def add(a, b): return tuple(x+y for x,y in zip(a,b))
def mul(a, s): return tuple(x*s for x in a)
def dot(a, b): return sum(x*y for x,y in zip(a,b))
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def length(a): return math.sqrt(dot(a,a))
def mean(points):
    points = list(points)
    return tuple(sum(p[k] for p in points)/len(points) for k in range(3))


def normal(verts, face):
    return cross(sub(verts[face[1]],verts[face[0]]),sub(verts[face[2]],verts[face[0]]))


def topology(faces):
    edges = defaultdict(list)
    for fi,f in enumerate(faces):
        for a,b in zip(f,f[1:]+f[:1]):
            edges[min(a,b),max(a,b)].append((fi,a,b))
    return edges


def validate(verts, faces):
    """Reject bad winding, non-manifold edges/fans and degenerate triangles."""
    if not verts or not faces or any(len(p)!=3 or not all(math.isfinite(c) for c in p) for p in verts):
        raise ValueError('Malha vazia ou coordenadas inválidas.')
    fans = [set() for p in verts]
    for fi,f in enumerate(faces):
        if len(f) not in (3,4) or len(set(f)) != len(f) or any(v<0 or v>=len(verts) for v in f):
            raise ValueError('Face inválida; use Preparar Scan.')
        if length(normal(verts,f)) < 1e-15:
            raise ValueError('Face degenerada; use Preparar Scan.')
        for v in f: fans[v].add(fi)
    neighbors = [defaultdict(set) for p in verts]
    border = defaultdict(int)
    for (a,b),use in topology(faces).items():
        if len(use)>2 or (len(use)==2 and use[0][1:]==use[1][1:]):
            raise ValueError('Malha não manifold ou orientação inconsistente; use Preparar Scan.')
        if len(use)==1:
            border[a]+=1; border[b]+=1
        else:
            x,y = use[0][0],use[1][0]
            for v in (a,b): neighbors[v][x].add(y); neighbors[v][y].add(x)
    if any(n!=2 for n in border.values()):
        raise ValueError('Borda não manifold; use Preparar Scan.')
    for v,fan in enumerate(fans):
        if not fan: raise ValueError('Vértice isolado.')
        seen,pending = set(),[next(iter(fan))]
        while pending:
            f=pending.pop()
            if f not in seen:
                seen.add(f); pending.extend(neighbors[v][f]-seen)
        if seen!=fan: raise ValueError('Vértice não manifold; use Preparar Scan.')
    return True


def compact(verts, faces):
    used=sorted({v for f in faces for v in f})
    ids={old:i for i,old in enumerate(used)}
    return [verts[v] for v in used], [tuple(ids[v] for v in f) for f in faces]


def clean(verts, faces):
    """Weld STL duplicates (1e-8 cm), remove duplicate/sliver faces, orient fans."""
    welded, lookup, remap = [],{},[]
    for p in verts:
        if len(p)!=3 or not all(math.isfinite(c) for c in p):
            raise ValueError('Coordenada inválida na malha.')
        key=tuple(round(c/1e-8) for c in p)
        if key not in lookup:
            lookup[key]=len(welded); welded.append(tuple(p))
        remap.append(lookup[key])
    out,seen = [],set()
    for f in faces:
        if any(v<0 or v>=len(remap) for v in f): raise ValueError('Índice de malha inválido.')
        for k in range(1,len(f)-1):
            t=(remap[f[0]],remap[f[k]],remap[f[k+1]])
            key=tuple(sorted(t))
            if len(set(t))==3 and key not in seen and length(normal(welded,t))>1e-15:
                out.append(t); seen.add(key)
    edges=topology(out)
    if any(len(use)>2 for use in edges.values()):
        raise ValueError('A malha tem arestas não manifold. Use Preparar Scan.')
    adjacent=defaultdict(list)
    for use in edges.values():
        if len(use)==2:
            (a,x,y),(b,u,v)=use
            adjacent[a].append((b,x==u)); adjacent[b].append((a,x==u))
    flips={}
    for start in range(len(out)):
        if start in flips: continue
        flips[start]=False; queue=deque([start])
        while queue:
            a=queue.popleft()
            for b,same in adjacent[a]:
                flip=flips[a]^same
                if b in flips and flips[b]!=flip: raise ValueError('Malha não orientável.')
                if b not in flips: flips[b]=flip; queue.append(b)
    return compact(welded,[tuple(reversed(f)) if flips[i] else f for i,f in enumerate(out)])


def shells(verts, faces):
    """Split by shared edges, duplicating point contacts between separate shells."""
    adjacent=defaultdict(set)
    for use in topology(faces).values():
        for a,_,_ in use:
            adjacent[a].update(b for b,_,_ in use if a!=b)
    remaining=set(range(len(faces))); out=[]
    while remaining:
        start=min(remaining); remaining.remove(start); queue=[start]; group=[]
        while queue:
            a=queue.pop(); group.append(faces[a])
            for b in adjacent[a]&remaining:
                remaining.remove(b); queue.append(b)
        v,f=compact(verts,group); validate(v,f); out.append((v,f))
    return sorted(out,key=lambda s:len(s[1]),reverse=True)


def decimate(verts, faces, target, progress=None):
    """Shortest-edge collapse with link condition, boundary and normal guards.

    Pure-Python fallback. The target is soft: topology takes priority over count.
    """
    validate(verts,faces)
    if any(len(f)!=3 for f in faces): raise ValueError('A redução requer triângulos.')
    points=list(verts); active={i:tuple(f) for i,f in enumerate(faces)}
    if target<4: target=4
    while len(active)>target:
        items=list(active.items()); polys=[f for i,f in items]
        edges=topology(polys); around=defaultdict(set); boundary=set()
        for (a,b),use in edges.items():
            around[a].add(b); around[b].add(a)
            if len(use)==1: boundary.update((a,b))
        candidates=[(dot(sub(points[a],points[b]),sub(points[a],points[b])),a,b) for a,b in edges]
        heapq.heapify(candidates); accepted=False
        while candidates:
            _,a,b=heapq.heappop(candidates); use=edges[a,b]
            if (a in boundary)!=(b in boundary) or (a in boundary and len(use)!=1): continue
            opposite={v for fi,x,y in use for v in polys[fi] if v not in (a,b)}
            if around[a]&around[b] != opposite: continue
            p=mean([points[a],points[b]])
            updated={}; good=True
            for fi,f in items:
                if a not in f and b not in f: continue
                g=tuple(a if v==b else v for v in f)
                if len(set(g))<3: updated[fi]=None; continue
                old=normal(points,f)
                pp=[p if v==a else points[v] for v in g]
                nn=cross(sub(pp[1],pp[0]),sub(pp[2],pp[0]))
                if dot(nn,old)<=0.1*length(nn)*length(old) or length(nn)<1e-15:
                    good=False; break
                updated[fi]=g
            if not good: continue
            trial=[updated.get(fi,f) for fi,f in items if updated.get(fi,f) is not None]
            vp=list(points); vp[a]=p
            cv,cf=compact(vp,trial)
            try: validate(cv,cf)
            except ValueError: continue
            points=vp
            for fi,f in updated.items():
                if f is None: del active[fi]
                else: active[fi]=f
            accepted=True
            if progress and len(active)%100==0: progress(len(active))
            break
        if not accepted: break
    return compact(points,list(active.values()))


def merge_quads(verts, faces):
    """Pair nearly coplanar convex triangles across their common longest edge."""
    used=set(); out=[]
    for (a,b),use in sorted(topology(faces).items()):
        if len(use)!=2: continue
        i,j=use[0][0],use[1][0]
        if i in used or j in used: continue
        f,g=faces[i],faces[j]
        edge_len=length(sub(verts[a],verts[b]))
        if any(length(sub(verts[x],verts[y]))>edge_len*1.001 for h in (f,g) for x,y in zip(h,h[1:]+h[:1])): continue
        nf,ng=normal(verts,f),normal(verts,g)
        if dot(nf,ng)<0.98*length(nf)*length(ng): continue
        border={}
        for h in (f,g):
            for x,y in zip(h,h[1:]+h[:1]):
                if {x,y}!={a,b}: border[x]=y
        start=min(border); q=[start]
        while len(q)<4: q.append(border[q[-1]])
        if border[q[-1]]!=start or len(set(q))!=4: continue
        if any(dot(cross(sub(verts[q[(k+1)%4]],verts[q[k]]),sub(verts[q[(k+2)%4]],verts[q[(k+1)%4]])),nf)<=1e-15 for k in range(4)): continue
        out.append(tuple(q)); used.update((i,j))
    out.extend(f for i,f in enumerate(faces) if i not in used)
    validate(verts,out)
    return out


def quadrangulate(verts, faces):
    """Conforming face-center split: one quad per original polygon corner.

    Planar linear splits preserve the cage shape and avoid proprietary tri caps.
    Shared edges have exactly one midpoint; holes and shell topology are kept.
    """
    points=list(verts); mids={}; out=[]
    for f in faces:
        center=len(points); points.append(mean(verts[v] for v in f))
        for a,b in zip(f,f[1:]+f[:1]):
            key=min(a,b),max(a,b)
            if key not in mids:
                mids[key]=len(points); points.append(mean([verts[a],verts[b]]))
        for k,a in enumerate(f):
            b,c=f[(k+1)%len(f)],f[k-1]
            out.append((a,mids[min(a,b),max(a,b)],center,mids[min(a,c),max(a,c)]))
    validate(points,out)
    return points,out


def limit_positions(verts, faces):
    """Catmull-Clark limit at cage vertices; mixed faces use one quad split.

    Compute one CC subdivision locally, then the exact quad-ring limit stencil
    (n*n*P' + 4*sum(edge points) + sum(face points)) / (n*(n+5)).
    For mixed/triangle T-Spline caps this is an approximation, not Fusion's
    proprietary cap evaluator. Open borders use a cubic boundary stencil;
    valence-two corners stay fixed, matching the tested legacy end conditions.
    """
    edges=topology(faces); incident=[[] for p in verts]; neighbors=[set() for p in verts]
    border=[[] for p in verts]; centers=[mean(verts[v] for v in f) for f in faces]
    edge_points={}
    for (a,b),use in edges.items():
        neighbors[a].add(b); neighbors[b].add(a)
        if len(use)==1:
            border[a].append(b); border[b].append(a)
        edge_points[a,b]=mean([verts[a],verts[b]]+[centers[f] for f,x,y in use])
    for fi,f in enumerate(faces):
        for v in f: incident[v].append(fi)
    out=[]
    for i,p in enumerate(verts):
        if border[i]:
            out.append(p if len(neighbors[i])==2 else mul(add(mul(p,4),add(verts[border[i][0]],verts[border[i][1]])),1/6))
            continue
        n=len(neighbors[i]); fc=mean(centers[f] for f in incident[i])
        mid=mean(mean([p,verts[j]]) for j in neighbors[i])
        first=mul(add(add(fc,mul(mid,2)),mul(p,n-3)),1/n)
        ep=mean(edge_points[min(i,j),max(i,j)] for j in neighbors[i])
        out.append(mul(add(add(mul(first,n),mul(ep,4)),fc),1/(n+5)))
    return out


def fit(verts, faces, scan, iterations=4, progress=None):
    """Damped progressive interpolation, rejecting face flips and worse steps."""
    validate(verts,faces); points=list(verts); history=[]
    lengths=[[] for p in points]
    for a,b in topology(faces):
        size=length(sub(points[a],points[b]))
        lengths[a].append(size); lengths[b].append(size)
    # A tiny sliver elsewhere in a scan must not freeze the entire fit.
    step_sizes=[0.3*sum(values)/len(values) for values in lengths]
    def residual(p):
        limits=limit_positions(p,faces)
        delta=[sub(scan.closest(q)[0],q) for q in limits]
        return delta,math.sqrt(sum(dot(d,d) for d in delta)/len(delta))
    delta,error=residual(points); history.append(error)
    for step in range(max(0,min(int(iterations),20))):
        if progress: progress(step,iterations)
        old_normals=[normal(points,f) for f in faces]
        improved=False
        for damping in (0.8,0.4,0.2,0.1):
            trial=[add(p,mul(d,min(damping,size/max(length(d),1e-20)))) for p,d,size in zip(points,delta,step_sizes)]
            # Lock a problematic local fan, not every vertex in the scan.
            for guard in range(8):
                bad={v for f,old in zip(faces,old_normals)
                     if dot(normal(trial,f),old)<=0.1*length(normal(trial,f))*length(old) for v in f}
                if not bad: break
                for v in bad: trial[v]=points[v]
            if bad: continue
            new_delta,new_error=residual(trial)
            if new_error<error:
                points,delta,error=trial,new_delta,new_error; improved=True; break
        history.append(error)
        if not improved or error<1e-8: break
    validate(points,faces)
    return points,history
