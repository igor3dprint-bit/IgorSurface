"""Offline topology preservation and limit fitting tests; no Fusion imports."""
import math
import sys
import unittest
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from IgorSurface.lib import cage


def sphere(n=3):
    corners=[(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
    sides=[[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]
    verts=[]; faces=[]; lookup={}
    for side in sides:
        a,b,c,d=[corners[i] for i in side]; grid=[]
        for y in range(n+1):
            row=[]
            for x in range(n+1):
                u,v=x/n,y/n
                p=tuple((1-u)*(1-v)*a[k]+u*(1-v)*b[k]+u*v*c[k]+(1-u)*v*d[k] for k in range(3))
                key=tuple(round(c,8) for c in p)
                if key not in lookup:
                    lookup[key]=len(verts); verts.append(cage.mul(p,1/cage.length(p)))
                row.append(lookup[key])
            grid.append(row)
        faces.extend((grid[y][x],grid[y][x+1],grid[y+1][x+1],grid[y+1][x]) for y in range(n) for x in range(n))
    return verts,faces


def cylinder(n=16, rows=3):
    verts=[(math.cos(2*math.pi*x/n),math.sin(2*math.pi*x/n),y/rows) for y in range(rows+1) for x in range(n)]
    faces=[(y*n+x,y*n+(x+1)%n,(y+1)*n+(x+1)%n,(y+1)*n+x) for y in range(rows) for x in range(n)]
    return verts,faces


class Sphere:
    def closest(self,p): return cage.mul(p,1/cage.length(p)),0


class Cylinder:
    def closest(self,p):
        r=math.hypot(p[0],p[1])
        return (p[0]/r,p[1]/r,max(0,min(1,p[2]))),0


class CageTests(unittest.TestCase):
    def test_all_quad_split_keeps_topology(self):
        v,f=cage.clean(*sphere(2))
        qv,qf=cage.quadrangulate(v,f)
        self.assertTrue(all(len(q)==4 for q in qf))
        self.assertEqual(len(qf),3*len(f))
        self.assertEqual(len(qv)-len(cage.topology(qf))+len(qf),2)
        self.assertTrue(cage.validate(qv,qf))

    def test_decimation_closed_topology(self):
        v,f=cage.clean(*sphere(3)); original=(list(v),list(f))
        reduced,polys=cage.decimate(v,f,60)
        self.assertTrue(cage.validate(reduced,polys))
        self.assertLessEqual(len(polys),60)
        self.assertEqual(len(reduced)-len(cage.topology(polys))+len(polys),2)
        self.assertTrue(all(len(use)==2 for use in cage.topology(polys).values()))
        self.assertEqual((v,f),original)

    def test_decimation_preserves_open_borders(self):
        v,f=cage.clean(*cylinder(12,3))
        v,f=cage.decimate(v,f,40)
        self.assertTrue(cage.validate(v,f))
        self.assertLessEqual(len(f),40)
        self.assertEqual(len(v)-len(cage.topology(f))+len(f),0)
        self.assertTrue(any(len(use)==1 for use in cage.topology(f).values()))

    def test_sphere_fitting_reduces_limit_error(self):
        v,f=sphere(3)
        fitted,history=cage.fit(v,f,Sphere(),4)
        self.assertTrue(cage.validate(fitted,f))
        self.assertLess(history[-1],history[0]*0.3)
        self.assertTrue(all(b<=a for a,b in zip(history,history[1:])))

    def test_cylinder_fitting_reduces_limit_error(self):
        v,f=cylinder()
        fitted,history=cage.fit(v,f,Cylinder(),4)
        self.assertTrue(cage.validate(fitted,f))
        self.assertLess(history[-1],history[0]*0.3)

    def test_disconnected_and_point_contacts_split(self):
        v=[(0,0,0),(1,0,0),(0,1,0),(-1,0,0),(0,-1,0)]
        parts=cage.shells(v,[(0,1,2),(0,3,4)])
        self.assertEqual(len(parts),2)
        self.assertTrue(all(cage.validate(v,f) for v,f in parts))

    def test_welding_dedup_and_orientation(self):
        v=[(0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,0)]
        v,f=cage.clean(v,[(0,1,2),(4,3,2),(0,1,2)])
        self.assertEqual(len(v),4); self.assertEqual(len(f),2)
        self.assertTrue(cage.validate(v,f))
        self.assertEqual(len(cage.merge_quads(v,f)),1)

    def test_nonmanifold_rejected(self):
        v=[(0,0,0),(1,0,0),(0,1,0),(0,-1,0),(0,0,1)]
        with self.assertRaises(ValueError): cage.clean(v,[(0,1,2),(1,0,3),(0,1,4)])

    def test_zero_iterations_preserves_cage(self):
        v,f=sphere(2)
        out,h=cage.fit(v,f,Sphere(),0)
        self.assertEqual(out,v); self.assertEqual(len(h),1)


if __name__=='__main__': unittest.main(verbosity=2)
