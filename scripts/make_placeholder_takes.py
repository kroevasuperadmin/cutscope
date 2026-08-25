#!/usr/bin/env python3
"""Generate the four practice-mode placeholder takes.

These are NOT AI-generated footage and must never be mistaken for it. Practice mode
replays a scripted production without calling any paid API, so there is no real take to
show. Each clip is a designed slate in that shot's colour palette, carrying the shot
number, the shot name, and a persistent SCRIPTED PLACEHOLDER mark.

The previous placeholder was a single FFmpeg SMPTE colour-bar test pattern reused for
every shot, which is a poor look for a film-production tool.

Run:  python scripts/make_placeholder_takes.py
Out:  public/take-<shot-id>.mp4   (720p, 4s, H.264, silent)
"""
import shutil
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "public"
FONT = "C\\:/Windows/Fonts/consola.ttf"      # ffmpeg drawtext wants the colon escaped
FONT_B = "C\\:/Windows/Fonts/arialbd.ttf"

# (shot id, shot number, title, era, top colour, bottom colour, accent)
SHOTS = [
    ("warehouse-displacement", "01", "WAREHOUSE DISPLACEMENT", "2024",
     "#12161d", "#1d2530", "#8fb3d9"),
    ("first-sighting-2012", "02", "FIRST SIGHTING", "2012",
     "#2a2013", "#4a3620", "#e0a94f"),
    ("arcade-coaching", "03", "ARCADE COACHING", "2012",
     "#1a0f22", "#2d1440", "#c774e8"),
    ("the-field-2012", "04", "THE FIELD", "2012",
     "#241d10", "#4a3d1d", "#d9b45c"),
]

DUR = 4
W, H = 1280, 720


def build(shot_id, num, title, era, top, bottom, accent):
    out = OUT / f"take-{shot_id}.mp4"
    # gradient + slow drift + grain, then type. Grain and the drift keep it from
    # reading as a static error card.
    vf = (
        f"gradients=s={W}x{H}:c0={top}:c1={bottom}:x0=0:y0=0:x1={W}:y1={H}:d={DUR},"
        f"noise=alls=4:allf=t,"
        f"zoompan=z='min(zoom+0.0006,1.06)':d={DUR*25}:s={W}x{H}:fps=25,"
        f"drawbox=x=0:y=0:w={W}:h={H}:color=black@0.20:t=fill,"
        f"drawtext=fontfile='{FONT_B}':text='{num}':fontsize=190:fontcolor={accent}@0.20"
        f":x=80:y=(h-text_h)/2-40,"
        f"drawtext=fontfile='{FONT_B}':text='{title}':fontsize=52:fontcolor=white@0.92"
        f":x=80:y=h/2-10,"
        f"drawtext=fontfile='{FONT}':text='TURNING POINT   S1   {era}':fontsize=22"
        f":fontcolor={accent}@0.80:x=82:y=h/2+62,"
        f"drawtext=fontfile='{FONT}':text='SCRIPTED PLACEHOLDER   no paid API called'"
        f":fontsize=19:fontcolor=white@0.42:x=82:y=h-52,"
        f"format=yuv420p"
    )
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:d={DUR}:r=25",
        "-filter_complex", vf, "-an",
        "-c:v", "libx264", "-preset", "slow", "-crf", "30", "-t", str(DUR),
        str(out),
    ]
    subprocess.run(cmd, check=True)
    return out


def main():
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found on PATH")
    OUT.mkdir(parents=True, exist_ok=True)
    for s in SHOTS:
        p = build(*s)
        print(f"{p.stat().st_size:>9,} bytes  {p.name}")


if __name__ == "__main__":
    main()
