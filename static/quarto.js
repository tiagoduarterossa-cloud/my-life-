// Visualizador 3D do quarto, so com WebGL (sem bibliotecas, funciona sem internet).
// Le /quarto/quarto.json, /quarto/quarto.bin (posicoes, uv, indices) e /quarto/quarto.jpg (textura).

const VS = `
attribute vec3 aPos; attribute vec2 aUv;
uniform mat4 uMvp; varying vec2 vUv; varying float vY;
void main() { vUv = aUv; vY = aPos.y; gl_Position = uMvp * vec4(aPos, 1.0); }`;
const FS = `
precision mediump float;
uniform sampler2D uTex; uniform float uCorte; uniform vec3 uLuz; uniform float uMistura;
varying vec2 vUv; varying float vY;
void main() {
  if (vY > uCorte) discard;
  vec3 c = texture2D(uTex, vUv).rgb;
  gl_FragColor = vec4(mix(c, c * uLuz, uMistura), 1.0);
}`;

function mat4Perspetiva(fov, asp, perto, longe) {
  const f = 1 / Math.tan(fov / 2), nf = 1 / (perto - longe);
  return [f / asp, 0, 0, 0, 0, f, 0, 0, 0, 0, (longe + perto) * nf, -1, 0, 0, 2 * longe * perto * nf, 0];
}
function mat4OlharPara(o, alvo, cima) {
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const norm = v => { const l = Math.hypot(...v) || 1; return v.map(x => x / l); };
  const cruz = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const ponto = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const z = norm(sub(o, alvo)), x = norm(cruz(cima, z)), y = cruz(z, x);
  return [x[0], y[0], z[0], 0, x[1], y[1], z[1], 0, x[2], y[2], z[2], 0, -ponto(x, o), -ponto(y, o), -ponto(z, o), 1];
}
function mat4Mult(a, b) {
  const r = new Array(16);
  for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++)
    r[j * 4 + i] = a[i] * b[j * 4] + a[4 + i] * b[j * 4 + 1] + a[8 + i] * b[j * 4 + 2] + a[12 + i] * b[j * 4 + 3];
  return r;
}

export async function iniciarQuarto(caixa, aoMudarEstado = () => {}) {
  const canvas = document.createElement("canvas");
  canvas.style.cssText = "width:100%;height:100%;display:block;touch-action:none;border-radius:14px";
  caixa.appendChild(canvas);
  const gl = canvas.getContext("webgl", { antialias: true });
  if (!gl) throw new Error("Este browser não suporta 3D (WebGL).");
  if (!gl.getExtension("OES_element_index_uint")) throw new Error("O tablet não suporta modelos tão grandes.");

  aoMudarEstado("A carregar o quarto…");
  const FALTA = "Ainda não há quarto neste tablet. No Termux corre: python converter_quarto.py ~/storage/downloads/NOME.fbx";
  const buscar = async (url, tipo) => {
    const r = await fetch(url);
    if (r.status === 404) throw new Error(FALTA);
    if (!r.ok) throw new Error(`erro ${r.status} ao ler ${url}`);
    return tipo === "json" ? r.json() : r.arrayBuffer();
  };
  const [info, bin, img] = await Promise.all([
    buscar("/quarto/quarto.json", "json"),
    buscar("/quarto/quarto.bin", "bin"),
    new Promise((ok, falha) => { const i = new Image(); i.onload = () => ok(i);
      i.onerror = () => falha(new Error(FALTA)); i.src = "/quarto/quarto.jpg"; }),
  ]);
  if (bin.byteLength !== info.vertices * 20 + info.indices * 4) throw new Error("Os ficheiros do quarto estão incompletos. Corre outra vez o converter_quarto.py.");
  const nV = info.vertices, nI = info.indices;
  const pos = new Float32Array(bin, 0, nV * 3);
  const uv = new Float32Array(bin, nV * 12, nV * 2);
  const ind = new Uint32Array(bin, nV * 20, nI);

  const compilar = (tipo, src) => { const s = gl.createShader(tipo); gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; };
  const prog = gl.createProgram();
  gl.attachShader(prog, compilar(gl.VERTEX_SHADER, VS)); gl.attachShader(prog, compilar(gl.FRAGMENT_SHADER, FS));
  gl.linkProgram(prog); gl.useProgram(prog);
  const buf = (alvo, dados, attr, n) => {
    const b = gl.createBuffer(); gl.bindBuffer(alvo, b); gl.bufferData(alvo, dados, gl.STATIC_DRAW);
    if (attr) { const l = gl.getAttribLocation(prog, attr); gl.enableVertexAttribArray(l); gl.vertexAttribPointer(l, n, gl.FLOAT, false, 0, 0); }
  };
  buf(gl.ARRAY_BUFFER, pos, "aPos", 3);
  buf(gl.ARRAY_BUFFER, uv, "aUv", 2);
  buf(gl.ELEMENT_ARRAY_BUFFER, ind);

  const tex = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, img);
  gl.generateMipmap(gl.TEXTURE_2D);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
  const ext = gl.getExtension("EXT_texture_filter_anisotropic");
  if (ext) gl.texParameterf(gl.TEXTURE_2D, ext.TEXTURE_MAX_ANISOTROPY_EXT, 4);

  const U = n => gl.getUniformLocation(prog, n);
  const altura = info.max[1];
  const tam = Math.max(info.max[0] - info.min[0], info.max[2] - info.min[2]);
  // distancia para o quarto caber no ecra, seja ele deitado ou em pe
  const larg = info.max[0] - info.min[0], prof = info.max[2] - info.min[2];
  const caber = (w, h) => { const asp = (canvas.clientWidth || 1) / (canvas.clientHeight || 1), t = Math.tan(0.45);
    return Math.max(h / 2 / t, w / 2 / (t * asp)); };
  const inicial = { yaw: 0.6, pitch: 0.75, dist: caber(tam * 1.1, tam * 1.1), alvo: [0, altura * 0.35, 0] };
  const cam = { ...inicial, alvo: [...inicial.alvo] };
  const estado = { teto: false, luz: [1, 1, 1], mistura: 0 };

  function desenhar() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = canvas.clientWidth * dpr | 0, h = canvas.clientHeight * dpr | 0;
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    gl.viewport(0, 0, w, h);
    gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);
    // casa de bonecas: as paredes viradas para nos ficam invisiveis
    gl.enable(gl.CULL_FACE); gl.cullFace(gl.BACK);
    const o = [cam.alvo[0] + cam.dist * Math.cos(cam.pitch) * Math.sin(cam.yaw),
               cam.alvo[1] + cam.dist * Math.sin(cam.pitch),
               cam.alvo[2] + cam.dist * Math.cos(cam.pitch) * Math.cos(cam.yaw)];
    const cima = Math.abs(cam.pitch) > 1.5 ? [-Math.sin(cam.yaw), 0, -Math.cos(cam.yaw)] : [0, 1, 0];
    gl.uniformMatrix4fv(U("uMvp"), false, mat4Mult(mat4Perspetiva(0.9, w / h, 0.05, 50), mat4OlharPara(o, cam.alvo, cima)));
    gl.uniform1f(U("uCorte"), estado.teto ? 99 : altura - 0.25);
    gl.uniform3fv(U("uLuz"), estado.luz); gl.uniform1f(U("uMistura"), estado.mistura);
    gl.uniform1i(U("uTex"), 0);
    gl.drawElements(gl.TRIANGLES, nI, gl.UNSIGNED_INT, 0);
  }
  let pedido = false;
  const redesenhar = () => { if (!pedido) { pedido = true; requestAnimationFrame(() => { pedido = false; desenhar(); }); } };

  // toque e rato: um dedo roda, dois dedos aproximam
  const dedos = new Map(); let distDedos = 0;
  canvas.addEventListener("pointerdown", e => { canvas.setPointerCapture(e.pointerId); dedos.set(e.pointerId, [e.clientX, e.clientY]); });
  canvas.addEventListener("pointerup", e => dedos.delete(e.pointerId));
  canvas.addEventListener("pointercancel", e => dedos.delete(e.pointerId));
  canvas.addEventListener("pointermove", e => {
    if (!dedos.has(e.pointerId)) return;
    const [px, py] = dedos.get(e.pointerId); dedos.set(e.pointerId, [e.clientX, e.clientY]);
    if (dedos.size === 1) {
      cam.yaw -= (e.clientX - px) * 0.008;
      cam.pitch = Math.min(1.55, Math.max(0.05, cam.pitch + (e.clientY - py) * 0.006));
    } else if (dedos.size === 2) {
      const [a, b] = [...dedos.values()], d = Math.hypot(a[0] - b[0], a[1] - b[1]);
      if (distDedos) cam.dist = Math.min(tam * 3, Math.max(0.8, cam.dist * distDedos / d));
      distDedos = d;
    }
    redesenhar();
  });
  canvas.addEventListener("pointerup", () => { if (dedos.size < 2) distDedos = 0; });
  canvas.addEventListener("wheel", e => { e.preventDefault(); cam.dist = Math.min(tam * 3, Math.max(0.8, cam.dist * (1 + e.deltaY * 0.001))); redesenhar(); }, { passive: false });
  new ResizeObserver(redesenhar).observe(canvas);

  desenhar(); aoMudarEstado("");
  return {
    info,
    planta() { cam.yaw = 0; cam.pitch = 1.55; cam.dist = caber(larg * 1.08, prof * 1.08) + altura; cam.alvo = [0, 0, 0]; redesenhar(); },
    repor() { Object.assign(cam, { ...inicial, dist: caber(tam * 1.1, tam * 1.1), alvo: [...inicial.alvo] }); redesenhar(); },
    teto(v) { estado.teto = v; redesenhar(); },
    // tinge o quarto com a cor do LED (r, g, b de 0 a 1)
    luz(cor, forca) { estado.luz = cor; estado.mistura = forca; redesenhar(); },
  };
}
