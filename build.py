#!/usr/bin/env python3
"""Build one episode of The AIP Morning Brief and regenerate the podcast site.

Usage: python build.py scripts/2026-11-23.json

Script JSON format (written each morning by the Claude scheduled task):
{
  "date": "2026-11-23",
  "title": "AIP Morning Brief — 23 Nov — <hook>",
  "show_notes": "Markdown show notes with source links",
  "dialogue": [{"speaker": "ANCHOR", "text": "..."}, {"speaker": "STRATEGIST", "text": "..."}]
}

The live GitHub Pages site is the store: each run downloads the current
episodes.json and recent MP3s from it, adds the new episode, and rebuilds
site/ (feed.xml, episodes/, cover.jpg) for deployment. No audio is ever
committed to git, so the repo stays tiny.
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

import wave

import numpy as np

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
SAMPLE_RATE = 24000
PAUSE_SECONDS = 0.35


def load_config():
    cfg = json.loads((ROOT / "config.json").read_text())
    cfg["site_url"] = cfg["site_url"].rstrip("/")
    return cfg


def fetch(url):
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return r.read()
    except (urllib.error.HTTPError, urllib.error.URLError):
        return None


# ---------- audio ----------

def synthesize(dialogue, cfg):
    """Return a mono float32 numpy array of the whole episode."""
    pause = np.zeros(int(SAMPLE_RATE * PAUSE_SECONDS), dtype=np.float32)
    chunks = []

    if os.environ.get("FAKE_TTS"):  # local testing without Kokoro
        for turn in dialogue:
            secs = max(1.0, len(turn["text"].split()) / 2.6)
            t = np.linspace(0, secs, int(SAMPLE_RATE * secs), endpoint=False)
            freq = 220 if turn["speaker"] == "ANCHOR" else 330
            chunks += [(0.1 * np.sin(2 * np.pi * freq * t)).astype(np.float32), pause]
        return np.concatenate(chunks)

    from kokoro import KPipeline

    pipeline = KPipeline(lang_code=cfg.get("lang_code", "b"))
    voices = cfg["voices"]
    for turn in dialogue:
        voice = voices.get(turn["speaker"].upper(), list(voices.values())[0])
        text = re.sub(r"\[[^\]]*\]", "", turn["text"]).strip()  # drop [audio tags]
        if not text:
            continue
        for _, _, audio in pipeline(text, voice=voice, speed=cfg.get("speed", 1.0)):
            if audio is None:
                continue
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            chunks.append(np.asarray(audio, dtype=np.float32))
        chunks.append(pause)
    return np.concatenate(chunks)


def to_mp3(samples, mp3_path):
    wav_path = mp3_path.with_suffix(".wav")
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav_path),
         "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
         "-ac", "1", "-ar", "44100", "-b:a", "64k", str(mp3_path)],
        check=True,
    )
    wav_path.unlink()


# ---------- feed ----------

def md_to_html(md):
    out = html.escape(md)
    out = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"^#+\s*(.+)$", r"<strong>\1</strong>", out, flags=re.M)
    return out.replace("\n", "<br/>\n")


def fmt_duration(seconds):
    seconds = int(round(seconds))
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def build_feed(cfg, episodes):
    e = html.escape
    base = cfg["site_url"]
    items = []
    for ep in episodes:
        url = f"{base}/episodes/{ep['file']}"
        items.append(f"""    <item>
      <title>{e(ep['title'])}</title>
      <description><![CDATA[{md_to_html(ep['show_notes'])}]]></description>
      <enclosure url="{e(url)}" length="{ep['bytes']}" type="audio/mpeg"/>
      <guid isPermaLink="false">{e(ep['guid'])}</guid>
      <pubDate>{ep['pub_date']}</pubDate>
      <itunes:duration>{ep['duration']}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
      <itunes:episodeType>full</itunes:episodeType>
    </item>""")
    now = format_datetime(datetime.now(timezone.utc))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{e(cfg['title'])}</title>
    <link>{e(base)}/</link>
    <atom:link href="{e(base)}/feed.xml" rel="self" type="application/rss+xml"/>
    <description>{e(cfg['description'])}</description>
    <language>{e(cfg.get('language', 'en-gb'))}</language>
    <lastBuildDate>{now}</lastBuildDate>
    <itunes:author>{e(cfg['author'])}</itunes:author>
    <itunes:owner>
      <itunes:name>{e(cfg['author'])}</itunes:name>
      <itunes:email>{e(cfg['owner_email'])}</itunes:email>
    </itunes:owner>
    <itunes:image href="{e(base)}/cover.jpg"/>
    <itunes:category text="Business"><itunes:category text="Investing"/></itunes:category>
    <itunes:explicit>false</itunes:explicit>
    <itunes:type>episodic</itunes:type>
{chr(10).join(items)}
  </channel>
</rss>
"""


# ---------- main ----------

def main():
    script_path = Path(sys.argv[1])
    script = json.loads(script_path.read_text())
    cfg = load_config()
    date = script.get("date") or script_path.stem
    keep = int(cfg.get("keep_episodes", 30))

    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "episodes").mkdir(parents=True)
    shutil.copy(ROOT / "cover.jpg", SITE / "cover.jpg")

    # Previous episodes from the live site (empty on the very first run).
    raw = fetch(f"{cfg['site_url']}/episodes.json")
    episodes = json.loads(raw) if raw else []
    episodes = [ep for ep in episodes if ep["date"] != date]  # allow same-day re-runs

    # New episode.
    print(f"Synthesizing {len(script['dialogue'])} turns for {date}...", flush=True)
    samples = synthesize(script["dialogue"], cfg)
    filename = f"{date}.mp3"
    mp3 = SITE / "episodes" / filename
    to_mp3(samples, mp3)
    episodes.insert(0, {
        "date": date,
        "title": script["title"],
        "show_notes": script.get("show_notes", ""),
        "file": filename,
        "bytes": mp3.stat().st_size,
        "duration": fmt_duration(len(samples) / SAMPLE_RATE),
        "guid": f"aip-morning-brief-{date}",
        "pub_date": format_datetime(datetime.now(timezone.utc)),
    })
    episodes.sort(key=lambda ep: ep["date"], reverse=True)
    episodes = episodes[:keep]

    # Re-download kept older MP3s so the new site still contains them.
    for ep in episodes[1:]:
        data = fetch(f"{cfg['site_url']}/episodes/{ep['file']}")
        if data:
            (SITE / "episodes" / ep["file"]).write_bytes(data)
        else:
            print(f"warning: could not fetch {ep['file']}; dropping it", flush=True)
    episodes = [ep for ep in episodes if (SITE / "episodes" / ep["file"]).exists()]

    (SITE / "episodes.json").write_text(json.dumps(episodes, indent=2))
    (SITE / "feed.xml").write_text(build_feed(cfg, episodes))
    (SITE / "index.html").write_text(
        f'<!doctype html><meta charset="utf-8"><title>{html.escape(cfg["title"])}</title>'
        f'<h1>{html.escape(cfg["title"])}</h1><p>{html.escape(cfg["description"])}</p>'
        f'<p><a href="feed.xml">RSS feed</a></p>'
    )
    print(f"Done: {filename} ({episodes[0]['duration']}), {len(episodes)} episodes in feed.")


if __name__ == "__main__":
    main()
