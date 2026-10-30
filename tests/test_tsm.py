"""Independent topology/coordinate checks against Fusion's captured planes."""
import importlib.util
import math
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('tested_tsm', ROOT / 'IgorSurface/commands/freeform/tsm.py')
tsm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tsm)


def records(text, tag):
    return [line.split()[1:] for line in text.splitlines() if line.split() and line.split()[0] == tag]


def inspect(text):
    links = [tuple(map(int, row)) for row in records(text, 'l')]
    edges = records(text, 'e')
    vertices = records(text, 'v')
    faces = records(text, 'f')
    points = [tuple(map(float, row[:3])) for row in records(text, '0g')]
    primary = {int(row[1]): points[g] for g, row in enumerate(
        row for row in records(text, '0m') if row[0] in {'gv','gvp'}) if row[0] == 'gvp'}
    assert len(primary) == len(vertices)
    for h, (prev,nxt,twin,v,f,e,flag) in enumerate(links):
        assert links[prev][1] == h and links[nxt][0] == h
        assert twin != h and links[twin][2] == h
        assert links[twin][5] == e
        assert links[nxt][3] == links[twin][3]
        assert links[links[twin][1]][3] == v
        assert 0 <= v < len(vertices) and -1 <= f < len(faces)
        assert 0 <= e < len(edges)
    cycles = []
    for fi, row in enumerate(faces):
        start = h = int(row[0])
        seen = []
        while h not in seen:
            assert links[h][4] == fi
            seen.append(h)
            h = links[h][1]
        assert h == start and len(seen) in (3,4)
        assert set(seen) == {i for i,l in enumerate(links) if l[4] == fi}
        cycle = tuple(primary[links[i][3]] for i in seen)
        cycles.append(min(cycle[k:] + cycle[:k] for k in range(len(cycle))))
    for e,row in enumerate(edges):
        assert links[int(row[0])][5] == e and float(row[1]) == 1
    for v,row in enumerate(vertices):
        assert links[int(row[0])][3] == v
        assert row[1] in {'EAST','WEST','NORTH','SOUTH'}
    boundary = {row[5] for row in links if row[4] == -1}
    assert {int(row[0]) for row in records(text,'ec')} == boundary
    return sorted(cycles), len(edges), len(vertices), len(links), boundary


def grid(nx,ny):
    p = [(x,y,0) for y in range(ny+1) for x in range(nx+1)]
    f = []
    for y in range(ny):
        for x in range(nx):
            a = y*(nx+1)+x
            f.append([a,a+1,a+nx+2,a+nx+1])
    return p,f


class WriterTests(unittest.TestCase):
    def test_legacy_rhino_dialect(self):
        p,f = grid(1,1)
        text = tsm.write(p,f)
        self.assertIn('\ncap-type 1\n',text)
        self.assertIn('\nforce-bezier-end-conditions 1\n',text)
        self.assertTrue(text.startswith('#TS0200\n\ndegree 3\n'))
        for tag in ['100edges','100verts','50000grip','end-conditions','star-knot-rule']:
            self.assertEqual(records(text,tag),[])

    def test_planes_match_fusion_structure(self):
        for name,nx,ny in [('q1',1,1),('q2',2,1),('plane',2,2)]:
            with self.subTest(name=name):
                expected = inspect((ROOT/'tests'/f'{name}.tsm').read_text(encoding='utf-8'))
                p,f = grid(nx,ny)
                actual = inspect(tsm.write(p,f))
                self.assertEqual(actual[:4], expected[:4])
                self.assertEqual(len(actual[4]),len(expected[4]))

    def test_coordinates_are_cm_not_scaled(self):
        p,f = grid(1,1)
        p = [(x*1.25-7,y*0.5+2,0.2*math.sin(x)) for x,y,z in p]
        output = tsm.write(p,f)
        self.assertEqual([tuple(map(float,row[:3])) for row in records(output,'0g')],p)
        self.assertEqual(len(records(output,'0g')),len(p))
        self.assertEqual(len(records(output,'0m')),len(p)+1)
        self.assertEqual(output,tsm.write(p,f))

    def test_hole_and_multiple_boundary_loops(self):
        p,f = grid(3,3)
        f.pop(4)
        result = inspect(tsm.write(p,f))
        self.assertEqual(len(result[4]),16)

    def test_disconnected_components(self):
        p,f = grid(1,1)
        output=tsm.write(p+[(x+3,y,z) for x,y,z in p],f+[[v+4 for v in f[0]]])
        self.assertEqual(len(inspect(output)[0]),2)

    def test_triangles_share_an_edge(self):
        p,f = grid(1,1)
        self.assertEqual(len(inspect(tsm.write(p,[[0,1,3],[0,3,2]]))[0]),2)

    def test_bad_coordinates(self):
        for p in [[],[(0,0)],[(0,0,float('nan'))],[(0,0,float('inf'))]]:
            with self.subTest(p=p),self.assertRaises(ValueError):
                tsm.write(p,[[0,1,2]])

    def test_bad_faces(self):
        p,f = grid(1,1)
        for bad in [[],[[0,1]],[[0,1,2,3,0]],[[0,1,1]],[[0,1,8]],
                    [[0,1,-1]],[[0,1,2.5]],[[0,1,3,2],[0,1,2]]]:
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                tsm.write(p,bad)

    def test_isolated_vertex(self):
        p,f = grid(1,1)
        with self.assertRaisesRegex(ValueError,'Isolated'):
            tsm.write(p+[(10,10,10)],f)

    def test_zero_length_edge(self):
        with self.assertRaisesRegex(ValueError,'Zero-length'):
            tsm.write([(0,0,0),(0,0,0),(1,1,0)],[[0,1,2]])

    def test_open_bow_tie(self):
        p=[(0,0,0),(1,0,0),(0,1,0),(-1,0,0),(0,-1,0)]
        with self.assertRaisesRegex(ValueError,'Non-manifold'):
            tsm.write(p,[[0,1,2],[0,3,4]])

    def test_closed_bow_tie(self):
        p=[(0,0,0),(1,0,0),(0,1,0),(0,0,1),(-1,0,0),(0,-1,0),(0,0,-1)]
        tetra=[[0,2,1],[0,1,3],[1,2,3],[2,0,3]]
        f=tetra+[[{0:0,1:4,2:5,3:6}[v] for v in face] for face in tetra]
        with self.assertRaisesRegex(ValueError,'vertex fan'):
            tsm.write(p,f)


if __name__ == '__main__':
    unittest.main()
