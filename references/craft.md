# MSR craft — prompt patterns that work

## Global prompt
Describe the refs and the scene; **name the references as "image 1" / "image 2"** (subject1 /
subject2 inputs). State setting, lighting, grade. One paragraph.

> A young Latina singer (image 1) with a magenta-streaked ponytail and a male dancer (image 2)
> in a teal jacket perform on a neon stadium stage. Magenta/teal spotlights, haze, glowing crowd.

The **background ref** sets the scene AND the output aspect ratio (portrait ref → vertical 9:16).

## Segment prompts (`--segments`, `|`-separated)
Each `|` segment is a beat in time (routed by PromptRelay). 3-5 beats over a 10s clip. This is
your shot list inside the clip — pace it to the audio's energy.

> she struts to the front gripping the mic | she belts with one arm raised, the dancer breaks
> into a move | both hit a synchronized pose | the camera pushes in as she spins

Keep each beat **medium action** (LTX ceiling). To stop an "acting-at-camera" look, write the
**orientation** explicitly ("turned three-quarters toward the crew", "looking down at her phone")
— a stated body angle beats a stated gaze instruction.

## Audio = the motion engine
| Want | Do |
|---|---|
| Music video, subject moves to the beat | pass the track, omit `--ambient` |
| Cinematic / BTS, grounded natural motion | `--ambient` (flat bed drives motion, real track post-muxed) |
| Subtle "between takes" candid | `--ambient` + a self-contained action (phone/looking off) |
| Anything | NEVER silent (silent = frozen). Match segment energy to the track (`ffmpeg -af volumedetect`). |

## Concept fit (play to MSR's strengths)
- **Music video / performance** — let audio drive; bold energy; multi-view sheets for each cast member.
- **Behind-the-scenes of a live-action anime/film adaptation** — a popular, view-drawing format
  that suits the MEDIUM-action ceiling (actors between takes). IP character (ChatGPT sheet) +
  a film-set background (camera rig in foreground) + `--ambient`. For true candid, orient the
  actor away and give them a self-contained action; an empty set + a centered subject reads staged.
- **Single character + recurring object** — subject1 = character sheet, subject2 = a motif object
  (it ties multi-scene sequences together). Note: MSR holds an object's identity but not its
  physics — don't choreograph it doing four different things; keep one consistent handling.

## Iterating
`draft`/`fast` to find the take, a high tier (`clean`/`fluid`/`cinematic`) for the keeper.
**Seed-hunt** — budget 2-3 seeds per keeper; a lot of takes are duds, that's normal. Seed-hunt
at **`draft`** (it's exact 9:16 AND fast), then render the winning seed at the keeper tier.
Always **watch with the `watch-video` skill** (see the frame-extraction note below — its collage
goes black on LTX mp4s). Change ONE variable at a time.

---

## Directing (research-baked) — the cure for generic "calm character does a calm thing"
The word "cinematic" does nothing. Cinematic = **vocabulary + intention**. Build each beat from:
- **One camera move** (lead the global with it): slow push-in, dolly, handheld follow, orbit, low-angle reveal. One per clip.
- **Motivated light** (the #1 amateur tell is flat frontal light): name a *source + direction + quality* ("warm amber lantern from camera-left, magenta neon rim"). Light the subject in the **background ref** (a key-lit spot) so dark scenes don't muddy.
- **A 3-5 colour palette** named in the global ("teal, magenta, amber, wet black") — cheapest "graded film" upgrade.
- **Counted-beat action** in `--segments` — this is the fix for the held-pose default. Write a tiny **beginning → middle → end micro-arc** across the clip (e.g. "stands, breathing | jaw sets, gaze lifts | turns to lens, exhales"). Forces motion instead of a frozen mood shot.
- **Orientation**: profile / three-quarter beats front-on for naturalism (see front-bias note).
- **Subject elongation/duplication = REFERENCE ASPECT, not resolution or motion.** If the subject
  comes out stretched tall or stacked/duplicated, your reference's aspect doesn't match the output.
  The MSR node anamorphically resizes refs to the canvas, so a WIDE turnaround sheet → TALL 9:16
  video tears the subject. **Author references in the output aspect** — a single portrait view or a
  vertically-stacked multi-view, never a 5-across horizontal sheet. (Resolution and aerial motion
  were both tested and ruled out; see SKILL.md.)

## Scroll-stopper rules (if it's for socials, not just a demo)
A gorgeous moving portrait is a **tool demo**, not **content**. To earn the tap:
- **Hook the first ~0.5-1.5s** — open on the close face mid-action or the impossible beat, NOT a slow reveal of someone standing. ~80% watch muted → the hook must read as **visual + (optional) text** with no sound.
- **Lean INTO the AI/impossible aesthetic** — "beautiful impossibility" out-shares fake-realism ~5:1. A face raises early retention.
- **Give it a payoff / a moment** — something must *happen* and resolve (a reveal, a flare, a turn). No event = nothing to stay for.
- **End on a loop** where you can. Keep cuts/motion **medium** (LTX ceiling).
- The **"behind-the-scenes of a live-action adaptation"** format is the flagship: it wins on nostalgia + the mundane-set-vs-iconic-moment juxtaposition, and *showing the crew/green-screen increases shares*. It also suits the MEDIUM-action ceiling.

## Asset notes (chatgpt-images / ideogram4)
- `chatgpt-images` (gpt-image-2) **ignores the requested size** and returns its own dims — but the **content proportions are correct** (a control circle comes back round). So don't trust the reported size; the pixels are fine and MSR resizes inputs cleanly regardless of their aspect.
- IP characters → `chatgpt-images` (it knows them); original characters → `ideogram4` (you describe them). Multi-view turnaround sheets, not single shots.
