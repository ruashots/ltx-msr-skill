---
name: msr
description: Generate consistent multi-subject videos from reference images with LTX 2.3 MSR (Multiple-Subject-Reference) — NO LoRA training. Use to put 1-3 referenced characters/objects into a scene that moves: music videos, character pieces, "behind-the-scenes of a live-action adaptation" shots. You supply reference turnaround sheets + a global/segment prompt + a driving audio track; the model keeps the identities and animates them. Needs ComfyUI running with the MSR nodes/LoRAs installed (see references/install.md).
---

# msr — multi-subject reference → video (LTX 2.3)

Reference images become *conditioning*, not pixels: the model generates a fresh video
that keeps your subjects' identities. One command:

```bash
python3 ~/.claude/skills/msr/scripts/msr.py \
  --subject1 char_sheet.png --subject2 prop.png --background scene.png \
  --global "CHARACTER (image 1) ... a PROP (image 2) ... in SCENE..." \
  --segments "beat one | beat two | beat three | beat four" \
  --audio track.wav --quality fast --duration 10 --out clip.mp4
```

## The loop
1. **Make the references** (the make-or-break step — see craft below). 1 required subject
   + optional 2nd subject/object + a background. The **background's orientation sets the
   output aspect** (portrait bg → vertical 9:16).
2. **Write the direction.** `--global` describes the refs (call them *"image 1"/"image 2"*)
   and the scene. `--segments` are `|`-separated action beats spread across the clip.
3. **Pick the audio + mode** (see "audio drives motion" — this is the non-obvious one).
4. **Render** at a `--quality` tier; **watch it** (use the `watch-video` skill — ComfyUI's
   mp4 preview decode is flaky; sample frames yourself) and iterate.

## Craft rules (these decide whether it works)
- **References = multi-view TURNAROUND SHEETS** (front / back / 3-4 / side + face close-ups
  on one image), not single shots. The sheet gives the model the subject's full identity so
  it survives turning and moving. A single front photo falls apart the moment they rotate.
- **Recognizable IP characters → generate the sheet with the `chatgpt-images` skill** (it
  *knows* the character). **Original characters → `ideogram4`** (you describe them). Don't
  reconstruct a known character by description — it comes out wrong/"cursed".
- **AUDIO DRIVES THE MOTION.** LTX 2.3 is audio-visual (joint latent). **Silent input →
  frozen subjects.** A **music beat → the subject dances** (reads music-video). Two modes:
  - *Music video:* pass the track, let the beat drive — omit `--ambient`.
  - *Cinematic / behind-the-scenes (no dancing):* pass `--ambient` — the script flattens the
    track into a low atmospheric bed (grounded motion), then **post-muxes the real track**
    over the finished video.
- **Action ceiling = MEDIUM.** Walking, turning, posing, gesturing, drawing a weapon, a punch
  — good. Fast sports/fighting/spins → smears. (NOTE: aerial/ungrounded motion does NOT cause the
  subject-duplication artifact — that was a falsified theory; an explicit "mid-air spin" rendered
  clean. The duplication/elongation is a REFERENCE-ASPECT problem — see the quality-ladder section.)
- **To kill the "acting at the camera" look, ORIENT the subject away** (profile / 3-4 /
  back) in the prompt text. "Don't look at the camera" alone *loses* to MSR's front-facing
  bias. (Fully back-turned in an empty set reads aimless — give a self-contained action like
  being on a phone, or put crew/another subject in frame.)
- **Match the segment energy to the audio.** Measure it (`ffmpeg -af volumedetect`) instead
  of assuming "intro = calm". Don't default to low-energy.

## Quality ladder (`--quality`)
`draft` 512/5-step (~9s, rough preview) · `fast` 768 · `standard` 1280 · `clean` 1536 ·
`fluid` 1920 · `max` 2048 · `cinematic` 1920. **Render time scales with CLIP LENGTH.**

All tiers work at full res — **resolution is NOT the cause of the elongation/duplication** (that was
a wrong theory; same-res renders went both clean and broken). The real cause is reference aspect ↓.

**⚠ THE BIG ONE — reference aspect must match the OUTPUT aspect.** The `LiconMSR` node anamorphically
resizes EVERY reference to the render canvas W×H (pure `cv2.resize`, no aspect preserve, no crop —
confirmed in its source). So a **wide horizontal turnaround sheet feeding a tall 9:16 video** breaks
the subject:
- if the wide sheet is stretched to the tall canvas → subject **ELONGATES** (tall & thin);
- if you pre-letterbox the wide sheet → it shrinks to a strip and the model **DUPLICATES** it (stacked figures).
Higher res just amplifies the elongation; it is not the root cause.
**Fix (confirmed 2026-06):** author references in the OUTPUT aspect — a **single portrait view** or a
**vertically-stacked** multi-view, NOT a 5-across horizontal sheet. `msr.py` now auto-fits every ref
(letterbox) to the exact canvas so it can't stretch, and warns if a ref's aspect is far from the
canvas — but the auto-fit can't rescue a wide sheet (it'll duplicate), so make the ref portrait. A
genuine 2nd *distinct* subject also renders clean at high res. This works at any tier, full res.

> **LEGACY (2026-06-17):** the ORIGINAL skill + workflow (git `51275b7`, untouched `assets/msr_base.json`)
> produced the known-good *2-distinct-subject* render `c4614dbe`. The 2026-06-17 changes (dynamic
> subject count, letterbox ref-fit, hard wide-ref warning, container normalize) target the
> *single-subject + wide-sheet* failures. If the new behavior looks off, `git show 51275b7:scripts/msr.py`
> is the original driver, or pass two distinct portrait refs + `--raw-aspect` to mimic the original path.

**Separately, the playback "stretch":** a correct render can still *look* stretched if the mp4 has
unset SAR + an odd width. `msr.py` auto-normalizes output to a standard container (1080×1920, SAR 1:1),
which fixes that. Independent of the reference-aspect issue above.

## Things that bite
- **35-millisecond "success" with no video** → an output node failed validation and ComfyUI
  **silently ignored it**, running only a trivial node. Check `ComfyUI/user/comfyui.log`. The
  classic cause is a model path that doesn't resolve (e.g. a `ltx2\` subfolder prefix that
  isn't there). The text-projection path is bare (no prefix) in the template.
- **Cinematic can come out *darker*, not brighter** — it can muddy a dark set. Light the
  subject in the background ref (a key-lit center spot) or lift exposure in post.
- ComfyUI's built-in mp4 preview decodes to black collages — don't judge from it; use `watch-video`.
- **`watch-video`'s collage itself goes BLACK on LTX mp4s.** Workaround: pull frames directly
  with `ffmpeg -ss <t> -i clip.mp4 -frames:v 1 f.png` and `hstack` them into a strip to inspect.
- **"It looks vertically stretched" is almost always the container, not the render.** Verify before
  theorizing: push a plain circle through the SAME tier — it comes back round (≈1.0 w/h). The real
  cause is unset SAR + an odd width confusing the player. `msr.py` now auto-normalizes the output to
  a standard container with **SAR 1:1** (1080×1920 for 9:16); that's the fix. Don't chase it in the
  render. (Root-caused 2026-06: tier aspect + container, NOT a generation bug.)
- **Delivery = standard container.** Output is auto-scaled to 1080×1920 (9:16) / 1920×1080 / 1080×1080
  with SAR 1:1 so it plays correctly everywhere. Pass `--raw-aspect` only if you need native render dims.

See `references/install.md` for the one-time ComfyUI setup, `references/craft.md` for the
full prompt patterns, and `HANDOFF.md` for the agent contract.
