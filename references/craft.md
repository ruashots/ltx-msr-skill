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
`draft`/`fast` to find the take, `cinematic` for the keeper. Always **watch with the `watch-video`
skill** (not ComfyUI's preview). Change ONE variable at a time.
