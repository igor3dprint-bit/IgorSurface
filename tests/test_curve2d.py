import sys, math, random; sys.path.insert(0, 'IgorSurface')
from lib.curve2d import chain, fit
# rectangle 30x20 (as 40 tiny segments) + hole circle r=5 (96 segs), shuffled and reversed like a raw section
segs = []
def poly(pts, closed=True):
    for i in range(len(pts) - (0 if closed else 1)):
        segs.append((pts[i], pts[(i+1) % len(pts)]))
rect = [(x, 0.0) for x in range(0, 30)] + [(30.0, y) for y in range(0, 20)] + [(x, 20.0) for x in range(30, 0, -1)] + [(0.0, y) for y in range(20, 0, -1)]
poly([(float(x), float(y)) for x, y in rect])
poly([(15 + 5*math.cos(2*math.pi*i/96), 10 + 5*math.sin(2*math.pi*i/96)) for i in range(96)])
# an open profile: line, quarter arc r=4, line
prof = [(40.0 + i, 0.0) for i in range(6)] + [(45 + 4*math.sin(t*math.pi/40), 4 - 4*math.cos(t*math.pi/40)) for t in range(1, 21)] + [(49.0, 4.0 + i) for i in range(1, 6)]
poly(prof, closed=False)
random.Random(1).shuffle(segs); segs = [s if random.random() < .5 else (s[1], s[0]) for s in segs]
chains = chain(segs)
assert len(chains) == 3, [len(c[0]) for c in chains]
res = sorted([fit(p, c, 0.01) for p, c in chains], key=len)
kinds = [[it[0] for it in r] for r in res]
print(kinds)
assert ['circle'] in kinds and abs([r for r in res if r[0][0] == 'circle'][0][0][2] - 5) < 1e-3
assert ['line'] * 4 in kinds, kinds
assert ['line', 'arc', 'line'] in kinds or ['line', 'arc', 'line'][::-1] in kinds, kinds
print('curve2d ok')
import time
rnd = random.Random(5)
noisy = [(x + rnd.gauss(0, .003), y + rnd.gauss(0, .003)) for x, y in [(15 + 5*math.cos(2*math.pi*i/400), 10 + 5*math.sin(2*math.pi*i/400)) for i in range(400)]]
r = fit(noisy, True, 0.02); assert r[0][0] == 'circle' and abs(r[0][2] - 5) < 0.005, r
big = [(i*0.01, 0.0) for i in range(2000)] + [(20 + 3*math.sin(t/300*math.pi/2), 3 - 3*math.cos(t/300*math.pi/2)) for t in range(1, 301)]
t = time.perf_counter(); r = fit(big, False, 0.01); dt = time.perf_counter() - t
print('noisy circle ok; 2300-pt profile ->', [x[0] for x in r], '%.2fs' % dt)
