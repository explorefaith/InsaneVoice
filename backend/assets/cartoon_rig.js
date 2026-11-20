/* InsaneVoice cartoon rig library — pre-built 3D-style SVG characters & props.
   The LLM only writes choreography JSON; this engine does all drawing/animation.
   Deterministic: window.IVScene.render(t) produces the exact frame for time t. */
window.IV = (function () {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const W = 1920, H = 1080;
  function el(name, attrs, parent) {
    const e = document.createElementNS(NS, name);
    for (const k in (attrs || {})) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  const clamp01 = v => v < 0 ? 0 : v > 1 ? 1 : v;
  const ease = t => { t = clamp01(t); return t * t * (3 - 2 * t); };
  const seg = (t, a, b) => ease(clamp01((t - a) / ((b - a) || 1e-6)));
  const lerp = (a, b, u) => a + (b - a) * u;
  const TAU = Math.PI * 2;

  function shadow(parent, rx) {
    return el("ellipse", { cx: 0, cy: 0, rx: rx || 70, ry: 13, fill: "rgba(0,0,0,.16)" }, parent);
  }

  /* ================= HUMAN RIG ================= */
  function human(P) {
    P = P || {};
    const skin = P.skin || "#eec39a";
    const hairC = P.hair || "#3b2a1a";
    const shirt = P.shirt || "#e2574c";
    const pants = P.pants || "#3a4a63";
    const g = el("g", {});
    const sh = shadow(g, 62);
    const body = el("g", {}, g);
    // legs (pivot at hip y=-92)
    const mkLeg = (x) => {
      const leg = el("g", { transform: `translate(${x},-92)` }, body);
      el("rect", { x: -9, y: 0, width: 18, height: 84, rx: 9, fill: pants }, leg);
      el("rect", { x: -11, y: 76, width: 24, height: 14, rx: 7, fill: "#2e3138" }, leg);
      return leg;
    };
    const legL = mkLeg(-14), legR = mkLeg(14);
    // torso
    const torso = el("g", {}, body);
    el("rect", { x: -32, y: -178, width: 64, height: 92, rx: 22, fill: shirt }, torso);
    if (P.old) el("path", { d: "M-32 -120 Q0 -100 32 -120", stroke: "rgba(0,0,0,.12)", "stroke-width": 5, fill: "none" }, torso);
    // arms (pivot at shoulder)
    const mkArm = (x) => {
      const arm = el("g", { transform: `translate(${x},-166)` }, body);
      el("rect", { x: -8, y: -4, width: 16, height: 64, rx: 8, fill: shirt }, arm);
      el("circle", { cx: 0, cy: 62, r: 9, fill: skin }, arm);
      return arm;
    };
    const armL = mkArm(-38), armR = mkArm(38);
    // head (pivot at neck 0,-178)
    const head = el("g", { transform: "translate(0,-178)" }, body);
    el("circle", { cx: 0, cy: -34, r: 37, fill: skin }, head);
    // hair variants
    const hs = P.hairstyle || "short";
    const hc = P.old ? "#cfcfd6" : hairC;
    if (hs === "long") {
      el("path", { d: "M-38 -46 Q-44 6 -30 22 L-30 -30 Q0 -78 30 -30 L30 22 Q44 6 38 -46 Q0 -84 -38 -46", fill: hc }, head);
      el("path", { d: "M-36 -52 Q0 -86 36 -52 Q36 -72 0 -78 Q-36 -72 -36 -52", fill: hc }, head);
    } else if (hs === "bun") {
      el("path", { d: "M-37 -40 Q0 -84 37 -40 Q30 -70 0 -74 Q-30 -70 -37 -40", fill: hc }, head);
      el("circle", { cx: 0, cy: -76, r: 15, fill: hc }, head);
    } else if (hs === "curly") {
      [-26, -13, 0, 13, 26].forEach(x => el("circle", { cx: x, cy: -62 + Math.abs(x) * 0.35, r: 13, fill: hc }, head));
    } else if (hs !== "bald") {
      el("path", { d: "M-37 -44 Q-34 -78 0 -76 Q34 -78 37 -44 Q18 -62 0 -60 Q-18 -62 -37 -44", fill: hc }, head);
    }
    // eyes
    const eyeY = P.child ? -38 : -40;
    const mkEye = (x) => {
      const eg = el("g", { transform: `translate(${x},${eyeY})` }, head);
      el("ellipse", { cx: 0, cy: 0, rx: 7.5, ry: 8.5, fill: "#fff" }, eg);
      el("circle", { cx: 0, cy: 1, r: 4, fill: "#23272f" }, eg);
      el("circle", { cx: 1.4, cy: -0.5, r: 1.3, fill: "#fff" }, eg);
      const lid = el("rect", { x: -8.5, y: -10, width: 17, height: 0, rx: 4, fill: skin }, eg);
      return lid;
    };
    const lidL = mkEye(-14), lidR = mkEye(14);
    // brows
    const bL = el("rect", { x: -23, y: -56, width: 17, height: 4.5, rx: 2, fill: hc }, head);
    const bR = el("rect", { x: 6, y: -56, width: 17, height: 4.5, rx: 2, fill: hc }, head);
    // mouth
    const mouth = el("ellipse", { cx: 0, cy: -14, rx: 9, ry: 2.6, fill: "#8a4238" }, head);
    if (P.glasses) {
      el("circle", { cx: -14, cy: eyeY, r: 12, fill: "none", stroke: "#2e3138", "stroke-width": 3 }, head);
      el("circle", { cx: 14, cy: eyeY, r: 12, fill: "none", stroke: "#2e3138", "stroke-width": 3 }, head);
      el("line", { x1: -2, y1: eyeY, x2: 2, y2: eyeY, stroke: "#2e3138", "stroke-width": 3 }, head);
    }
    if (P.hat) el("path", { d: "M-40 -62 Q0 -96 40 -62 L40 -70 Q0 -104 -40 -70 Z", fill: P.hatColor || "#4a6741" }, head);
    const rig = {
      kind: "human", node: g,
      set: {
        walk(phase, amp) {
          const s = Math.sin(phase) * amp, c = -Math.sin(phase) * amp;
          legL.setAttribute("transform", `translate(-14,-92) rotate(${s})`);
          legR.setAttribute("transform", `translate(14,-92) rotate(${c})`);
          armL.setAttribute("transform", `translate(-38,-166) rotate(${c * 0.7})`);
          armR.setAttribute("transform", `translate(38,-166) rotate(${s * 0.7})`);
          body.setAttribute("transform", `translate(0,${-Math.abs(Math.sin(phase)) * 5 * amp})`);
        },
        armL(a) { armL.setAttribute("transform", `translate(-38,-166) rotate(${a})`); },
        armR(a) { armR.setAttribute("transform", `translate(38,-166) rotate(${a})`); },
        lean(a) { torso.setAttribute("transform", `rotate(${a} 0 -90)`); },
        head(a) { head.setAttribute("transform", `translate(0,-178) rotate(${a})`); },
        mouth(open, smile) {
          mouth.setAttribute("ry", 2.6 + open * 11);
          mouth.setAttribute("rx", 9 - smile * 1 + open * 1.5);
          mouth.setAttribute("cy", -14 - smile * 1.5);
        },
        blink(v) { lidL.setAttribute("height", 18 * v); lidR.setAttribute("height", 18 * v); },
        brows(mood) {
          if (mood === "happy") { bL.setAttribute("transform", "rotate(-8 -14 -54)"); bR.setAttribute("transform", "rotate(8 14 -54)"); }
          else if (mood === "sad") { bL.setAttribute("transform", "rotate(10 -14 -54)"); bR.setAttribute("transform", "rotate(-10 14 -54)"); }
          else if (mood === "surprised") { bL.setAttribute("y", -62); bR.setAttribute("y", -62); }
          else if (mood === "angry") { bL.setAttribute("transform", "rotate(16 -14 -50)"); bR.setAttribute("transform", "rotate(-16 14 -50)"); }
          else { bL.removeAttribute("transform"); bR.removeAttribute("transform"); bL.setAttribute("y", -56); bR.setAttribute("y", -56); }
        },
        crouch(v) { body.setAttribute("transform", `translate(0,${44 * v}) rotate(${8 * v} 0 -60)`); },
        flip(f) { g.setAttribute("transform", g.dataset.pos + (f ? " scale(-1,1)" : "")); },
        pos(x, y, s, f) {
          g.dataset.pos = `translate(${x},${y}) scale(${f ? -s : s},${s})`;
          g.setAttribute("transform", g.dataset.pos + (g.dataset.flip ? " scale(-1,1)" : ""));
        },
        setFlip(f) { g.dataset.flip = f ? "1" : ""; g.setAttribute("transform", g.dataset.pos + (f ? " scale(-1,1)" : "")); },
        jump(dy, sq) {
          body.setAttribute("transform", `translate(0,${dy}) scale(${1 + sq * 0.18},${1 - sq * 0.22})`);
          sh.setAttribute("transform", `translate(0,${-dy * 0.08}) scale(${1 - dy * 0.0012},${1 - dy * 0.0012})`);
        },
      },
    };
    rig.set.mouth(0, 0.6);
    return rig;
  }

  /* ================= QUADRUPED (cat/dog) ================= */
  function quadruped(P) {
    P = P || {};
    const dog = P.kind === "dog";
    const bodyC = P.color || (dog ? "#a9744f" : "#8d9099");
    const g = el("g", {});
    shadow(g, 52);
    const body = el("g", {}, g);
    const mkLeg = (x) => {
      const leg = el("g", { transform: `translate(${x},-46)` }, body);
      el("rect", { x: -7, y: 0, width: 14, height: 46, rx: 7, fill: bodyC }, leg);
      return leg;
    };
    const legL = mkLeg(-40), legR = mkLeg(-24), legL2 = mkLeg(28), legR2 = mkLeg(44);
    el("ellipse", { cx: 0, cy: -62, rx: 62, ry: 30, fill: bodyC }, body);
    const tail = el("g", { transform: dog ? "translate(58,-72)" : "translate(-58,-72)" }, body);
    el("path", { d: dog ? "M0 0 Q26 -8 34 -34" : "M0 0 Q-26 -8 -34 -34", stroke: bodyC, "stroke-width": 11, "stroke-linecap": "round", fill: "none" }, tail);
    const headG = el("g", { transform: dog ? "translate(-64,-92)" : "translate(64,-88)" }, body);
    el("circle", { cx: 0, cy: 0, r: 30, fill: bodyC }, headG);
    const earL = el("path", { d: dog ? "M-18 -24 L-26 -52 L-2 -34 Z" : "M-20 -20 L-30 -44 L-4 -32 Z", fill: bodyC }, headG);
    const earR = el("path", { d: dog ? "M2 -26 L10 -54 L24 -30 Z" : "M4 -22 L14 -46 L28 -28 Z", fill: bodyC }, headG);
    el("circle", { cx: -11, cy: -6, r: 4.5, fill: "#23272f" }, headG);
    el("circle", { cx: 11, cy: -6, r: 4.5, fill: "#23272f" }, headG);
    el("ellipse", { cx: 0, cy: 6, rx: 6, ry: 4.5, fill: dog ? "#33231a" : "#d38b9c" }, headG);
    el("path", { d: "M-8 12 Q0 18 8 12", stroke: "rgba(0,0,0,.35)", "stroke-width": 3, fill: "none" }, headG);
    if (!dog) { // whiskers
      el("line", { x1: 12, y1: 4, x2: 30, y2: 2, stroke: "rgba(255,255,255,.65)", "stroke-width": 2 }, headG);
      el("line", { x1: 12, y1: 9, x2: 30, y2: 11, stroke: "rgba(255,255,255,.65)", "stroke-width": 2 }, headG);
    }
    const mouth = el("ellipse", { cx: 0, cy: 10, rx: 5, ry: 1.6, fill: "#5a2f28" }, headG);
    return {
      kind: "quad", node: g,
      set: {
        walk(phase, amp) {
          const s = Math.sin(phase) * 24 * amp;
          legL.setAttribute("transform", `translate(-40,-46) rotate(${s})`);
          legR.setAttribute("transform", `translate(-24,-46) rotate(${-s})`);
          legL2.setAttribute("transform", `translate(28,-46) rotate(${-s})`);
          legR2.setAttribute("transform", `translate(44,-46) rotate(${s})`);
          body.setAttribute("transform", `translate(0,${-Math.abs(Math.sin(phase)) * 4 * amp})`);
        },
        tailWag(p) { tail.setAttribute("transform", (dog ? "translate(58,-72)" : "translate(-58,-72)") + ` rotate(${Math.sin(p) * 28})`); },
        head(a) { headG.setAttribute("transform", (dog ? "translate(-64,-92)" : "translate(64,-88)") + ` rotate(${a})`); },
        mouth(open) { mouth.setAttribute("ry", 1.6 + open * 5); },
        jump(dy, sq) { body.setAttribute("transform", `translate(0,${dy}) scale(${1 + sq * 0.15},${1 - sq * 0.2})`); },
        armL() {}, armR() {}, lean() {},
        pos(x, y, s, f) {
          g.dataset.pos = `translate(${x},${y}) scale(${f ? -s : s},${s})`;
          g.dataset.flip = f ? "1" : "";
          g.setAttribute("transform", g.dataset.pos + (f ? " scale(-1,1)" : ""));
        },
        setFlip(f) { g.dataset.flip = f ? "1" : ""; g.setAttribute("transform", g.dataset.pos + (f ? " scale(-1,1)" : "")); },
        crouch() {}, blink() {}, brows() {},
      },
    };
  }

  /* ================= BIRD ================= */
  function bird(P) {
    const c = (P && P.color) || "#5b87d7";
    const g = el("g", {});
    shadow(g, 34);
    const body = el("g", {}, g);
    el("ellipse", { cx: 0, cy: -46, rx: 34, ry: 26, fill: c }, body);
    el("circle", { cx: 24, cy: -62, r: 16, fill: c }, body);
    el("path", { d: "M38 -62 L52 -58 L38 -53 Z", fill: "#e8a33c" }, body);
    el("circle", { cx: 28, cy: -66, r: 3.4, fill: "#23272f" }, body);
    const wing = el("path", { d: "M-4 -52 Q-30 -58 -34 -30 Q-12 -30 -2 -42 Z", fill: "rgba(0,0,0,.25)" }, body);
    const legL = el("line", { x1: -8, y1: -22, x2: -8, y2: 0, stroke: "#e8a33c", "stroke-width": 4 }, body);
    const legR = el("line", { x1: 8, y1: -22, x2: 8, y2: 0, stroke: "#e8a33c", "stroke-width": 4 }, body);
    const tail = el("path", { d: "M-30 -50 L-52 -44 L-30 -38 Z", fill: "rgba(0,0,0,.2)" }, body);
    const mouth = el("ellipse", { cx: 38, cy: -56, rx: 4, ry: 1.6, fill: "#8a4238" }, body);
    return {
      kind: "bird", node: g,
      set: {
        flap(p) { wing.setAttribute("transform", `rotate(${Math.sin(p) * 40} -4 -52)`); },
        hop() {}, walk(phase, amp) { body.setAttribute("transform", `translate(0,${-Math.abs(Math.sin(phase)) * 3 * amp})`); },
        mouth(open) { mouth.setAttribute("ry", 1.6 + open * 4); },
        jump(dy) { body.setAttribute("transform", `translate(0,${dy})`); },
        armL() {}, armR() {}, lean() {}, crouch() {},
        pos(x, y, s, f) { g.dataset.pos = `translate(${x},${y})`; g.dataset.s = s; g.dataset.flip = f ? "1" : ""; g.setAttribute("transform", g.dataset.pos + (f ? " scale(-1,1)" : `scale(${s},${s})`)); },
        setFlip(f) { const s = g.dataset.s || 1; g.dataset.flip = f ? "1" : ""; g.setAttribute("transform", g.dataset.pos + (f ? " scale(-1,1)" : `scale(${s},${s})`)); },
        blink() {}, brows() {}, head() {},
      },
    };
  }

  /* ================= PROPS ================= */
  function tree() {
    const g = el("g", {});
    const sway = el("g", {}, g);
    el("rect", { x: -16, y: -150, width: 32, height: 152, rx: 12, fill: "#7c5333" }, sway);
    el("circle", { cx: 0, cy: -196, r: 92, fill: "#4f9d4f" }, sway);
    el("circle", { cx: -62, cy: -160, r: 62, fill: "#58ab58" }, sway);
    el("circle", { cx: 62, cy: -158, r: 64, fill: "#459545" }, sway);
    el("circle", { cx: -18, cy: -214, r: 40, fill: "#63b963" }, sway);
    return { node: g, tick(t) { sway.setAttribute("transform", `rotate(${Math.sin(t * 0.9) * 2.4} 0 -20)`); } };
  }
  function pine() {
    const g = el("g", {});
    el("rect", { x: -12, y: -110, width: 24, height: 112, fill: "#6b4a2e" }, g);
    [[-40, -90, 62], [-50, -150, 74], [-58, -210, 84]].forEach(([x, y, w]) =>
      el("path", { d: `M${x} ${y} L${-x} ${y} L0 ${y - w} Z`, fill: "#3e8f5f" }, g));
    return { node: g, tick() {} };
  }
  function bush() {
    const g = el("g", {});
    el("circle", { cx: -26, cy: -22, r: 30, fill: "#4f9d4f" }, g);
    el("circle", { cx: 10, cy: -30, r: 34, fill: "#58ab58" }, g);
    el("circle", { cx: 38, cy: -18, r: 26, fill: "#459545" }, g);
    return { node: g, tick(t) { g.setAttribute("transform", `rotate(${Math.sin(t * 1.3) * 1.6})`); } };
  }
  function flower(P) {
    const g = el("g", {});
    const stem = el("g", {}, g);
    el("line", { x1: 0, y1: 0, x2: 0, y2: -44, stroke: "#4e8f3e", "stroke-width": 6 }, stem);
    el("circle", { cx: 0, cy: -52, r: 12, fill: (P && P.color) || "#f26d6d" }, stem);
    el("circle", { cx: -11, cy: -46, r: 8, fill: (P && P.color) || "#f26d6d" }, stem);
    el("circle", { cx: 11, cy: -46, r: 8, fill: (P && P.color) || "#f26d6d" }, stem);
    el("circle", { cx: 0, cy: -52, r: 5, fill: "#ffd76e" }, stem);
    return { node: g, tick(t) { stem.setAttribute("transform", `rotate(${Math.sin(t * 1.7 + (P && P.ph || 0)) * 5})`); } };
  }
  function river(P) {
    const w = (P && P.w) || 1920;
    const g = el("g", {});
    el("rect", { x: -20, y: -58, width: w + 40, height: 130, rx: 20, fill: "#4aa3df" }, g);
    const waves = [];
    for (let i = 0; i < 9; i++) {
      waves.push(el("rect", { x: 40 + i * (w / 8), y: -30 + (i % 3) * 22, width: 70, height: 9, rx: 4.5, fill: "rgba(255,255,255,.5)" }, g));
    }
    return { node: g, tick(t) { waves.forEach((r, i) => { r.setAttribute("x", 40 + ((i * (w / 8) + t * (26 + i * 7)) % (w + 80)) - 40); }); } };
  }
  function pond() {
    const g = el("g", {});
    el("ellipse", { cx: 0, cy: 0, rx: 210, ry: 52, fill: "#4aa3df" }, g);
    el("ellipse", { cx: -60, cy: -10, rx: 70, ry: 16, fill: "rgba(255,255,255,.35)" }, g);
    return { node: g, tick() {} };
  }
  function house(P) {
    const g = el("g", {});
    const night = (P && P.time) === "night";
    el("rect", { x: -130, y: -170, width: 260, height: 172, rx: 10, fill: (P && P.color) || "#e7d3b1" }, g);
    el("path", { d: "M-152 -168 L0 -280 L152 -168 Z", fill: "#b0603f" }, g);
    el("rect", { x: -34, y: -90, width: 68, height: 92, rx: 6, fill: "#8a5a38" }, g);
    el("circle", { cx: 20, cy: -46, r: 5, fill: "#e8cf8e" }, g);
    [[-96, -130], [58, -130]].forEach(([x, y]) => {
      el("rect", { x, y, width: 46, height: 44, rx: 5, fill: night ? "#ffd76e" : "#9fd4e8", stroke: "#7c5333", "stroke-width": 5 }, g);
    });
    return { node: g, tick() {} };
  }
  function fence(P) {
    const w = (P && P.w) || 500;
    const g = el("g", {});
    el("rect", { x: 0, y: -62, width: w, height: 10, rx: 4, fill: "#c9b28a" }, g);
    el("rect", { x: 0, y: -32, width: w, height: 10, rx: 4, fill: "#c9b28a" }, g);
    for (let x = 0; x <= w; x += 90) el("rect", { x, y: -84, width: 13, height: 86, rx: 4, fill: "#b39c72" }, g);
    return { node: g, tick() {} };
  }
  function bench() {
    const g = el("g", {});
    el("rect", { x: -80, y: -60, width: 160, height: 14, rx: 6, fill: "#b07c46" }, g);
    el("rect", { x: -80, y: -108, width: 160, height: 12, rx: 6, fill: "#b07c46" }, g);
    [[-64], [50]].forEach(([x]) => el("rect", { x, y: -46, width: 12, height: 48, rx: 4, fill: "#7c5333" }, g));
    [[-64], [50]].forEach(([x]) => el("rect", { x, y: -96, width: 12, height: 40, rx: 4, fill: "#7c5333" }, g));
    return { node: g, tick() {} };
  }
  function rock() {
    const g = el("g", {});
    el("path", { d: "M-58 0 Q-50 -44 0 -52 Q56 -46 62 0 Z", fill: "#9aa3ab" }, g);
    el("path", { d: "M-20 -46 Q10 -52 34 -34", stroke: "rgba(255,255,255,.3)", "stroke-width": 5, fill: "none" }, g);
    return { node: g, tick() {} };
  }
  function table() {
    const g = el("g", {});
    el("rect", { x: -90, y: -84, width: 180, height: 14, rx: 6, fill: "#a9744f" }, g);
    [[-76], [58]].forEach(([x]) => el("rect", { x, y: -70, width: 14, height: 72, rx: 5, fill: "#8a5a38" }, g));
    return { node: g, tick() {} };
  }
  function chair() {
    const g = el("g", {});
    el("rect", { x: -36, y: -66, width: 72, height: 12, rx: 5, fill: "#a9744f" }, g);
    el("rect", { x: -36, y: -128, width: 12, height: 66, rx: 5, fill: "#8a5a38" }, g);
    el("rect", { x: -30, y: -54, width: 12, height: 56, rx: 5, fill: "#8a5a38" }, g);
    el("rect", { x: 20, y: -54, width: 12, height: 56, rx: 5, fill: "#8a5a38" }, g);
    return { node: g, tick() {} };
  }
  function bookshelf() {
    const g = el("g", {});
    el("rect", { x: -70, y: -190, width: 140, height: 192, rx: 8, fill: "#8a5a38" }, g);
    [["#e2574c", -150], ["#4a6741", -110], ["#5b87d7", -70], ["#e8a33c", -30]].forEach(([c, y]) => {
      el("rect", { x: -58, y, width: 116, height: 8, fill: "#6e4a2e" }, g);
      for (let i = 0; i < 6; i++) el("rect", { x: -54 + i * 19, y: y - 26, width: 13, height: 26, rx: 2, fill: c }, g);
    });
    return { node: g, tick() {} };
  }
  function sun() {
    const g = el("g", {});
    const rays = el("g", { transform: "translate(0,0)" }, g);
    for (let i = 0; i < 12; i++)
      el("line", { x1: 0, y1: -78, x2: 0, y2: -96, stroke: "#ffcf5e", "stroke-width": 9, "stroke-linecap": "round", transform: `rotate(${i * 30})` }, rays);
    el("circle", { cx: 0, cy: 0, r: 62, fill: "#ffd76e" }, g);
    return { node: g, tick(t) { rays.setAttribute("transform", `rotate(${t * 7})`); } };
  }
  function moon() {
    const g = el("g", {});
    el("circle", { cx: 0, cy: 0, r: 56, fill: "#f4e9c8" }, g);
    el("circle", { cx: -18, cy: -12, r: 10, fill: "rgba(0,0,0,.08)" }, g);
    el("circle", { cx: 16, cy: 18, r: 14, fill: "rgba(0,0,0,.08)" }, g);
    el("circle", { cx: 22, cy: -22, r: 8, fill: "rgba(0,0,0,.08)" }, g);
    return { node: g, tick() {} };
  }
  function clouds() {
    const g = el("g", {});
    const made = [];
    for (let i = 0; i < 4; i++) {
      const x0 = 120 + i * 470, y0 = 90 + (i % 2) * 70;
      const cg = el("g", { transform: `translate(${x0},${y0})` }, g);
      el("ellipse", { cx: 0, cy: 0, rx: 85, ry: 26, fill: "rgba(255,255,255,.92)" }, cg);
      el("circle", { cx: -34, cy: -12, r: 24, fill: "rgba(255,255,255,.92)" }, cg);
      el("circle", { cx: 22, cy: -16, r: 30, fill: "rgba(255,255,255,.92)" }, cg);
      made.push({ cg, x0, y0, sp: 12 + i * 7 });
    }
    return { node: g, tick(t) { made.forEach(m => { m.cg.setAttribute("transform", `translate(${((m.x0 + t * m.sp) % 2400) - 240},${m.y0})`); }); } };
  }
  function stars() {
    const g = el("g", {});
    const list = [];
    for (let i = 0; i < 46; i++) {
      const s = el("circle", { cx: Math.random() * 1920, cy: Math.random() * 560, r: 1.6 + Math.random() * 2.4, fill: "#fff" }, g);
      list.push({ s, ph: Math.random() * 10 });
    }
    return { node: g, tick(t) { list.forEach(o => { o.s.setAttribute("opacity", 0.45 + 0.55 * Math.abs(Math.sin(t * 1.6 + o.ph))); }); } };
  }
  function rain() {
    const g = el("g", {});
    const drops = [];
    for (let i = 0; i < 90; i++) {
      const d = el("line", { x1: Math.random() * 2000 - 40, y1: Math.random() * 1100, x2: Math.random() * 2000 - 40 - 8, y2: Math.random() * 1100 + 26, stroke: "rgba(190,215,235,.55)", "stroke-width": 3, "stroke-linecap": "round" }, g);
      drops.push({ d, y0: parseFloat(d.getAttribute("y1")), sp: 620 + Math.random() * 260 });
    }
    return { node: g, tick(t) { drops.forEach(o => { const y = (o.y0 + t * o.sp) % 1160 - 30; o.d.setAttribute("y1", y); o.d.setAttribute("y2", y + 26); o.d.setAttribute("x2", parseFloat(o.d.getAttribute("x1")) - 8); }); } };
  }
  function snow() {
    const g = el("g", {});
    const flakes = [];
    for (let i = 0; i < 80; i++) {
      const f = el("circle", { cx: Math.random() * 1980 - 30, cy: Math.random() * 1100, r: 3 + Math.random() * 4.5, fill: "rgba(255,255,255,.85)" }, g);
      flakes.push({ f, y0: Math.random() * 1100, sp: 60 + Math.random() * 90, ph: Math.random() * 9, x0: parseFloat(f.getAttribute("cx")) });
    }
    return { node: g, tick(t) { flakes.forEach(o => { o.f.setAttribute("cy", (o.y0 + t * o.sp) % 1140 - 20); o.f.setAttribute("cx", o.x0 + Math.sin(t * 0.9 + o.ph) * 36); }); } };
  }
  function fireflies() {
    const g = el("g", {});
    const list = [];
    for (let i = 0; i < 22; i++) {
      const f = el("circle", { cx: Math.random() * 1800 + 60, cy: 420 + Math.random() * 480, r: 4.5, fill: "#ffe98a" }, g);
      list.push({ f, x0: parseFloat(f.getAttribute("cx")), y0: parseFloat(f.getAttribute("cy")), ph: Math.random() * 9, sp: 0.5 + Math.random() * 0.7 });
    }
    return { node: g, tick(t) { list.forEach(o => { o.f.setAttribute("cx", o.x0 + Math.sin(t * o.sp + o.ph) * 60); o.f.setAttribute("cy", o.y0 + Math.sin(t * (o.sp * 0.8) + o.ph * 2) * 34); o.f.setAttribute("opacity", 0.35 + 0.65 * Math.abs(Math.sin(t * 2.2 + o.ph * 3))); }); } };
  }
  function butterfly(P) {
    const c = (P && P.color) || "#f26d9e";
    const g = el("g", {});
    const f = el("g", {}, g);
    const wL = el("ellipse", { cx: -9, cy: -6, rx: 13, ry: 18, fill: c }, f);
    const wR = el("ellipse", { cx: 9, cy: -6, rx: 13, ry: 18, fill: c }, f);
    el("rect", { x: -3, y: -20, width: 6, height: 30, rx: 3, fill: "#4a3b2e" }, f);
    return {
      node: g,
      tick(t) {
        wL.setAttribute("rx", 4 + Math.abs(Math.sin(t * 14)) * 11);
        wR.setAttribute("rx", 4 + Math.abs(Math.sin(t * 14)) * 11);
        f.setAttribute("transform", `translate(${Math.sin(t * 0.9) * 130},${Math.cos(t * 0.7) * 55 - 40})`);
      },
    };
  }
  function bee() {
    const g = el("g", {});
    const f = el("g", {}, g);
    el("ellipse", { cx: 0, cy: 0, rx: 16, ry: 12, fill: "#ffcf5e" }, f);
    el("rect", { x: -9, y: -12, width: 6, height: 24, fill: "#3a2d1e" }, f);
    el("rect", { x: 2, y: -12, width: 6, height: 24, fill: "#3a2d1e" }, f);
    const wL = el("ellipse", { cx: -4, cy: -16, rx: 10, ry: 6, fill: "rgba(255,255,255,.7)" }, f);
    return {
      node: g,
      tick(t) {
        wL.setAttribute("ry", 2 + Math.abs(Math.sin(t * 30)) * 6);
        f.setAttribute("transform", `translate(${Math.sin(t * 1.6) * 90},${Math.cos(t * 1.1) * 40 - 30})`);
      },
    };
  }
  function fish(P) {
    const c = (P && P.color) || "#ff9a5a";
    const g = el("g", {});
    const f = el("g", {}, g);
    el("ellipse", { cx: 0, cy: 0, rx: 34, ry: 18, fill: c }, f);
    el("path", { d: "M30 0 L52 -14 L52 14 Z", fill: c }, f);
    el("circle", { cx: -18, cy: -4, r: 4, fill: "#23272f" }, f);
    return {
      node: g,
      tick(t) {
        const dir = Math.sin(t * 0.55);
        f.setAttribute("transform", `translate(${Math.sin(t * 0.55) * 110},${Math.sin(t * 1.3) * 12}) scale(${dir > 0 ? 1 : -1},1) rotate(${Math.sin(t * 5) * 6})`);
      },
    };
  }
  function mountains() {
    const g = el("g", {});
    el("path", { d: "M-80 0 L360 -420 L760 0 Z", fill: "#8ea6c0" }, g);
    el("path", { d: "M280 -318 L360 -420 L444 -314 Z", fill: "#e9f1f7" }, g);
    el("path", { d: "M560 0 L980 -330 L1380 0 Z", fill: "#a5b9cf" }, g);
    return { node: g, tick() {} };
  }
  function hills() {
    const g = el("g", {});
    el("ellipse", { cx: 480, cy: 40, rx: 700, ry: 130, fill: "#63b963" }, g);
    el("ellipse", { cx: 1500, cy: 60, rx: 800, ry: 110, fill: "#58ab58" }, g);
    return { node: g, tick() {} };
  }
  function road() {
    const g = el("g", {});
    el("rect", { x: -40, y: -76, width: 2000, height: 84, fill: "#565b63" }, g);
    for (let x = 0; x < 1960; x += 130) el("rect", { x, y: -42, width: 62, height: 9, rx: 4, fill: "rgba(255,255,255,.75)" }, g);
    return { node: g, tick() {} };
  }

  const FACTORIES = {
    man: human, woman: human, boy: human, girl: human, oldman: human,
    cat: () => quadruped({ kind: "cat" }), dog: () => quadruped({ kind: "dog" }),
    bird, butterfly, bee, fish,
    tree, pine, bush, flower, river, pond, house, fence, bench, rock,
    table, chair, bookshelf, sun, moon, clouds, stars, rain, snow,
    fireflies, mountains, hills, road,
  };
  const PROPS = Object.keys(FACTORIES).filter(k => !["man", "woman", "boy", "girl", "oldman", "cat", "dog", "bird"].includes(k));
  const ACTORS = ["man", "woman", "boy", "girl", "oldman", "cat", "dog", "bird"];
  const GESTURES = ["wave", "point", "cheer", "think", "carry", "nod", "shake", "bow", "dance", "spin", "jump", "sit"];

  return { el, clamp01, ease, seg, lerp, TAU, FACTORIES, PROPS, ACTORS, GESTURES };
})();

/* ================= SCENE DRIVER ================= */
window.IVScene = (function () {
  const { el, FACTORIES, ease, seg, clamp01, TAU } = IV;
  const W = 1920, H = 1080;
  const SKY = {
    day: ["#9fd9f2", "#e6f6ff"], sunset: ["#5a4a8a", "#ff9a5a"], night: ["#0e1440", "#2a2f6b"],
  };
  const GROUND = {
    grass: "#7cc45f", sand: "#ecd69a", wood: "#b98a5a", floor: "#caa27a",
    stone: "#a8b0b8", snow: "#eef3f8", water: "#4aa3df", road: "#7f8790",
  };
  let actors = [], props = [], camA, camB, dur, spFrom, spTo, camNode, world;

  function build(scene, duration, speakFrom, speakTo) {
    dur = duration; spFrom = speakFrom == null ? -1 : speakFrom; spTo = speakTo == null ? -1 : speakTo;
    const stage = document.getElementById("stage");
    stage.innerHTML = "";
    const defs = el("div", {}, stage); // placeholder removed later
    defs.remove();
    const timeOfDay = scene.time === "sunset" ? "sunset" : scene.time === "night" ? "night" : "day";
    const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, style: "position:absolute;inset:0" }, stage);
    const d = el("defs", {}, svg);
    const grad = el("linearGradient", { id: "sky", x1: 0, y1: 0, x2: 0, y2: 1 }, d);
    const cols = SKY[timeOfDay];
    el("stop", { offset: "0%", "stop-color": cols[0] }, grad);
    el("stop", { offset: "100%", "stop-color": cols[1] }, grad);
    camNode = el("g", { id: "camera" }, svg);
    const world = el("g", {}, camNode);
    el("rect", { x: -400, y: -300, width: W + 800, height: H + 300, fill: "url(#sky)" }, world);
    const gy = scene.groundY || 920;
    // far scenery first
    (scene.props || []).forEach(p => {
      if (!p || !FACTORIES[p.type]) return;
      const f = FACTORIES[p.type]({ time: timeOfDay, ...p.params });
      const gg = el("g", {}, world);
      gg.appendChild(f.node);
      const yy = p.y == null ? gy : p.y;
      gg.setAttribute("transform", `translate(${p.x == null ? 300 : p.x},${yy}) scale(${p.scale == null ? 1 : p.scale})`);
      props.push({ f, gg, base: gg.getAttribute("transform") });
    });
    const groundC = GROUND[scene.ground] || GROUND.grass;
    el("rect", { x: -400, y: gy, width: W + 800, height: H - gy + 400, fill: groundC }, world);
    if (scene.ground === "wood") for (let x = -400; x < W + 400; x += 160) el("line", { x1: x, y1: gy, x2: x - 60, y2: H + 200, stroke: "rgba(0,0,0,.12)", "stroke-width": 4 }, world);
    // ground-level props (rendered after ground)
    (scene.props || []).forEach((p, i) => {
      if (!p || !FACTORIES[p.type] || (p.y == null)) return;
    });
    // actors
    (scene.actors || []).forEach((a, idx) => {
      if (!a || !FACTORIES[a.type]) return;
      const params = Object.assign({}, a.params || {});
      if (a.type === "oldman") { params.old = true; params.hairstyle = params.hairstyle || "short"; }
      if (a.type === "boy" || a.type === "girl") { params.child = true; }
      if (a.type === "woman" || a.type === "girl") { params.hairstyle = params.hairstyle || (a.type === "woman" ? "long" : "bun"); }
      const rig = FACTORIES[a.type](params);
      const gg = el("g", {}, world);
      gg.appendChild(rig.node);
      const scale = (a.scale == null ? (params.child ? 0.72 : 1) : a.scale);
      actors.push({
        rig, gg, a, scale,
        x: a.x == null ? 400 + idx * 200 : a.x,
        flip: !!a.flip,
        speaker: !!a.speaker,
        emote: a.emote || (timeOfDay === "night" ? "neutral" : "happy"),
        walks: [],
      });
    });
    // precompute walk tracks
    actors.forEach(A => {
      let x = A.x;
      const acts = (A.a.actions || []).slice().sort((u, v) => (u.t && u.t[0] ? u.t[0] : 0) - (v.t && v.t[0] ? v.t[0] : 0));
      acts.forEach(act => {
        if (act.do === "walk" && act.t && act.to != null) {
          A.walks.push({ t0: act.t[0] == null ? 0 : act.t[0], t1: act.t[1] == null ? dur : act.t[1], from: x, to: act.to });
          x = act.to;
        }
      });
      A.walks.sort((u, v) => u.t0 - v.t0);
    });
    camA = (scene.camera && scene.camera.start) || { x: 0, y: 0, zoom: 1 };
    camB = (scene.camera && scene.camera.end) || camA;
    // frame 0 immediately
    IVScene.render(0);
  }

  function render(t) {
    // camera
    const u = ease(clamp01(t / (dur || 1)));
    const cx = lerp(camA.x || 0, camB.x || 0, u), cy = lerp(camA.y || 0, camB.y || 0, u);
    const cz = lerp(camA.zoom || 1, camB.zoom || 1, u);
    camNode.setAttribute("transform", `translate(${W / 2},${H * 0.8}) scale(${cz}) translate(${-(W / 2) - cx},${-(H * 0.8) - cy})`);
    // props
    props.forEach(p => { if (p.f.tick) p.f.tick(t); });
    // actors
    actors.forEach(A => {
      const r = A.rig, S = r.set;
      // position from walk track
      let x = A.x, walking = null;
      for (const wseg of A.walks) {
        if (t >= wseg.t1) x = wseg.to;
        else if (t >= wseg.t0) { walking = wseg; x = lerp(wseg.from, wseg.to, ease(clamp01((t - wseg.t0) / (wseg.t1 - wseg.t0)))); }
      }
      let flip = A.flip;
      if (walking) flip = walking.to < walking.from;
      const acts = (A.a.actions || []).slice().sort((u, v) => (u.t && u.t[0] ? u.t[0] : 0) - (v.t && v.t[0] ? v.t[0] : 0));
      let emote = A.emote;
      acts.forEach(act => {
        if (act.do === "face" && act.t && t >= act.t[0]) flip = !!act.dir;
        if (act.do === "emote" && act.t && t >= act.t[0]) emote = act.name || "happy";
      });
      S.pos(x, sceneGroundY(), A.scale, false);
      S.setFlip(flip);
      // idle breathing + blink
      const breathe = Math.sin(t * 2.1 + A.x * 0.01) * 1.5;
      // walk cycle
      let jumpDy = 0, jumpSq = 0, gest = null;
      for (const act of acts) {
        const t0 = act.t && act.t[0] != null ? act.t[0] : 0, t1 = act.t && act.t[1] != null ? act.t[1] : dur;
        if (t < t0 || t > t1) continue;
        const p = seg(t, t0, t1);
        if (act.do === "gesture") gest = { name: act.name || "wave", p, t, t0, t1 };
        else if (act.do === "jump") { const s = Math.sin(p * Math.PI); jumpDy = -s * 210; jumpSq = (p < 0.12 ? (0.12 - p) * 4 : (p > 0.86 ? (p - 0.86) * 5 : 0)); }
        else if (act.do === "spin") { A.gg.setAttribute("transform", A.gg.dataset.pos + ` rotate(${p * 360})`); }
        else if (act.do === "sit") S.crouch(Math.sin(p * Math.PI) > 0.4 ? 1 : 0);
      }
      if (walking) S.walk(t * TAU * 2.6, Math.min(1, (t - walking.t0) * 2) * Math.min(1, (walking.t1 - t) * 2));
      else S.walk(0, 0);
      // gestures override arms/head
      if (gest) {
        const { name, p } = gest;
        if (name === "wave") { S.armR(-150 + Math.sin(t * 11) * 16 * Math.sin(p * Math.PI)); S.armL(6); }
        else if (name === "point") { S.armR(-78); S.armL(8); S.lean(-3); }
        else if (name === "cheer") { S.armR(-158); S.armL(158); }
        else if (name === "think") { S.armL(-138); S.head(Math.sin(t * 0.8) * 3); }
        else if (name === "carry") { S.armR(-38); S.armL(38); }
        else if (name === "nod") { S.head(Math.sin(p * TAU * 2) * 11); }
        else if (name === "shake") { S.head(Math.sin(p * TAU * 3) * 14); }
        else if (name === "bow") { S.lean(24 * Math.sin(p * Math.PI)); S.head(12 * Math.sin(p * Math.PI)); }
        else if (name === "dance") { S.armR(-120 + Math.sin(t * 8) * 40); S.armL(-120 - Math.sin(t * 8) * 40); S.lean(Math.sin(t * 4) * 6); }
        else if (name === "sit") { S.crouch(1); }
      } else if (!walking) {
        S.armL(4 + breathe); S.armR(-4 - breathe); S.lean(0); S.head(0);
      }
      // talk lip-sync
      const speaking = A.speaker && t >= spFrom && t <= spTo;
      if (speaking) {
        const env = Math.min(1, (t - spFrom) / 0.35) * Math.min(1, (spTo - t) / 0.35);
        const open = (0.25 + 0.75 * Math.abs(Math.sin(t * TAU * 4.2 + Math.sin(t * 6.7) * 0.8))) * env;
        S.mouth(open, 0);
        if (r.kind === "human") S.head(Math.sin(t * TAU * 1.1) * 3.5);
      } else {
        S.mouth(0, emote === "sad" ? -0.4 : 0.8);
      }
      // blink
      const bl = ((t + A.x * 0.013) * 0.36) % 1 < 0.055 ? 1 : 0;
      S.blink(bl);
      S.brows(emote);
      // jump overrides body transform
      if (jumpDy || jumpSq) S.jump(jumpDy, jumpSq);
    });
  }

  function sceneGroundY() { return (window.__SCENE && window.__SCENE.groundY) || 920; }
  const lerp = IV.lerp;
  return { build, render };
})();
