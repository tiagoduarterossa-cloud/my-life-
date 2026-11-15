#!/usr/bin/env python3
"""
Converte o scan do quarto (FBX binario, da 3d Scanner App) para o visualizador 3D da central.

Uso no Termux (precisa de: pkg install python-numpy python-pillow):
    python converter_quarto.py ~/storage/downloads/quarto.fbx

Cria static/quarto/quarto.json, quarto.bin e quarto.jpg. Estes ficheiros NAO vao para o GitHub
(estao no .gitignore), porque mostram o teu quarto por dentro.
"""
import json, struct, sys, zlib
from pathlib import Path
import numpy as np
from PIL import Image
Image.MAX_IMAGE_PIXELS = None

d = open(sys.argv[1], 'rb').read()
ver = struct.unpack('<I', d[23:27])[0]
big = ver >= 7500
def prop(o):
    t = chr(d[o]); o += 1
    if t in 'CY': return (d[o] if t=='C' else struct.unpack('<h', d[o:o+2])[0]), o + (1 if t=='C' else 2)
    if t == 'I': return struct.unpack('<i', d[o:o+4])[0], o+4
    if t == 'F': return struct.unpack('<f', d[o:o+4])[0], o+4
    if t == 'D': return struct.unpack('<d', d[o:o+8])[0], o+8
    if t == 'L': return struct.unpack('<q', d[o:o+8])[0], o+8
    if t in 'SR':
        n = struct.unpack('<I', d[o:o+4])[0]; v = d[o+4:o+4+n]
        return (v if t=='R' else v.decode('utf-8','replace')), o+4+n
    if t in 'fdlib':
        n, enc, cl = struct.unpack('<III', d[o:o+12]); o += 12
        raw = d[o:o+cl]; o += cl
        if enc: raw = zlib.decompress(raw)
        fmt = {'f':'f','d':'d','l':'q','i':'i','b':'B'}[t]
        return list(struct.unpack('<%d%s' % (n, fmt), raw)), o
    raise ValueError(t)
def node(o):
    if big: end, np_, pl = struct.unpack('<QQQ', d[o:o+24]); o += 24
    else: end, np_, pl = struct.unpack('<III', d[o:o+12]); o += 12
    nl = d[o]; name = d[o+1:o+1+nl].decode(); o += 1 + nl
    if end == 0: return None, o
    props = []
    for _ in range(np_):
        v, o = prop(o); props.append(v)
    kids = []
    while o < end - (25 if big else 13):
        k, o = node(o)
        if k is None: break
        kids.append(k)
    return (name, props, kids), end

def find(n, name):
    out = [n] if n[0] == name else []
    for k in n[2]: out += find(k, name)
    return out
def ler_fbx():
    o = 27; top = []
    while o < len(d) - 200:
        n, o = node(o)
        if n is None: break
        top.append(n)
    return top
top = ler_fbx()
geos = [g for t in top for g in find(t, 'Geometry')]
textura = None
for t in top:
    for vid in find(t, 'Video'):
        for k in vid[2]:
            if k[0] == 'Content' and k[1] and isinstance(k[1][0], bytes): textura = k[1][0]
g = geos[0]; L = {k[0]: k for k in g[2]}
uvl = {c[0]: c for c in L['LayerElementUV'][2]}
V = np.array(L['Vertices'][1][0], np.float64).reshape(-1, 3)
idx = np.array(L['PolygonVertexIndex'][1][0], np.int64); idx = np.where(idx < 0, ~idx, idx)
UV = np.array(uvl['UV'][1][0], np.float32).reshape(-1, 2)
UVI = np.array(uvl['UVIndex'][1][0], np.int64)
tri_v = idx.reshape(-1, 3); tri_uv = UVI.reshape(-1, 3)

# 1. endireitar: angulo em torno do eixo vertical que deixa as paredes mais "alinhadas"
y = V[:, 1]; meio = (y > np.percentile(y, 20)) & (y < np.percentile(y, 80))
P = V[meio][:, [0, 2]]
def nitidez(a):
    c, s = np.cos(a), np.sin(a)
    R = P @ np.array([[c, -s], [s, c]])
    return sum((np.histogram(R[:, i], bins=400)[0].astype(float) ** 2).sum() for i in (0, 1))
angs = np.radians(np.arange(-45, 45, 0.25))
ang = angs[np.argmax([nitidez(a) for a in angs])]
c, s = np.cos(ang), np.sin(ang)
xz = V[:, [0, 2]] @ np.array([[c, -s], [s, c]])
V = np.column_stack([xz[:, 0], V[:, 1], xz[:, 1]])
print('rotacao', round(np.degrees(ang), 2), 'graus')

# 2. cortar o ruido de fora do quarto: fica a maior "mancha" continua no chao (histograma em z)
hz, ez = np.histogram(V[:, 2], bins=200)
cheio = hz > hz.max() * 0.01
melhor, atual, ini = (0, 0, 0), 0, 0
for i, ok in enumerate(cheio):
    if ok:
        if atual == 0: ini = i
        atual += 1
        if atual > melhor[0]: melhor = (atual, ini, i)
    else: atual = 0
zmin, zmax = ez[melhor[1]] - 0.05, ez[melhor[2] + 1] + 0.05
hx, ex = np.histogram(V[:, 0], bins=200); okx = np.where(hx > hx.max() * 0.01)[0]
xmin, xmax = ex[okx[0]] - 0.05, ex[okx[-1] + 1] + 0.05
dentro = (V[:, 2] >= zmin) & (V[:, 2] <= zmax) & (V[:, 0] >= xmin) & (V[:, 0] <= xmax)
tri_ok = dentro[tri_v].all(axis=1)
tri_v, tri_uv = tri_v[tri_ok], tri_uv[tri_ok]
print('triangulos', len(tri_ok), '->', int(tri_ok.sum()))

# 3. chao em y=0 e quarto centrado
usados = np.unique(tri_v)
chao = np.percentile(V[usados, 1], 0.5)
V[:, 1] -= chao
cx, cz = (V[usados, 0].min() + V[usados, 0].max()) / 2, (V[usados, 2].min() + V[usados, 2].max()) / 2
V[:, 0] -= cx; V[:, 2] -= cz

# 4. um vertice por cada par (posicao, uv)
chave = tri_v.ravel() * (len(UV) + 1) + tri_uv.ravel()
unicos, inv = np.unique(chave, return_inverse=True)
pos = V[unicos // (len(UV) + 1)].astype(np.float32)
uv = UV[unicos % (len(UV) + 1)].astype(np.float32)
ind = inv.astype(np.uint32)
mn, mx = pos.min(0), pos.max(0)
print('vertices', len(pos), 'indices', len(ind), 'medidas (m)', np.round(mx - mn, 2))

pasta = Path(__file__).resolve().parent / 'static' / 'quarto'
pasta.mkdir(parents=True, exist_ok=True)
out = str(pasta / 'quarto')
with open(out + '.bin', 'wb') as f:
    f.write(pos.tobytes()); f.write(uv.tobytes()); f.write(ind.tobytes())
json.dump({"vertices": int(len(pos)), "indices": int(len(ind)),
           "min": [round(float(v), 3) for v in mn], "max": [round(float(v), 3) for v in mx]},
          open(out + '.json', 'w'))
import io
tex = Image.open(io.BytesIO(textura)).convert('RGB').resize((4096, 4096), Image.LANCZOS)
tex.save(out + '.jpg', quality=85)
print('Pronto. Abre o separador Quarto na central.')
