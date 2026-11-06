#!/usr/bin/env python3
"""InsaneVoice logo v2 - human-crafted, print-label aesthetic. Flat colors only."""
import os

OUT = os.path.dirname(os.path.abspath(__file__))

CREAM = "#F4EFE6"
INK = "#1A1712"
INK_SOFT = "#5C564A"
VERMILLION = "#C9432B"
VERMILLION_DARKBG = "#E85B3A"
COBALT = "#2B4C9B"

# speech-cadence rhythm: rises, small dip, deliberate peak, falls - NOT symmetric
HEIGHTS = [70, 128, 100, 190, 148, 252, 336, 300, 452, 380, 262, 210, 160, 122, 82]
ACCENT_INDEX = 8  # the deliberate peak gets the single accent colour


def bars(mark_color, accent_color, center_y=352):
    n = len(HEIGHTS)
    bw, gap = 22, 24
    total = n * bw + (n - 1) * gap
    x0 = (1024 - total) / 2
    out = []
    for i, h in enumerate(HEIGHTS):
        x = x0 + i * (bw + gap)
        y = center_y - h / 2
        col = accent_color if i == ACCENT_INDEX else mark_color
        out.append(
            f'    <rect x="{x:.0f}" y="{y:.0f}" width="{bw}" height="{h}" rx="5" fill="{col}"/>'
        )
    return "\n".join(out)


def wordmark(text_color, accent_color, dot=True):
    dot_svg = f'<tspan fill="{accent_color}">.</tspan>' if dot else ""
    sub = (
        f'  <text x="512" y="784" font-family="Georgia, \'Times New Roman\', serif" font-size="27"\n'
        f'        text-anchor="middle" fill="{text_color}" opacity="0.72"\n'
        f'        letter-spacing="11">VOICE CLONING STUDIO</text>'
    )
    main = (
        f'  <text x="512" y="700" font-family="Georgia, \'Times New Roman\', serif" font-size="118"\n'
        f'        text-anchor="middle" fill="{text_color}">InsaneVoice{dot_svg}</text>'
    )
    return main + "\n" + sub


def frame(stroke_color, outer_op="1.0", inner_op="0.55"):
    return (
        f'  <rect x="66" y="66" width="892" height="892" rx="26" fill="none" '
        f'stroke="{stroke_color}" stroke-width="3" opacity="{outer_op}"/>\n'
        f'  <rect x="88" y="88" width="848" height="848" rx="16" fill="none" '
        f'stroke="{stroke_color}" stroke-width="1.4" opacity="{inner_op}"/>'
    )


def svg(bg, mark_color, accent, text_color, frame_color, name):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  <rect width="1024" height="1024" rx="72" fill="{bg}"/>
{frame(frame_color)}

{bars(mark_color, accent)}

{wordmark(text_color, accent)}
<!-- {name} -->
</svg>'''


VARIANTS = {
    "logo-c1.svg": svg(CREAM, INK, VERMILLION, INK, INK, "C1 Print Label - vermillion"),
    "logo-c2.svg": svg(INK, CREAM, VERMILLION_DARKBG, CREAM, CREAM, "C2 Ink Edition - warm black"),
    "logo-c3.svg": svg(CREAM, INK, COBALT, INK, INK, "C3 Print Label - cobalt"),
}


def preview_html():
    cards = ""
    for i, fname in enumerate(VARIANTS):
        tag = ["C1 &mdash; PRINT LABEL", "C2 &mdash; INK EDITION", "C3 &mdash; COBALT PRESS"][i]
        desc = [
            "Warm paper &amp; ink with a single vermillion peak &mdash; vintage record-label energy.",
            "Same mark on warm ink &mdash; for dark UI, GitHub social preview, app icon.",
            "Cobalt accent on paper &mdash; calmer, more editorial.",
        ][i]
        cards += f'''
    <div class="card">
      <img src="{fname}" alt="{tag}">
      <span class="tag">{tag}</span>
      <p class="desc">{desc}</p>
    </div>'''
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>InsaneVoice - Logo v2</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #14120D; color: #E8E4D8; font-family: Georgia, serif; padding: 48px; }}
  h1 {{ text-align: center; font-size: 30px; letter-spacing: 5px; color: #C9432B; font-weight: normal; margin-bottom: 8px; }}
  p.sub {{ text-align: center; opacity: 0.6; margin-bottom: 40px; font-size: 14px; letter-spacing: 2px; }}
  .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 30px; max-width: 1480px; margin: 0 auto; }}
  .card {{ background: #1C1913; border: 1px solid #2E2A20; border-radius: 16px; padding: 24px; text-align: center; }}
  .card img {{ width: 100%; border-radius: 10px; display: block; }}
  .tag {{ display: inline-block; margin-top: 18px; padding: 5px 16px; border: 1px solid #C9432B; color: #E85B3A; border-radius: 999px; font-size: 12px; letter-spacing: 3px; }}
  .desc {{ margin-top: 10px; font-size: 13.5px; opacity: 0.65; line-height: 1.6; }}
</style>
</head>
<body>
  <h1>INSANEVOICE &mdash; v2</h1>
  <p class="sub">FLAT &middot; PRINTED &middot; HAND-TUNED RHYTHM &mdash; NO GRADIENTS, NO AI GLOW</p>
  <div class="grid">{cards}
  </div>
</body>
</html>'''


if __name__ == "__main__":
    for name, content in VARIANTS.items():
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            f.write(content)
        print("wrote", name)
    with open(os.path.join(OUT, "preview2.html"), "w", encoding="utf-8") as f:
        f.write(preview_html())
    print("wrote preview2.html")
