#!/usr/bin/env python3
"""
vref.py - Video Reference builder.

Give it a video URL (YouTube, Facebook, TikTok, Instagram, Vimeo, direct mp4...)
and it produces a folder Claude can read to fully "understand" the video:

  library/<slug>/
    REFERENCE.md      <- start here (Claude reads this)
    meta.json         <- title, uploader, duration, description, url
    transcript.md     <- timestamped transcript
    transcript.txt    <- plain text transcript
    sheets/           <- labelled contact sheets (3x3 grids of keyframes)
    frames/           <- individual full-size keyframes
    video.mp4         <- source video (deleted unless --keep-video)

Usage:
    python vref.py <url>
    python vref.py <url> --name my-slug --frames 45 --model small
    python vref.py <url> --cookies chrome        # for login-walled FB/IG videos
    python vref.py <url> --keep-video
    python vref.py --queue queue.txt             # run a file of vref commands in turn
"""

import argparse
import importlib.util
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIBRARY = ROOT / "library"
COOKIE_DIR = ROOT / "cookies"
QUEUE_LOGS = LIBRARY / "_logs"
QUEUE_REASON_ENV = "VREF_QUEUE_REASON"  # file a queued run writes its failure reason to

SHEET_COLS = 3
SHEET_ROWS = 3
FRAME_WIDTH = 1024
SHEET_TILE_WIDTH = 640

# whisper language code -> extra tags platforms use for the same language
SUB_LANG_ALIASES = {
    "he": ["iw"],
    "jw": ["jv"],
    "no": ["nb", "nn"],
    "yue": ["zh-HK"],
}


# ---------------------------------------------------------------- helpers

def log(msg):
    print(f"[vref] {msg}", flush=True)


def run(cmd, **kw):
    """Run a command, return CompletedProcess. Never raises."""
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", **kw
    )


def slugify(text, fallback="video"):
    text = re.sub(r"[^\w\s-]", "", (text or "").strip().lower())
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    return (text[:60] or fallback)


def ts(seconds):
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def ts_file(seconds):
    return ts(seconds).replace(":", "-")


# ---------------------------------------------------------------- download

def find_cookie_file(url, explicit=None):
    """Pick a cookies.txt for this site from video-ref/cookies/ (Netscape format).

    Chromium's app-bound encryption on Windows makes --cookies-from-browser
    unusable, so a one-time exported cookies file is the reliable path.
    Name files after the site: youtube.txt, facebook.txt, instagram.txt...
    A cookies/default.txt is used when nothing more specific matches.
    """
    if explicit:
        p = Path(explicit)
        if not p.exists():
            raise SystemExit(f"Cookies file not found: {p}")
        return p
    if not COOKIE_DIR.is_dir():
        return None
    host = re.sub(r"^www\.", "", (re.search(r"https?://([^/]+)", url) or
                                  re.match(r"()", url)).group(1) if "://" in url else "")
    for p in sorted(COOKIE_DIR.glob("*.txt")):
        if p.stem.lower() != "default" and p.stem.lower() in host.lower():
            return p
    default = COOKIE_DIR / "default.txt"
    return default if default.exists() else None


def lang_tags(language):
    return [language] + SUB_LANG_ALIASES.get(language, [])


def sub_lang_patterns(language):
    """--sub-langs value for yt-dlp; each entry is a regex matched against the whole tag."""
    if not language:
        return "en.*,ur.*,hi.*"
    return ",".join(f"{re.escape(t)}(-.*)?" for t in lang_tags(language))


def download(url, workdir, cookies=None, cookie_file=None, quality=720, language=None):
    workdir.mkdir(parents=True, exist_ok=True)
    fmt = f"bv*[height<={quality}]+ba/b[height<={quality}]/bv*+ba/b"
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", fmt,
        "--merge-output-format", "mp4",
        "--write-info-json",
        "--write-subs", "--write-auto-subs",
        "--sub-langs", sub_lang_patterns(language),
        "--convert-subs", "srt",
        "--no-playlist",
        "--retries", "5",
        "--ignore-errors",  # a failed subtitle fetch (e.g. HTTP 429) shouldn't kill the video
        "--no-warnings",
        "-o", str(workdir / "source.%(ext)s"),
        url,
    ]
    base_cmd = list(cmd)
    if cookies:
        cmd += ["--cookies-from-browser", cookies]
    elif cookie_file:
        log(f"using cookies file: {cookie_file.name}")
        cmd += ["--cookies", str(cookie_file)]

    def got_video():
        return sorted(
            [p for p in workdir.glob("source.*")
             if p.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}],
            key=lambda p: p.stat().st_size, reverse=True,
        )

    log("downloading video...")
    res = run(cmd)
    if res.returncode != 0 and not got_video() and (cookies or cookie_file):
        # stale/rotated cookies (e.g. YouTube's "The page needs to be reloaded")
        # can break videos that would download fine anonymously
        log("download with cookies failed, retrying without cookies...")
        for p in workdir.glob("source.*"):
            p.unlink(missing_ok=True)
        res = run(base_cmd)
        if got_video():
            log("worked without cookies - your cookies file is probably stale")
    videos = got_video()
    if res.returncode != 0 and videos:
        log("some extras (e.g. platform subtitles) failed to download - continuing")
    if not videos:
        tail = (res.stderr or res.stdout or "").strip().splitlines()[-12:]
        host = re.sub(r"^www\.", "", (re.search(r"https?://([^/]+)", url) or
                                      re.match(r"()", url)).group(1))
        site = host.split(".")[-2] if host.count(".") else "default"
        raise SystemExit(
            "yt-dlp failed:\n  " + "\n  ".join(tail) + "\n\n"
            "If the site is asking you to sign in / prove you are not a bot:\n"
            "  export your own cookies with the browser extension\n"
            "  'Get cookies.txt LOCALLY' from a private/incognito window\n"
            "  (then close that window so the site doesn't rotate them),\n"
            f"  save as Netscape format to {COOKIE_DIR / (site + '.txt')}\n"
            "  and run this command again. A stale cookies file can also\n"
            "  cause this - try deleting it."
        )
    return videos[0]


def load_meta(workdir, url):
    info_files = list(workdir.glob("source.info.json"))
    data = {}
    if info_files:
        try:
            data = json.loads(info_files[0].read_text(encoding="utf-8"))
        except Exception:
            data = {}
    return {
        "url": url,
        "title": data.get("title") or "Untitled video",
        "uploader": data.get("uploader") or data.get("channel") or "",
        "upload_date": data.get("upload_date") or "",
        "duration": data.get("duration") or 0,
        "view_count": data.get("view_count"),
        "like_count": data.get("like_count"),
        "extractor": data.get("extractor_key") or "",
        "webpage_url": data.get("webpage_url") or url,
        "description": (data.get("description") or "").strip(),
        "width": data.get("width"),
        "height": data.get("height"),
        "fps": data.get("fps"),
    }


def probe_duration(video):
    res = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", str(video)])
    try:
        return float(res.stdout.strip())
    except Exception:
        return 0.0


# ---------------------------------------------------------------- transcript

def parse_srt(path):
    raw = path.read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"\n\s*\n", raw.strip())
    segs = []
    for block in blocks:
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        time_line = next((l for l in lines if "-->" in l), None)
        if not time_line:
            continue
        m = re.search(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)",
                      time_line)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        idx = lines.index(time_line)
        text = " ".join(lines[idx + 1:])
        text = re.sub(r"<[^>]+>", "", text).strip()
        if text:
            segs.append({"start": start, "end": end, "text": text})

    # auto-subs repeat lines heavily -> drop consecutive duplicates
    cleaned = []
    for s in segs:
        if cleaned and s["text"] == cleaned[-1]["text"]:
            cleaned[-1]["end"] = s["end"]
            continue
        if cleaned and s["text"].startswith(cleaned[-1]["text"]):
            cleaned[-1] = s
            continue
        cleaned.append(s)
    return cleaned


def subs_from_download(workdir, language=None):
    tagged = []
    for p in sorted(workdir.glob("source*.srt")):
        m = re.search(r"source\.([\w-]+)\.srt", p.name)
        tagged.append((p, m.group(1) if m else ""))
    if language:
        # only accept captions in the requested language
        wanted = lang_tags(language)
        tagged = [(p, tag) for p, tag in tagged
                  if tag in wanted or tag.split("-")[0] in wanted]
    else:
        # prefer english, else whatever exists
        tagged.sort(key=lambda pt: not pt[1].startswith("en"))
    if not tagged:
        return None, None
    preferred, tag = tagged[0]
    segs = parse_srt(preferred)
    if not segs:
        return None, None
    return segs, f"platform captions ({tag or 'unknown'})"


def whisper_transcribe(video, workdir, model_size="base", language=None):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        log("faster-whisper not installed -> skipping transcription")
        return None, None

    wav = workdir / "audio.wav"
    log("extracting audio...")
    res = run(["ffmpeg", "-y", "-i", str(video), "-vn",
               "-ac", "1", "-ar", "16000", str(wav)])
    if res.returncode != 0 or not wav.exists():
        log("audio extraction failed -> skipping transcription")
        return None, None

    log(f"transcribing with faster-whisper ({model_size})... this can take a while")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    if ((language is not None) and (language not in model.supported_languages)):
        raise SystemExit(
            f"Language \"{language}\" isn't supported by model \"{model_size}\". "
            f"Supported: {', '.join(model.supported_languages)}"
        )

    segments, info = model.transcribe(str(wav), beam_size=5, vad_filter=True, language=language)

    segs = [{"start": s.start, "end": s.end, "text": s.text.strip()}
            for s in segments if s.text.strip()]
    wav.unlink(missing_ok=True)
    how = "set" if language else "detected"
    return segs, f"faster-whisper {model_size} ({how} language: {info.language})"


# ---------------------------------------------------------------- frames

def scene_timestamps(video, threshold=0.30):
    res = run(["ffmpeg", "-i", str(video), "-vf",
               f"select='gt(scene,{threshold})',metadata=print:file=-",
               "-an", "-f", "null", "-"])
    out = (res.stdout or "") + (res.stderr or "")
    return [float(m) for m in re.findall(r"pts_time:([\d.]+)", out)]


def pick_timestamps(video, duration, target):
    marks = []
    if duration > 6:
        scenes = scene_timestamps(video)
        log(f"scene changes detected: {len(scenes)}")
        marks.extend(scenes)
    # always add an even grid so nothing long is skipped
    grid = max(target, 8)
    marks.extend([duration * (i + 0.5) / grid for i in range(grid)])

    marks = sorted(t for t in marks if 0.2 <= t <= max(0.3, duration - 0.2))
    min_gap = max(1.0, duration / (target * 2.5)) if duration else 1.0
    spaced = []
    for t in marks:
        if not spaced or t - spaced[-1] >= min_gap:
            spaced.append(t)

    if len(spaced) > target:  # thin out evenly, keep first and last
        step = len(spaced) / target
        spaced = [spaced[min(len(spaced) - 1, int(i * step))] for i in range(target)]
    return spaced


def extract_frames(video, timestamps, frames_dir):
    frames_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for i, t in enumerate(timestamps, 1):
        path = frames_dir / f"f{i:03d}_{ts_file(t)}.jpg"
        res = run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(video),
                   "-frames:v", "1", "-vf", f"scale={FRAME_WIDTH}:-2",
                   "-q:v", "4", str(path)])
        if res.returncode == 0 and path.exists() and path.stat().st_size > 0:
            out.append({"index": i, "time": t, "path": path})
    log(f"frames extracted: {len(out)}")
    return out


def build_sheets(frames, sheets_dir):
    from PIL import Image, ImageDraw, ImageFont

    sheets_dir.mkdir(parents=True, exist_ok=True)
    try:
        font = ImageFont.truetype("arial.ttf", 26)
    except Exception:
        font = ImageFont.load_default()

    per_sheet = SHEET_COLS * SHEET_ROWS
    sheets = []
    for s in range(math.ceil(len(frames) / per_sheet)):
        chunk = frames[s * per_sheet:(s + 1) * per_sheet]
        tiles = []
        for f in chunk:
            img = Image.open(f["path"]).convert("RGB")
            ratio = SHEET_TILE_WIDTH / img.width
            img = img.resize((SHEET_TILE_WIDTH, max(1, int(img.height * ratio))))
            d = ImageDraw.Draw(img)
            label = f"#{f['index']}  {ts(f['time'])}"
            d.rectangle([0, 0, 230, 40], fill=(0, 0, 0))
            d.text((10, 6), label, fill=(255, 235, 0), font=font)
            tiles.append(img)

        tile_h = max(t.height for t in tiles)
        pad = 8
        sheet = Image.new(
            "RGB",
            (SHEET_COLS * SHEET_TILE_WIDTH + pad * (SHEET_COLS + 1),
             SHEET_ROWS * tile_h + pad * (SHEET_ROWS + 1)),
            (18, 18, 20),
        )
        for i, t in enumerate(tiles):
            r, c = divmod(i, SHEET_COLS)
            sheet.paste(t, (pad + c * (SHEET_TILE_WIDTH + pad),
                            pad + r * (tile_h + pad)))
        path = sheets_dir / f"sheet{s + 1:02d}.jpg"
        sheet.save(path, quality=82)
        sheets.append({
            "path": path,
            "first": chunk[0]["index"],
            "last": chunk[-1]["index"],
            "start": chunk[0]["time"],
            "end": chunk[-1]["time"],
        })
    log(f"contact sheets built: {len(sheets)}")
    return sheets


# ---------------------------------------------------------------- writing

def write_transcript(segs, source, outdir):
    if not segs:
        (outdir / "transcript.md").write_text(
            "# Transcript\n\n_No transcript could be produced for this video._\n",
            encoding="utf-8")
        return 0

    lines = [f"# Transcript\n", f"Source: {source}\n"]
    for s in segs:
        lines.append(f"**[{ts(s['start'])}]** {s['text']}")
    (outdir / "transcript.md").write_text("\n\n".join(lines), encoding="utf-8")

    plain = " ".join(s["text"] for s in segs)
    (outdir / "transcript.txt").write_text(plain, encoding="utf-8")
    return len(plain.split())


def transcript_around(segs, start, end):
    if not segs:
        return ""
    hits = [s["text"] for s in segs if s["start"] < end and s["end"] > start]
    text = " ".join(hits)
    return (text[:400] + "...") if len(text) > 400 else text


def write_reference(outdir, meta, segs, source, frames, sheets, words, duration):
    rel = lambda p: p.relative_to(outdir).as_posix()
    d = meta.get("duration") or duration

    md = []
    md.append(f"# Video reference: {meta['title']}\n")
    md.append("> **How to use this folder (for Claude):** read this file top to "
              "bottom, then open every image in `sheets/` — those contact sheets "
              "ARE the video's visuals, each tile labelled `#frame  timestamp`. "
              "For a closer look at any tile, open the matching full-size image "
              "in `frames/`. Match a frame's timestamp against `transcript.md` to "
              "know what was being said over that visual. Only after seeing the "
              "sheets should you describe or reuse the video's design, layout, "
              "editing style, or on-screen text.\n")

    md.append("## Metadata\n")
    md.append(f"- **URL:** {meta['webpage_url']}")
    md.append(f"- **Platform:** {meta['extractor'] or 'unknown'}")
    if meta["uploader"]:
        md.append(f"- **Uploader:** {meta['uploader']}")
    if meta["upload_date"]:
        u = meta["upload_date"]
        md.append(f"- **Published:** {u[:4]}-{u[4:6]}-{u[6:]}" if len(u) == 8 else f"- **Published:** {u}")
    md.append(f"- **Duration:** {ts(d)} ({int(d)}s)")
    if meta.get("width"):
        orient = "vertical / reel" if (meta.get("height") or 0) > (meta.get("width") or 0) else "horizontal"
        md.append(f"- **Resolution:** {meta['width']}x{meta['height']} ({orient})")
    if meta.get("view_count") is not None:
        md.append(f"- **Views:** {meta['view_count']:,}")
    if meta.get("like_count") is not None:
        md.append(f"- **Likes:** {meta['like_count']:,}")
    md.append(f"- **Transcript source:** {source or 'none'}")
    md.append(f"- **Transcript length:** {words} words")
    md.append(f"- **Keyframes:** {len(frames)} in `frames/`, tiled into "
              f"{len(sheets)} contact sheet(s) in `sheets/`\n")

    if meta["description"]:
        desc = meta["description"]
        desc = desc[:2000] + ("\n\n_[description truncated]_" if len(desc) > 2000 else "")
        md.append("## Author's description\n")
        md.append("```\n" + desc + "\n```\n")

    md.append("## Visuals — open these images first\n")
    md.append("| Sheet | Frames | Covers | What is being said there |")
    md.append("|---|---|---|---|")
    for s in sheets:
        say = transcript_around(segs, s["start"], s["end"]).replace("|", "/")
        say = (say[:150] + "...") if len(say) > 150 else (say or "—")
        md.append(f"| `{rel(s['path'])}` | #{s['first']}–#{s['last']} | "
                  f"{ts(s['start'])}–{ts(s['end'])} | {say} |")
    md.append("")

    md.append("<details>\n<summary>Full keyframe index (open individually for detail)</summary>\n")
    md.append("| # | Time | File |")
    md.append("|---|---|---|")
    for f in frames:
        md.append(f"| {f['index']} | {ts(f['time'])} | `{rel(f['path'])}` |")
    md.append("\n</details>\n")

    md.append("## Transcript\n")
    if segs:
        md.append("Full timestamped transcript: `transcript.md` "
                  "(plain text: `transcript.txt`).\n")
        md.append("### Preview\n")
        for s in segs[:25]:
            md.append(f"**[{ts(s['start'])}]** {s['text']}\n")
        if len(segs) > 25:
            md.append(f"_... {len(segs) - 25} more segments in `transcript.md`._\n")
    else:
        md.append("_No transcript available (no speech, or captions unavailable)._\n")

    md.append("## Reference notes\n")
    md.append("_Claude: after reading the sheets + transcript, fill this in — "
              "structure/beats, visual style (palette, typography, layout, motion, "
              "pacing), on-screen text, hooks and CTAs, and what is worth copying. "
              "This section is what makes the folder reusable later._\n")

    (outdir / "REFERENCE.md").write_text("\n".join(md), encoding="utf-8")


# ---------------------------------------------------------------- queue

class QueueLineError(Exception):
    pass


class QueueParser(argparse.ArgumentParser):
    """Parser for queue lines: raises instead of printing usage and exiting."""

    def error(self, message):
        raise QueueLineError(message)


def qlog(msg):
    print(f"[queue] {msg}", flush=True)


def queue_argv(command):
    """Split a queue line into vref arguments, dropping a leading 'python vref.py'."""
    lex = shlex.shlex(command, posix=True)
    lex.whitespace_split = True
    lex.escape = ""  # keep Windows backslashes as they are
    lex.commenters = ""
    try:
        tokens = list(lex)
    except ValueError as e:
        raise QueueLineError(str(e).lower())
    if tokens and re.fullmatch(r"(py|python[\d.]*)(\.exe)?", Path(tokens[0]).name, re.I):
        tokens = tokens[1:]
    if tokens and Path(tokens[0]).name.lower() == "vref.py":
        tokens = tokens[1:]
    return tokens


def is_local(url):
    return "://" not in url


def planned_slug(args):
    """Output folder name, when it can be known without downloading anything."""
    if args.name:
        return slugify(args.name)
    if is_local(args.url):
        return slugify(Path(args.url).stem)
    return None


def check_queue_item(command, have_whisper):
    """Return (argv, args, problem) for a queue line; problem is None if it looks runnable."""
    try:
        argv = queue_argv(command)
        args = build_parser(QueueParser).parse_args(argv)
    except QueueLineError as e:
        return None, None, str(e)
    if args.queue:
        return argv, args, "a queue line can't start another queue"
    if not args.url:
        return argv, args, "no video URL or file given"
    problem = check_args(args)
    if problem:
        return argv, args, problem
    if args.cookies_file and not Path(args.cookies_file).is_file():
        return argv, args, f"cookies file not found: {args.cookies_file}"
    if is_local(args.url):
        if not Path(args.url).is_file():
            return argv, args, f"video file not found: {args.url}"
        if args.require_transcript and args.no_transcribe:
            return argv, args, "--require-transcript can't succeed with --no-transcribe on a local file"
        if not have_whisper and not args.no_transcribe:
            return argv, args, ("faster-whisper isn't installed, so this file can't be transcribed "
                                "(pip install faster-whisper, or add --no-transcribe)")
    return argv, args, None


def read_queue(path):
    return path.read_text(encoding="utf-8-sig").splitlines()


def write_queue(path, lines):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for attempt in range(10):  # an editor can briefly lock the file on Windows
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.5)


def pending_commands(lines):
    return [(i, l.strip()) for i, l in enumerate(lines, 1)
            if l.strip() and not l.strip().startswith("#")]


def replace_command(path, command, replacement):
    """Swap the first line matching command for replacement lines.

    The file is re-read first so edits made while a video was processing survive.
    """
    lines = read_queue(path)
    for i, l in enumerate(lines):
        if l.strip() == command:
            end = i + 1
            if not replacement and end < len(lines) and not lines[end].strip():
                end += 1  # take the blank line separating it from the next command
            lines[i:end] = replacement
            write_queue(path, lines)
            return True
    return False


def mark_failed(path, command, reason):
    replace_command(path, command, [
        f"# FAILED {datetime.now():%Y-%m-%d %H:%M} - {reason}",
        f"# {command}",
    ])


def note_failure(message):
    """When running inside a queue, hand the failure reason back to the runner."""
    path = os.environ.get(QUEUE_REASON_ENV)
    if path:
        try:
            Path(path).write_text(message, encoding="utf-8")
        except OSError:
            pass


def one_line_reason(message):
    """Boil a (possibly multi-line) error message down to one line for the queue file."""
    raw = message.strip().splitlines() or ["unknown error"]
    head = raw[0].strip()
    if head.endswith(":"):
        # e.g. "yt-dlp failed:" followed by its output - the ERROR line is the useful bit
        block = []
        for l in raw[1:]:
            if not l.strip():
                break
            block.append(l.strip())
        errors = [l for l in block if "ERROR" in l]
        if errors or block:
            head = f"{head} {(errors or block)[-1]}"
    return " ".join(head.split())[:300]


def run_queue_item(argv, log_path):
    """Run one vref command, teeing its output to the console and log_path.

    Returns (returncode, reason); reason is None on success.
    """
    reason_file = log_path.with_suffix(".reason")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env[QUEUE_REASON_ENV] = str(reason_file)
    cmd = [sys.executable, "-u", str(ROOT / "vref.py"), *argv]
    last = ""
    with open(log_path, "w", encoding="utf-8") as logf:
        logf.write(f"$ {subprocess.list2cmdline(cmd)}\n\n")
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", env=env)
        try:
            for line in proc.stdout:
                sys.stdout.write(line)
                logf.write(line)
                last = line.strip() or last
            proc.wait()
        except KeyboardInterrupt:
            # Ctrl+C reaches the child too; give it a moment to exit on its own
            try:
                proc.wait(timeout=10)
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                proc.kill()
            raise
    if proc.returncode == 0:
        reason_file.unlink(missing_ok=True)
        return 0, None
    if reason_file.exists():
        reason = one_line_reason(reason_file.read_text(encoding="utf-8", errors="replace"))
        reason_file.unlink(missing_ok=True)
    else:
        reason = last or f"exited with code {proc.returncode}"
    return proc.returncode, reason


def run_queue(path):
    if not path.is_file():
        raise SystemExit(f"Queue file not found: {path}")
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool} not found on PATH.")
    have_whisper = importlib.util.find_spec("faster_whisper") is not None

    # check everything up front, while the user is still at the keyboard
    pending = pending_commands(read_queue(path))
    problems, slugs, url_needs_whisper = [], {}, False
    for n, command in pending:
        _, args, problem = check_queue_item(command, have_whisper)
        slug = planned_slug(args) if args and not problem else None
        if slug and slug in slugs:
            problem = (f"writes to library/{slug}, same as line {slugs[slug]} "
                       "- give one of them a different --name")
        elif slug:
            slugs[slug] = n
        if problem:
            problems.append((n, command, problem))
        elif not is_local(args.url) and not args.no_transcribe:
            url_needs_whisper = True

    qlog(f"{len(pending)} command(s) in {path}")
    if url_needs_whisper and not have_whisper:
        qlog("note: faster-whisper isn't installed - online videos without platform "
             "captions will get no transcript (or fail, with --require-transcript)")
    if problems:
        print(f"\n{len(problems)} problem(s) found:\n")
        for n, command, problem in problems:
            print(f"  line {n}: {problem}\n    {command}\n")
        try:
            answer = input(f"Comment out these {len(problems)} line(s) and run the rest? [y/N] ")
        except EOFError:
            answer = ""
        if answer.strip().lower() not in ("y", "yes"):
            raise SystemExit("Queue not started - nothing was changed.")
        for _, command, problem in problems:
            mark_failed(path, command, problem)

    QUEUE_LOGS.mkdir(parents=True, exist_ok=True)
    done = failed = 0
    stopped = False
    while True:
        pending = pending_commands(read_queue(path))
        if not pending:
            break
        n, command = pending[0]
        print()
        qlog(f"[{done + failed + 1}] {command}")

        # lines added while the queue was running haven't been checked yet
        argv, args, problem = check_queue_item(command, have_whisper)
        if problem:
            qlog(f"FAILED: {problem}")
            mark_failed(path, command, problem)
            failed += 1
            continue

        log_path = QUEUE_LOGS / f"{datetime.now():%Y%m%d-%H%M%S}-{planned_slug(args) or 'download'}.log"
        try:
            code, reason = run_queue_item(argv, log_path)
        except KeyboardInterrupt:
            code, reason = 130, None
        if code in (130, 0xC000013A):  # Ctrl+C (the second is Windows' STATUS_CONTROL_C_EXIT)
            print()
            qlog("stopped - this command is still in the queue:")
            print(f"  {command}")
            stopped = True
            break
        if code == 0:
            replace_command(path, command, [])
            done += 1
        else:
            qlog(f"FAILED: {reason}")
            qlog(f"full output: {log_path}")
            mark_failed(path, command, reason)
            failed += 1

    left = len(pending_commands(read_queue(path)))
    print()
    qlog(f"finished: {done} done, {failed} failed"
         f"{f' (commented out in {path.name})' if failed else ''}, {left} left")
    if stopped:
        sys.exit(130)


# ---------------------------------------------------------------- main

def check_args(args):
    """Problems argparse can't catch on its own; returns a message or None."""
    if args.language:
        try:
            from faster_whisper.tokenizer import _LANGUAGE_CODES
        except ImportError:
            _LANGUAGE_CODES = None  # can't validate & whisper won't run anyway
        if _LANGUAGE_CODES and args.language not in _LANGUAGE_CODES:
            return f"unknown --language {args.language!r}; see README.md for language codes"
    return None


def build_parser(parser_class=argparse.ArgumentParser):
    ap = parser_class(description="Build a Claude-readable reference from a video URL.")
    ap.add_argument("url", nargs="?", help="video URL, or a path to a local video file")
    ap.add_argument("--name", help="folder slug (default: from video title)")
    ap.add_argument("--frames", type=int, default=36, help="max keyframes (default 36)")
    ap.add_argument("--model", default="base",
                    help="faster-whisper model when captions are unavailable "
                         "(tiny/base/small/medium, default base)")
    ap.add_argument("--cookies", help="browser to pull cookies from, e.g. chrome "
                                      "(often blocked on Windows - prefer --cookies-file)")
    ap.add_argument("--cookies-file", help="path to an exported cookies.txt "
                                           "(auto-detected from video-ref/cookies/)")
    ap.add_argument("--quality", type=int, default=720, help="max video height (default 720)")
    ap.add_argument("--keep-video", action="store_true", help="keep source.mp4")
    ap.add_argument("--no-transcribe", action="store_true", help="skip whisper fallback")
    ap.add_argument("--language", type=str.lower, default=None,
                    help = "language the video is spoken in: only captions in this language are used, and "
                           "faster-whisper transcribes in it if there are none; see README.md for language codes "
                           "(default: english captions, else automatically detect the language)")
    ap.add_argument("--require-transcript", action="store_true",
                    help="fail instead of carrying on when no transcript can be produced")
    ap.add_argument("--queue", metavar="FILE",
                    help="run each vref command in FILE in turn, removing each one once it "
                         "succeeds and commenting out any that fail, with the reason")
    return ap


def main():
    ap = build_parser()
    args = ap.parse_args()

    if args.queue:
        if args.url:
            ap.error("give either a video or --queue, not both")
        return run_queue(Path(args.queue))
    if not args.url:
        ap.error("a video URL or file is required (or --queue FILE)")
    problem = check_args(args)
    if problem:
        ap.error(problem)

    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool} not found on PATH.")

    tmp = LIBRARY / "_work"
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)

    local = Path(args.url)
    if local.is_file():
        tmp.mkdir(parents=True, exist_ok=True)
        video = tmp / f"source{local.suffix}"
        shutil.copy2(local, video)
        log(f"using local file: {local.name}")
        meta = {"url": str(local), "title": local.stem, "uploader": "",
                "upload_date": "", "duration": 0, "view_count": None,
                "like_count": None, "extractor": "local file",
                "webpage_url": str(local), "description": "",
                "width": None, "height": None, "fps": None}
    else:
        cookie_file = find_cookie_file(args.url, args.cookies_file)
        video = download(args.url, tmp, cookies=args.cookies,
                         cookie_file=cookie_file, quality=args.quality,
                         language=args.language)
        meta = load_meta(tmp, args.url)
    duration = meta.get("duration") or probe_duration(video)
    meta["duration"] = duration
    log(f"'{meta['title']}' - {ts(duration)}")

    segs, source = subs_from_download(tmp, args.language)
    if segs:
        log(f"using {source} ({len(segs)} segments)")
    elif args.language:
        log(f"no '{args.language}' captions on the platform")
    if not segs and not args.no_transcribe:
        segs, source = whisper_transcribe(video, tmp, args.model, args.language)
    if not segs:
        if args.require_transcript:
            # checked before the output folder is touched, so an earlier result survives
            if args.no_transcribe:
                why = "--no-transcribe was set"
            elif importlib.util.find_spec("faster_whisper") is None:
                why = "faster-whisper isn't installed"
            else:
                why = "faster-whisper produced nothing (audio extraction failed or no speech)"
            raise SystemExit(f"No transcript could be produced: no usable platform captions "
                             f"and {why} (--require-transcript)")
        segs, source = [], None

    slug = slugify(args.name or meta["title"])
    outdir = LIBRARY / slug
    if outdir.exists():
        shutil.rmtree(outdir, ignore_errors=True)
    outdir.mkdir(parents=True, exist_ok=True)

    stamps = pick_timestamps(video, duration, args.frames)
    frames = extract_frames(video, stamps, outdir / "frames")
    sheets = build_sheets(frames, outdir / "sheets") if frames else []

    words = write_transcript(segs, source or "n/a", outdir)
    (outdir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False),
                                      encoding="utf-8")
    write_reference(outdir, meta, segs, source, frames, sheets, words, duration)

    if args.keep_video:
        shutil.move(str(video), str(outdir / f"video{video.suffix}"))
    shutil.rmtree(tmp, ignore_errors=True)

    log("done ->")
    print(f"\n  {(outdir / 'REFERENCE.md')}\n")
    print(f"  {len(frames)} keyframes | {len(sheets)} contact sheets | {words} transcript words")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except SystemExit as e:
        if isinstance(e.code, str):
            note_failure(e.code)
        raise
    except Exception as e:
        note_failure(f"{type(e).__name__}: {e}")
        raise
