# The AIP Morning Brief

Free, fully automated daily podcast.

1. A Claude scheduled task researches the news each morning and commits `scripts/YYYY-MM-DD.json` (two-host dialogue + show notes).
2. That push triggers `.github/workflows/publish.yml`, which voices the script with Kokoro (free, open-source TTS), builds an MP3 and RSS feed, and deploys them to GitHub Pages.
3. Spotify reads `https://<username>.github.io/aip-morning-brief/feed.xml` and lists each new episode automatically.

The last 30 episodes are kept; older ones drop off. No audio is stored in git.

## Settings
Edit `config.json`: `owner_email` (Spotify sends its verification code here), `site_url`, voices (`bf_emma`, `bf_isabella`, `bm_george`, `bm_lewis` are British options), `speed`, `keep_episodes`.

## Manual run
Actions → Publish episode → Run workflow (optionally name a script file).

Public news only — this repo and feed are public.
