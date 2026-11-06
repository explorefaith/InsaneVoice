#!/usr/bin/env python3
"""InsaneVoice brand logo generator - generates 3 classic SVG logo options."""
import math, os

OUT = os.path.dirname(os.path.abspath(__file__))

GOLD_STOPS = [("0%", "#F3D98B"), ("45%", "#D4AF37"), ("100%", "#8C6D1F")]
IVORY = "#F5EFE0"
INK_TOP, INK_BOT = "#121B2E", "#080C15"


def gold_grad(gid, x1="0%", y1="0%", x2="100%", y2="100%"):
    stops = "".join(
        f'      <stop offset="{o}" stop-color="{c}"/>' for o, c in GOLD_STOPS
    )
    return (
        f'    <linearGradient id="{gid}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">\n'
        f"{stops}\n    </linearGradient>"
    )


def logo_a():
    """The Golden Resonator - crest badge, ring of sound bars, serif IV monogram."""
    cx, cy = 512, 425
    bars = []
    N = 72
    for i in range(N):
        a = 2 * math.pi * i / N
        # deterministic symmetric waveform pattern
        w1 = 0.5 + 0.5 * math.sin(3 * a + 0.7)
        w2 = 0.5 + 0.5 * math.sin(7 * a)
        w3 = 0.5 + 0.5 * math.sin(11 * a + 2.1)
        h = 10 + 54 * (0.55 * w1 + 0.30 * w2 + 0.15 * w3)
        r1, r2 = 172, 172 + h
        x1, y1 = cx + r1 * math.cos(a), cy + r1 * math.sin(a)
        x2, y2 = cx + r2 * math.cos(a), cy + r2 * math.sin(a)
        op = 0.45 + 0.55 * (h - 10) / 54
        bars.append(
            f'      <line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="url(#ag)" stroke-width="7" stroke-linecap="round" opacity="{op:.2f}"/>'
        )
    bars_svg = "\n".join(bars)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  <defs>
{gold_grad("ag")}
{gold_grad("agv", "0%", "0%", "0%", "100%")}
    <linearGradient id="ink" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="{INK_TOP}"/>
      <stop offset="100%" stop-color="{INK_BOT}"/>
    </linearGradient>
    <radialGradient id="glow" cx="50%" cy="42%" r="60%">
      <stop offset="0%" stop-color="#1C2A47" stop-opacity="0.9"/>
      <stop offset="100%" stop-color="#080C15" stop-opacity="0"/>
    </radialGradient>
  </defs>

  <!-- badge -->
  <rect x="8" y="8" width="1008" height="1008" rx="204" fill="url(#ink)"/>
  <rect x="8" y="8" width="1008" height="1008" rx="204" fill="url(#glow)"/>
  <rect x="34" y="34" width="956" height="956" rx="182" fill="none" stroke="url(#ag)" stroke-width="4"/>
  <rect x="58" y="58" width="908" height="908" rx="162" fill="none" stroke="url(#ag)" stroke-width="1.4" opacity="0.45"/>

  <!-- sound ring -->
  <circle cx="{cx}" cy="{cy}" r="150" fill="none" stroke="#D4AF37" stroke-width="1.2" opacity="0.35"/>
{bars_svg}
  <circle cx="{cx}" cy="{cy - 172}" r="7" fill="#F3D98B"/>

  <!-- monogram -->
  <text x="{cx}" y="{cy + 82}" font-family="Georgia, 'Times New Roman', serif" font-size="230"
        font-weight="bold" text-anchor="middle" fill="url(#agv)" letter-spacing="6">IV</text>

  <!-- wordmark -->
  <line x1="182" y1="826" x2="352" y2="826" stroke="#D4AF37" stroke-width="1.2" opacity="0.7"/>
  <rect x="494" y="820" width="12" height="12" transform="rotate(45 500 826)" fill="#D4AF37"/>
  <line x1="636" y1="826" x2="806" y2="826" stroke="#D4AF37" stroke-width="1.2" opacity="0.7"/>
  <text x="512" y="852" font-family="Georgia, 'Times New Roman', serif" font-size="58"
        text-anchor="middle" fill="{IVORY}" letter-spacing="13">INSANEVOICE</text>
  <text x="512" y="912" font-family="Georgia, 'Times New Roman', serif" font-size="24"
        text-anchor="middle" fill="#D4AF37" letter-spacing="9" opacity="0.95">VOICE CLONING STUDIO</text>
</svg>'''


def logo_b():
    """The Royal Seal - circular seal with ring text and harmonic waves."""
    harmonics = []
    for amp, sw, col, op in [(96, 10, IVORY, 0.95), (58, 6, "#D4AF37", 0.9), (30, 3.5, "#8C6D1F", 0.9)]:
        pts = []
        for x in range(232, 793, 7):
            t = (x - 512) / 280.0
            y = 512 + amp * math.sin(t * 2.6 * math.pi) * math.exp(-0.9 * t * t)
            pts.append(f"{x},{y:.1f}")
        harmonics.append(
            f'      <polyline points="{" ".join(pts)}" fill="none" stroke="{col}" '
            f'stroke-width="{sw}" stroke-linecap="round" opacity="{op}"/>'
        )
    harmonics_svg = "\n".join(harmonics)
    ring_text = "\u2605  INSANEVOICE  \u2605  VOICE CLONING STUDIO  \u2605  EST. 2026  "
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  <defs>
{gold_grad("bg1")}
    <radialGradient id="seal" cx="50%" cy="45%" r="65%">
      <stop offset="0%" stop-color="#16223B"/>
      <stop offset="72%" stop-color="#0C1424"/>
      <stop offset="100%" stop-color="#070B13"/>
    </radialGradient>
    <path id="ringpath" d="M 512 64 A 448 448 0 1 1 511.9 64" fill="none"/>
  </defs>

  <circle cx="512" cy="512" r="500" fill="url(#seal)"/>
  <circle cx="512" cy="512" r="496" fill="none" stroke="url(#bg1)" stroke-width="7"/>
  <circle cx="512" cy="512" r="408" fill="none" stroke="url(#bg1)" stroke-width="1.6" opacity="0.7"/>
  <circle cx="512" cy="512" r="318" fill="none" stroke="#D4AF37" stroke-width="1" opacity="0.35"/>

  <text font-family="Georgia, 'Times New Roman', serif" font-size="37" fill="#E5C55F"
        letter-spacing="7">
    <textPath href="#ringpath" startOffset="1%"> {ring_text}</textPath>
  </text>

{harmonics_svg}
  <circle cx="512" cy="512" r="10" fill="#F3D98B"/>
  <circle cx="252" cy="512" r="6" fill="#D4AF37" opacity="0.85"/>
  <circle cx="772" cy="512" r="6" fill="#D4AF37" opacity="0.85"/>
</svg>'''


def logo_c():
    """The Modern Classic - chip with waveform forming a V, refined wordmark."""
    bars = []
    heights = [34, 62, 96, 132, 168, 196, 168, 210, 254, 300, 342, 300, 254, 210, 168, 196, 168, 132, 96, 62, 34]
    n = len(heights)
    gap, bw = 26, 18
    total = n * bw + (n - 1) * gap
    x0 = 512 - total / 2
    for i, h in enumerate(heights):
        x = x0 + i * (bw + gap)
        bars.append(
            f'      <rect x="{x:.0f}" y="{432 - h / 2:.0f}" width="{bw}" height="{h}" rx="{bw / 2}" fill="url(#cg)"/>'
        )
    bars_svg = "\n".join(bars)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  <defs>
    <linearGradient id="cg" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#39D0B8"/>
      <stop offset="55%" stop-color="#2AA79B"/>
      <stop offset="100%" stop-color="#D4AF37"/>
    </linearGradient>
    <linearGradient id="chipbg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0E1416"/>
      <stop offset="100%" stop-color="#081512"/>
    </linearGradient>
  </defs>

  <rect x="8" y="8" width="1008" height="1008" rx="230" fill="url(#chipbg)"/>
  <rect x="8" y="8" width="1008" height="1008" rx="230" fill="none" stroke="#173029" stroke-width="2"/>

{bars_svg}

  <text x="512" y="700" font-family="Georgia, 'Times New Roman', serif" font-size="104"
        text-anchor="middle" fill="{IVORY}">Insane<tspan fill="#39D0B8">Voice</tspan></text>
  <text x="512" y="768" font-family="Georgia, 'Times New Roman', serif" font-size="27"
        text-anchor="middle" fill="#39D0B8" letter-spacing="10" opacity="0.9">FREE \u00b7 PRIVATE \u00b7 YOURS</text>
</svg>'''


def preview_html():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>InsaneVoice - Logo Concepts</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0B0E14; color: #E8E4D8; font-family: Georgia, serif;
         padding: 48px; }
  h1 { text-align: center; font-size: 34px; letter-spacing: 6px; color: #D4AF37;
       font-weight: normal; margin-bottom: 8px; }
  p.sub { text-align: center; opacity: 0.65; margin-bottom: 44px; font-size: 15px;
          letter-spacing: 2px; }
  .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 32px;
          max-width: 1500px; margin: 0 auto; }
  .card { background: #10141D; border: 1px solid #232B3B; border-radius: 20px;
          padding: 28px; text-align: center; }
  .card img { width: 100%; border-radius: 16px; display: block; }
  .tag { display: inline-block; margin-top: 20px; padding: 6px 18px;
         border: 1px solid #D4AF37; color: #D4AF37; border-radius: 999px;
         font-size: 13px; letter-spacing: 3px; }
  .desc { margin-top: 12px; font-size: 14px; opacity: 0.7; line-height: 1.6; }
  .light-row { max-width: 1500px; margin: 48px auto 0; display: grid;
               grid-template-columns: repeat(3, 1fr); gap: 32px; }
  .light { background: #F4F1E8; border-radius: 20px; padding: 28px;
           text-align: center; }
  .light img { width: 55%; }
  .light .tag { border-color: #8C6D1F; color: #8C6D1F; }
</style>
</head>
<body>
  <h1>INSANEVOICE</h1>
  <p class="sub">THREE CLASSIC LOGO CONCEPTS &mdash; PICK YOUR FAVOURITE</p>
  <div class="grid">
    <div class="card">
      <img src="logo-a.svg" alt="Logo A">
      <span class="tag">A &mdash; THE GOLDEN RESONATOR</span>
      <p class="desc">Crest badge with a crown of sound bars and serif IV monogram.
         Deep ink &amp; champagne gold &mdash; timeless, premium, studio-grade.</p>
    </div>
    <div class="card">
      <img src="logo-b.svg" alt="Logo B">
      <span class="tag">B &mdash; THE ROYAL SEAL</span>
      <p class="desc">Circular wax-seal emblem with harmonic sound waves and ring
         typography. Feels like a mark of authenticity &mdash; for a serious tool.</p>
    </div>
    <div class="card">
      <img src="logo-c.svg" alt="Logo C">
      <span class="tag">C &mdash; THE MODERN CLASSIC</span>
      <p class="desc">Refined chip with a teal-to-gold waveform. Cleaner, more
         product-like &mdash; friendly for GitHub and app icons.</p>
    </div>
  </div>
  <div class="light-row">
    <div class="light"><img src="logo-a.svg" alt=""><span class="tag">A ON LIGHT</span></div>
    <div class="light"><img src="logo-b.svg" alt=""><span class="tag">B ON LIGHT</span></div>
    <div class="light"><img src="logo-c.svg" alt=""><span class="tag">C ON LIGHT</span></div>
  </div>
</body>
</html>"""


if __name__ == "__main__":
    for name, fn in [("logo-a.svg", logo_a), ("logo-b.svg", logo_b), ("logo-c.svg", logo_c)]:
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            f.write(fn())
        print("wrote", name)
    with open(os.path.join(OUT, "preview.html"), "w", encoding="utf-8") as f:
        f.write(preview_html())
    print("wrote preview.html")
