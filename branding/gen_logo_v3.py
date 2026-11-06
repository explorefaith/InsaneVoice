#!/usr/bin/env python3
"""InsaneVoice logo v3 — the approved C1 mark, stripped to pure waveform.
No wordmark, no subtitle, no frame. App icon / favicon / watermark use."""
import os

OUT = os.path.dirname(os.path.abspath(__file__))

CREAM = "#F4EFE6"
INK = "#1A1712"
VERMILLION = "#C9432B"

# same hand-tuned speech-cadence rhythm as the approved C1 logo
HEIGHTS = [70, 128, 100, 190, 148, 252, 336, 300, 452, 380, 262, 210, 160, 122, 82]
ACCENT_INDEX = 8


def svg(bg=CREAM, mark=INK, accent=VERMILLION, rx=72, pad=0.86):
    n = len(HEIGHTS)
    bw, gap = 22, 24
    total = n * bw + (n - 1) * gap
    x0 = (1024 - total * pad) / 2 - (total * (1 - pad) / 2) + (total * (1 - pad) / 2)
    # center the scaled block
    scaled = total * pad
    x0 = (1024 - scaled) / 2
    bars = []
    for i, h in enumerate(HEIGHTS):
        x = x0 + i * (bw + gap) * pad
        hh = h * pad
        y = 512 - hh / 2
        col = accent if i == ACCENT_INDEX else mark
        bars.append(
            f'    <rect x="{x:.0f}" y="{y:.0f}" width="{bw * pad:.0f}" height="{hh:.0f}" '
            f'rx="{bw * pad / 2:.0f}" fill="{col}"/>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  <rect width="1024" height="1024" rx="{rx}" fill="{bg}"/>
{chr(10).join(bars)}
</svg>'''


if __name__ == "__main__":
    with open(os.path.join(OUT, "logo-mark.svg"), "w", encoding="utf-8") as f:
        f.write(svg())                                  # app icon: cream tile
    with open(os.path.join(OUT, "logo-mark-transparent.svg"), "w", encoding="utf-8") as f:
        f.write(svg(bg="none"))                         # watermark / dark use
    with open(os.path.join(OUT, "logo-mark-ink.svg"), "w", encoding="utf-8") as f:
        f.write(svg(bg=INK, mark=CREAM, accent="#E85B3A"))  # dark mode variant
    print("wrote logo-mark.svg, logo-mark-transparent.svg, logo-mark-ink.svg")
