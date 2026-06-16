# MSR — agent handoff

Written for any capable agent (not the operator). MSR = LTX 2.3 Multiple-Subject-Reference:
reference images → consistent multi-subject video, no LoRA training. Tool-name examples use
Claude Code (`Bash`/`Read`); map to your runtime.

## Contract
1. **Verify the backend.** ComfyUI must be reachable (`COMFY_URL`, default `http://127.0.0.1:8188`)
   with the MSR nodes/LoRAs installed (`references/install.md`). `GET /system_stats` to check.
2. **Get the references first** — this is the make-or-break step, not the render:
   - 1 required subject + optional 2nd subject/object + 1 background.
   - Subjects MUST be **multi-view turnaround sheets** (front/back/3-4 + face), or identity
     breaks the moment they move. Recognizable **IP character → ChatGPT image gen** (it knows
     them); **original → a local t2i** (Ideogram-class). Don't reconstruct a known character
     from your own description — it comes out wrong.
   - The **background's orientation sets the output aspect** (portrait → vertical 9:16).
3. **Direct it.** `--global` names the refs as *"image 1"/"image 2"* + the scene; `--segments`
   are `|`-separated medium-action beats.
4. **Choose the audio mode** (the non-obvious axis — see Findings).
5. **Render** at a `--quality` tier, then **watch the output frame-by-frame** (sample frames;
   do NOT trust ComfyUI's mp4 preview — it decodes black). Iterate one variable at a time.

```bash
python3 scripts/msr.py --subject1 sheet.png --background scene.png \
  --global "..." --segments "a | b | c" --audio t.wav --ambient --quality cinematic --out o.mp4
```

## Findings & gotchas (the expensive lessons)
- **Audio drives the motion.** LTX 2.3 is audio-visual. Silent → frozen subjects. A music
  **beat → the subject dances** (music-video look). For cinematic/BTS, use `--ambient`: it
  flattens the track into an atmospheric bed (grounded motion) and post-muxes the real track
  onto the finished video. Match segment energy to the track; measure it, don't assume.
- **Action ceiling = MEDIUM.** High action (sports/fighting/spins) smears even at cinematic.
- **"Don't look at the camera" loses to the front-facing bias.** Physically orient the subject
  away in the prompt (profile/3-4/back). Fully back-turned on an empty set looks aimless — give
  a self-contained action (phone) or another subject/crew to react to.
- **35 ms "success" with no video = silently-ignored output validation.** A bad model path in
  an output's chain makes ComfyUI ignore that output and run only a trivial node — the API still
  returns success. Read `ComfyUI/user/comfyui.log`. (The template ships the known path fixes;
  the worst offender is a `ltx2\` subfolder prefix on a model that lives at the folder root.)
- **Cinematic can render *darker*, not sharper-and-brighter** — it can muddy a dark set. Key-light
  the subject in the background ref, or lift exposure in post.
- **Object physics aren't preserved** — MSR keeps an object's *identity* but will pop its
  position around if you over-choreograph it. One consistent handling per shot.

## Quality / cost
`draft` 512/5-step (~9 s) → `cinematic` 1920/13-step. **Render time scales with clip length**:
cinematic at 10 s ≈ 15 min. Iterate cheap, finalize once.
