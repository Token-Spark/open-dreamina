#!/usr/bin/env python3
"""Generate the scrolling end-credits overlay image (transparent PNG) for
APHRODITE: OUTCAST OF OLYMPUS.

Output: ./data/credits/credits.png  (720px wide, height dynamic)

The image is a tall transparent PNG.  ffmpeg scrolls it over the AI-generated
background video to produce the final credits clip.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ── paths ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "credits" / "credits.png"

# ── fonts (host-side, verified available) ─────────────────────────────────
FONT_REGULAR = "/System/Library/Fonts/STHeiti Medium.ttc"
FONT_LIGHT   = "/System/Library/Fonts/STHeiti Light.ttc"

# ── canvas ────────────────────────────────────────────────────────────────
W = 720                       # width  (matches 720p 9:16)
PAD_X = 70                   # horizontal padding
PAD_TOP = 160               # blank space above title (so it scrolls in)
PAD_BOTTOM = 1280            # blank space below (so last line scrolls out)
BG_ALPHA = 168              # 0-255 overlay darkness (≈ 66 %)

# ── colours ──────────────────────────────────────────────────────────────
WHITE  = (255, 255, 255)
GOLD   = (212, 175, 55)
GREY   = (180, 180, 190)

# ── content ──────────────────────────────────────────────────────────────
TITLE       = "APHRODITE: OUTCAST OF OLYMPUS"
SUBTITLE    = "A TOKEN SPARK AI PRODUCTION"

CREDITS = [
    "Executive Producer",
    "Producer",
    "Writer",
    "Director",
    "Cinematography",
    "Production Design",
    "Visual Effects Supervisor",
    "Editor",
    "Sound Designer",
    "Music Composer",
    "Colorist",
    "Storyboard Artist",
    "Costume Designer",
]
NAME = "Kun Liu (Louis)"

TOOLS_TITLE = "PRODUCTION TOOLS"
TOOLS = [
    ("Open Dreamina", "AIGC Creation Platform"),
    ("DeepSeek",       "AI Writing & Reasoning"),
    ("ZCode",          "AI Coding Agent"),
    ("Trae",           "AI Development Environment"),
    ("Token Spark",    "AI Computing Solutions"),
]

CREATED_BY = "Created by"
SIGNATURE  = "KUN LIU (LOUIS)"
COPYRIGHT  = "© 2026 TOKEN SPARK AI"


# ── helpers ───────────────────────────────────────────────────────────────
def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_REGULAR if bold else FONT_LIGHT, size)


def text_size(draw: ImageDraw.ImageDraw, txt: str, fnt) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), txt, font=fnt)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


# ── build ─────────────────────────────────────────────────────────────────
def build():
    # 1. measure total height with a dummy 1px image
    dummy = Image.new("RGBA", (1, 1))
    dd = ImageDraw.Draw(dummy)

    sections: list[tuple[str, str]] = []   # (kind, payload)  rendered later

    f_title = font(32)
    f_sub   = font(26, bold=False)
    f_role  = font(28, bold=False)
    f_name  = font(28)
    f_tools_h = font(26)
    f_tool   = font(24)
    f_tool_d = font(20, bold=False)
    f_sig   = font(32)
    f_copy  = font(22, bold=False)

    y = PAD_TOP
    line_h = 52

    # title
    sections.append(("center", (TITLE, f_title, GOLD, y)))
    y += text_size(dd, TITLE, f_title)[1] + 14
    sections.append(("center", (SUBTITLE, f_sub, GREY, y)))
    y += text_size(dd, SUBTITLE, f_sub)[1] + 60

    # credits (role left / name right with dot leaders)
    for role in CREDITS:
        sections.append(("role", (role, NAME, f_role, f_name, y)))
        y += line_h
    y += 70

    # tools
    sections.append(("center", (TOOLS_TITLE, f_tools_h, GOLD, y)))
    y += text_size(dd, TOOLS_TITLE, f_tools_h)[1] + 36
    for tool, desc in TOOLS:
        sections.append(("tool", (tool, desc, f_tool, f_tool_d, y)))
        y += 46
    y += 70

    # signature
    sections.append(("center", (CREATED_BY, f_copy, GREY, y)))
    y += text_size(dd, CREATED_BY, f_copy)[1] + 18
    sections.append(("center", (SIGNATURE, f_sig, WHITE, y)))
    y += text_size(dd, SIGNATURE, f_sig)[1] + 30
    sections.append(("center", (COPYRIGHT, f_copy, GREY, y)))
    y += text_size(dd, COPYRIGHT, f_copy)[1]

    total_h = PAD_TOP + (y - PAD_TOP) + PAD_BOTTOM

    # 2. draw onto the real canvas
    img = Image.new("RGBA", (W, total_h))
    draw = ImageDraw.Draw(img)

    # semi-transparent dark scrim so text reads over any background
    draw.rectangle([0, 0, W, total_h], fill=(8, 8, 16, BG_ALPHA))

    for kind, payload in sections:
        if kind == "center":
            txt, fnt, color, yy = payload
            tw, _ = text_size(draw, txt, fnt)
            draw.text(((W - tw) / 2, yy), txt, font=fnt, fill=color)
        elif kind == "role":
            role, name, f_r, f_n, yy = payload
            # role: left
            draw.text((PAD_X, yy), role, font=f_r, fill=WHITE)
            # name: right
            nw, _ = text_size(draw, name, f_n)
            draw.text((W - PAD_X - nw, yy), name, font=f_n, fill=GOLD)
            # dot leaders
            rw, _ = text_size(draw, role, f_r)
            gap_x = PAD_X + rw + 20
            name_x = W - PAD_X - nw - 20
            dot_y = yy + f_r.size * 0.42
            dot = "·"
            f_dot = font(20, bold=False)
            dot_w, _ = text_size(draw, dot, f_dot)
            x = gap_x
            while x + dot_w / 2 < name_x:
                draw.text((x, dot_y), dot, font=f_dot, fill=(90, 90, 110))
                x += dot_w + 10
        elif kind == "tool":
            tool, desc, f_t, f_d, yy = payload
            draw.text((PAD_X, yy), tool, font=f_t, fill=WHITE)
            dw, _ = text_size(draw, desc, f_d)
            draw.text((W - PAD_X - dw, yy + 4), desc, font=f_d, fill=GREY)

    img.save(str(OUT))
    print(f"[credits] {OUT}  {W}x{total_h}")
    return total_h


if __name__ == "__main__":
    build()
