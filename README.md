# msr — multi-subject reference → video (LTX 2.3)

Turn a few reference images into a consistent multi-subject video — **no LoRA training**.
Built on LiconStudio's LTX 2.3 Multiple-Subject-Reference workflow, wrapped as one command
you drive from the shell (or an agent drives for you).

Good for: music videos, character pieces, and the "behind-the-scenes of a live-action
adaptation" format (a real-looking actor as an anime/game character on a film set).

```bash
python3 scripts/msr.py \
  --subject1 character_sheet.png --subject2 prop.png --background scene.png \
  --global "CHARACTER (image 1) holding PROP (image 2) in SCENE..." \
  --segments "beat one | beat two | beat three" \
  --audio track.wav --ambient --quality cinematic --duration 10 --out clip.mp4
```

## How it works
References become *conditioning*, not pixels — the model generates a fresh video that keeps
your subjects' identities. You provide:
- **subject reference(s)** — ideally **multi-view turnaround sheets** (front/back/side + face),
  so identity survives motion;
- **a background** — whose orientation also sets the output aspect (portrait → vertical 9:16);
- **a global prompt** (name the refs "image 1"/"image 2") + **segment prompts** (timed beats);
- **a driving audio track** — because the model is audio-visual, **the audio drives the motion**.

## Setup
Needs a running ComfyUI with the MSR custom nodes + LoRAs and an LTX-2.3-22b checkpoint — see
[`references/install.md`](references/install.md). Point the skill at it with `COMFY_URL`
(default `http://127.0.0.1:8188`). Reference-image generation is done with separate image tools
(ChatGPT-class for known characters, Ideogram-class for originals).

## Docs
- [`SKILL.md`](SKILL.md) — agent/Claude Code reference + the craft rules.
- [`HANDOFF.md`](HANDOFF.md) — contract + findings/gotchas for any agent.
- [`references/install.md`](references/install.md) — one-time ComfyUI setup.
- [`references/craft.md`](references/craft.md) — prompt patterns that work.

## Notes
- **Action ceiling is medium** — choreograph walking/turning/posing, not fighting/sports.
- **Audio modes:** let a music beat drive (music video) or use `--ambient` for grounded
  cinematic/BTS motion with the real track post-muxed on top.
- Render time scales with clip length; iterate at `draft`/`fast`, finalize at `cinematic`.

LTX 2.3 weights and the underlying models carry their own licenses; check them for commercial use.
