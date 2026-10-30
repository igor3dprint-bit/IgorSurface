import sys
from unittest import mock
adsk = mock.MagicMock(); sys.modules.update({'adsk': adsk, 'adsk.core': adsk.core, 'adsk.fusion': adsk.fusion})
sys.path.insert(0, '.')
from IgorSurface.commands.quadPatch.entry import faces_from_edges as F
key = lambda fs: sorted(sorted(f) for f in fs)
# 2x1 strip of quads sharing an edge (nodes 0-1-2 / 3-4-5)
strip = [(0, 1), (1, 2), (3, 4), (4, 5), (0, 3), (1, 4), (2, 5)]
assert key(F(strip)) == [[0, 1, 3, 4], [1, 2, 4, 5]], F(strip)
# quad with a diagonal = 2 triangles, no quad
assert key(F([(0, 1), (1, 2), (2, 3), (3, 0), (0, 2)])) == [[0, 1, 2], [0, 2, 3]]
# open polyline: no face; loop order is usable as a boundary
assert F([(0, 1), (1, 2), (2, 3)]) == []
f = F([(0, 1), (1, 2), (2, 3), (3, 0)])[0]
assert all(frozenset((f[i], f[(i+1) % 4])) in {frozenset(e) for e in [(0, 1), (1, 2), (2, 3), (3, 0)]} for i in range(4))
print('faces_from_edges ok')
