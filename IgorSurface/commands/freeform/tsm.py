"""Serialize a manifold control cage using Fusion-compatible legacy Rhino TSM.

Coordinates are centimeters, as measured with addByTSMDescription in Fusion.
The legacy ``units 1 meters`` header is retained deliberately: Fusion uses the
numeric grip coordinates directly in its native centimeter space.
"""
import math
import operator


def write(verts, faces):
    """Return cubic TSM text for a smooth quad/triangle control cage.

    Open boundaries and disconnected manifold components are supported.
    Invalid indices, inconsistent winding, isolated vertices, zero-length
    edges, and non-manifold edges or vertex fans raise ValueError.
    No welding, repair, coordinate scaling, or crease insertion is performed.
    """
    try:
        points = [tuple(float(c) for c in p) for p in verts]
        polygons = [tuple(operator.index(v) for v in f) for f in faces]
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('Cage coordinates and face indices must be numeric.') from exc
    if not points or not polygons:
        raise ValueError('The cage must contain vertices and faces.')
    if any(len(p) != 3 or not all(math.isfinite(c) for c in p) for p in points):
        raise ValueError('Each vertex must contain three finite coordinates.')
    outgoing = [[] for _ in points]
    incident = [set() for _ in points]
    directed = {}
    links, edges, face_links = [], [], []
    for fi, face in enumerate(polygons):
        if len(face) not in (3, 4) or len(set(face)) != len(face):
            raise ValueError('Each face must have three or four distinct indices.')
        if any(v < 0 or v >= len(points) for v in face):
            raise ValueError('Face index is outside the vertex array.')
        cycle = []
        for pos, a in enumerate(face):
            b = face[(pos + 1) % len(face)]
            if points[a] == points[b]:
                raise ValueError('Zero-length cage edge.')
            if (a, b) in directed:
                raise ValueError('Inconsistent winding or non-manifold edge.')
            h = len(links)
            twin = directed.get((b, a), -1)
            if twin >= 0:
                edge = links[twin][5]
                links[twin][2] = h
            else:
                edge = len(edges)
                edges.append(h)
            links.append([-1, -1, twin, a, fi, edge, 0])
            directed[a, b] = h
            outgoing[a].append(h)
            incident[a].add(fi)
            cycle.append(h)
        for pos, h in enumerate(cycle):
            links[h][0] = cycle[pos - 1]
            links[h][1] = cycle[(pos + 1) % len(cycle)]
        face_links.append(cycle[0])
    if any(not fan for fan in outgoing):
        raise ValueError('Isolated vertices are not supported.')

    # Add the exterior half-edges and close every boundary loop.
    boundary = {}
    boundary_in = {}
    boundary_edges = []
    for h in range(len(links)):
        if links[h][2] != -1:
            continue
        a = links[h][3]
        b = links[links[h][1]][3]
        if b in boundary or a in boundary_in:
            raise ValueError('Non-manifold boundary vertex.')
        twin = len(links)
        links[h][2] = twin
        links.append([-1, -1, h, b, -1, links[h][5], 0])
        boundary[b] = twin
        boundary_in[a] = twin
        outgoing[b].append(twin)
        boundary_edges.append(links[h][5])
    if set(boundary) != set(boundary_in):
        raise ValueError('Open boundary chain is not a manifold cage.')
    for a, h in boundary.items():
        target = links[links[h][2]][3]
        links[h][0] = boundary_in[a]
        links[h][1] = boundary[target]
        links[h][6] = max(0, 4 - len(outgoing[a]))

    # A closed bow-tie can have valid edges but disconnected vertex fans.
    for vertex, fan in enumerate(incident):
        neighbors = {f: set() for f in fan}
        for h in outgoing[vertex]:
            f, other = links[h][4], links[links[h][2]][4]
            if f >= 0 and other >= 0:
                neighbors[f].add(other)
                neighbors[other].add(f)
        seen, pending = set(), [next(iter(fan))]
        while pending:
            f = pending.pop()
            if f not in seen:
                seen.add(f)
                pending.extend(neighbors[f] - seen)
        if seen != fan:
            raise ValueError('Non-manifold vertex fan.')

    lines = ['#TS0200', '', 'degree 3', 'cap-type 1',
             'star-smoothness 0', 'units 1 meters',
             'force-bezier-end-conditions 1']
    lines.extend('f %d 0' % h for h in face_links)
    lines.extend('e %d 1' % h for h in edges)
    lines.extend('v %d EAST' % fan[0] for fan in outgoing)
    lines.extend('l ' + ' '.join(map(str, row)) for row in links)
    lines.extend('ec %d 0' % e for e in boundary_edges)
    lines.append('0m odd-grip-map')
    lines.extend('0m gvp %d' % v for v in range(len(points)))
    lines.extend('0g ' + ' '.join(format(c, '.17g') for c in p) + ' 1' for p in points)
    lines.extend(['tol 0.00001', 'ver 30'])
    return '\n'.join(lines) + '\n'
