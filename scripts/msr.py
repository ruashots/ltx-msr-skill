#!/usr/bin/env python3
"""
msr.py — drive LTX 2.3 Multiple-Subject-Reference (MSR) video generation via ComfyUI.

Turn 1-3 reference images (subjects + background) + prompts + a driving audio track
into a consistent multi-subject video — no LoRA training. Wraps LiconStudio's MSR
workflow; the agent supplies references and direction.

Usage:
  msr.py --subject1 power_sheet.png --background csm_set.png \
         --global "Power (image 1) on a neon film set..." \
         --segments "she scrolls her phone | she glances at the crew | she shifts, bored" \
         --audio track.wav --ambient --quality cinematic --duration 10 --out out.mp4

Reference images: each subject ref MUST be a PORTRAIT subject that FILLS a ~9:16 frame — a single
portrait view, or multi-view stacked VERTICALLY. A WIDE horizontal turnaround sheet (views in a row)
breaks portrait output: the node anamorphically resizes refs to the canvas, so a wide sheet either
stretches the subject (tall/thin) or, once letterboxed, becomes a thin strip the model DUPLICATES
(stacked bodies). Recognizable IP -> `chatgpt-images`; original characters -> `ideogram4`.

LEGACY NOTE (2026-06-17): the ORIGINAL skill + workflow (git tag/commit 51275b7 "Plain reproducible
output", + the untouched assets/msr_base.json) is what produced the known-good 2-distinct-subject
render `c4614dbe-...`. The 2026-06-17 changes here — dynamic subject count (only wire slots actually
used), letterbox ref-fit to the exact canvas, hard wide-ref warning, and output container normalize
(--raw-aspect to skip) — fix the SINGLE-subject + wide-sheet elongation/duplication failures. If the
new behavior ever looks off, `git show 51275b7:scripts/msr.py` is the original driver; or just pass
two DISTINCT portrait refs and --raw-aspect to mimic the original clean path. The node graph itself
(assets/msr_base.json) was never modified.
"""
import argparse, json, os, subprocess, sys, tempfile, time
import urllib.request, urllib.error, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "assets", "msr_base.json")

# --- node ids in the bundled template (validated; see assets/msr_base.json) ---
N_SUBJ1, N_SUBJ2, N_BG = "80", "81", "85"
N_LICON = "28"; N_SUBJ2_RESIZE = "83"  # LiconMSR node + the subject-2 resize feeding its input "2"
N_GLOBAL, N_SEGMENTS = "5899", "5900"
N_AUDIO = "109"; N_RES = "101"; N_SIGMAS = "27"; N_DISTILL = "123"
N_DURATION = "112"; N_FPS = "113"; N_OUT = "89"

# --- quality ladder: (resize_longer_edge, sigmas, distill_strength) ---
# render time scales with CLIP LENGTH; times below are ~10s clips, model warm.
QUALITY = {
    "draft":     (512,  "1.0, 0.975, 0.909375, 0.725, 0.421875, 0.0", 0.5),               # ~9s  rough preview
    "fast":      (768,  "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0", 0.5),  # ~80s
    "standard":  (1280, "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0", 0.5),  # ~180s
    "clean":     (1536, "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0", 0.5),
    "fluid":     (1920, "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0", 0.5),
    "max":       (2048, "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0", 0.5),  # exact 9:16 (1152x2048), higher than clean
    "cinematic": (1920, "1.0, 0.992, 0.984, 0.975, 0.95, 0.91, 0.85, 0.76, 0.66, 0.54, 0.41, 0.28, 0.14, 0.0", 0.35),  # ~15min@10s
}
# NOTE: all tiers render at full res fine. Subject ELONGATION/DUPLICATION is NOT a resolution or tier
# problem (that was a wrong theory — same-res renders went both clean and broken). The real cause is
# REFERENCE ASPECT: LiconMSR anamorphically resizes each ref to the canvas, so a wide turnaround sheet
# into a tall 9:16 video tears the subject. fit_letterbox() (in staging) pre-fits refs to the canvas to
# stop the stretch, and _warn_wide_ref() flags wide refs — but author refs in the OUTPUT aspect
# (single portrait view or vertically-stacked), since a wide sheet duplicates even when letterboxed.
# (Root-caused 2026-06: confirmed in licon_msr.py cv2.resize-to-canvas + a portrait-vs-wide-ref A/B.)

def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr); sys.exit(code)

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        die(f"command failed: {' '.join(cmd)}\n{r.stderr.strip()[:500]}")
    return r

def win_input_dir():
    """ComfyUI input dir, resolved for staging reference images."""
    d = os.environ.get("COMFY_INPUT_DIR")
    if d: return d
    # battlestation default (WSL view)
    return "/mnt/c/ComfyUI-Production/ComfyUI-Easy-Install/ComfyUI/input"

def host_path(p):
    """VHS_LoadAudio opens the file on the ComfyUI HOST, so it needs a host-readable path.
    On WSL driving a Windows ComfyUI, a /mnt/c/... path is invalid there — convert to C:\\...
    via `wslpath -w`. Native (same-OS) setups pass through unchanged. Override with
    COMFY_HOST_PATHSTYLE=native to force pass-through."""
    if os.environ.get("COMFY_HOST_PATHSTYLE") == "native":
        return p
    if p.startswith("/mnt/"):
        try:
            r = subprocess.run(["wslpath", "-w", p], capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except FileNotFoundError:
            pass
    return p

def _warn_wide_ref(path, CW, CH):
    """HARD-warn when a subject ref is LANDSCAPE (or much wider than the portrait canvas). A wide
    turnaround sheet can't be saved by any fit for portrait video: letterboxed it shrinks to a thin
    strip and the model DUPLICATES the subject (stacked figures). Author refs as a PORTRAIT subject
    that fills a ~9:16 frame — a single portrait view, or views stacked VERTICALLY."""
    from PIL import Image
    w, h = Image.open(path).size
    canvas_is_portrait = CH >= CW
    if (w > h) or (canvas_is_portrait and (w / h) > (CW / CH) + 0.25):
        print(f"WARNING: reference {os.path.basename(path)} is landscape/wide (aspect {w/h:.2f}) but the "
              f"canvas is portrait ({CW}x{CH}, {CW/CH:.2f}). A wide turnaround sheet WILL likely render a "
              f"duplicated/stacked subject. Use a PORTRAIT reference (single view, or views stacked "
              f"VERTICALLY) that fills the frame.", file=sys.stderr)

def canvas_dims(bg_path, res):
    """The exact render canvas (W,H): bg's longer edge -> res, both multiples of 32.
    Matches what the workflow's 'scale longer dimension' + LTX /32 rounding produce."""
    from PIL import Image
    bw, bh = Image.open(bg_path).size
    ar = bw / bh
    if bh >= bw:  # portrait / square
        H = res; W = max(32, round(res * ar / 32) * 32)
    else:         # landscape
        W = res; H = max(32, round((res / ar) / 32) * 32)
    return W, H

def fit_letterbox(src, W, H, dst):
    """Uniform-scale src to FIT inside W×H and pad (letterbox) — NEVER stretch. Why this matters:
    the LiconMSR node anamorphically resizes every reference to the canvas W×H. If a reference's
    aspect != the canvas (e.g. a WIDE turnaround sheet into a TALL video) the subject comes out
    elongated/duplicated. Pre-fitting each ref to EXACTLY the canvas dims makes that resize a no-op
    (or uniform), so identity proportions are preserved at full resolution. (Root cause + fix found
    2026-06: confirmed in licon_msr.py's cv2.resize-to-target, no aspect preservation.)"""
    from PIL import Image
    im = Image.open(src).convert("RGB"); w, h = im.size
    s = min(W / w, H / h)
    nw, nh = max(1, round(w * s)), max(1, round(h * s))
    im = im.resize((nw, nh), Image.LANCZOS)
    pad = Image.new("RGB", (W, H), im.getpixel((1, 1)))
    pad.paste(im, ((W - nw) // 2, (H - nh) // 2))
    pad.save(dst)
    return dst

def stage_image(path, name, indir):
    """Copy a ref image into ComfyUI's input dir; return the bare filename it expects."""
    if not os.path.isfile(path): die(f"reference not found: {path}")
    dst = os.path.join(indir, name)
    run(["cp", path, dst])
    return name

def make_ambient(src, dst):
    """Flatten a track into a low atmospheric bed so the subject stays GROUNDED, not dancing.
    LTX 2.3 is audio-visual: a music beat drives dance motion. For cinematic/BTS, drive with
    this bed and post-mux the real track on top instead."""
    run(["ffmpeg","-nostdin","-loglevel","error","-y","-i",src,
         "-af","lowpass=f=450,acompressor=threshold=-30dB:ratio=20:attack=200:release=1000,volume=-13dB",
         "-ac","1","-ar","44100", dst])

def api(comfy, path, data=None):
    url = comfy.rstrip("/") + path
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        die(f"ComfyUI {path} -> HTTP {e.code}: {body[:600]}")

def normalize_container(path):
    """Scale the output to the nearest standard container with SAR 1:1.

    Why this exists (hard-won): the render is NOT geometrically broken — a circle pushed
    through the clean tier comes out round. But two things make a correct render LOOK
    stretched: (1) the muxed mp4 carries an unset SAR plus an odd width (e.g. 864), and many
    players/previews then guess the wrong pixel-aspect; (2) only the draft(512)/clean(1536)
    tiers land on an exact-9:16 multiple-of-32 — fast/standard/fluid/cinematic render a few %
    off-aspect. Scaling to a standard size (1080x1920 etc.) and stamping SAR 1:1 fixes both:
    it removes the player ambiguity and re-stretches an off-aspect render back to true 9:16.
    """
    import subprocess as _sp
    pr = _sp.run(["ffprobe","-v","error","-select_streams","v:0",
                  "-show_entries","stream=width,height","-of","csv=p=0:s=x", path],
                 capture_output=True, text=True)
    try:
        w, h = (int(x) for x in pr.stdout.strip().split("x"))
    except Exception:
        return  # can't probe; leave as-is
    a = w / h
    # snap to the nearest standard 9:16 / 16:9 / 1:1 container; else keep native dims
    if abs(a - 9/16) < 0.06:   tw, th = 1080, 1920
    elif abs(a - 16/9) < 0.10: tw, th = 1920, 1080
    elif abs(a - 1) < 0.06:    tw, th = 1080, 1080
    else:                      tw, th = (w + w % 2), (h + h % 2)
    tmpf = path + ".norm.mp4"
    run(["ffmpeg","-nostdin","-loglevel","error","-y","-i",path,
         "-vf", f"scale={tw}:{th}:flags=lanczos,setsar=1",
         "-c:v","libx264","-crf","17","-pix_fmt","yuv420p","-c:a","copy", tmpf])
    run(["mv","-f", tmpf, path])


def main():
    ap = argparse.ArgumentParser(description="LTX 2.3 MSR multi-subject reference -> video")
    ap.add_argument("--subject1", required=True, help="primary subject reference (multi-view sheet recommended)")
    ap.add_argument("--subject2", help="second subject/object reference (sheet or object). Reused if omitted.")
    ap.add_argument("--background", required=True, help="background/scene reference. ITS ORIENTATION sets the "
                    "output aspect (portrait ref -> vertical 9:16 video).")
    ap.add_argument("--global", dest="global_prompt", required=True,
                    help="describes the refs + scene; refer to them as 'image 1' / 'image 2'.")
    ap.add_argument("--segments", required=True,
                    help="action beats over time, '|'-separated (PromptRelay). Keep to MEDIUM action — "
                         "LTX smears high action. To avoid an acting-to-camera look, ORIENT the subject "
                         "away (profile/3-4) in the text; 'don't look at camera' alone loses to the front bias.")
    ap.add_argument("--audio", required=True, help="driving audio. SILENT input -> frozen subjects; "
                    "audio energy/beat drives the motion.")
    ap.add_argument("--ambient", action="store_true", help="flatten --audio into an atmospheric bed so the "
                    "subject stays grounded (no dancing), then post-mux the original --audio onto the output. "
                    "Use for cinematic/BTS; omit for music videos (let the beat drive the motion).")
    ap.add_argument("--soundtrack", help="override the post-mux track (default: the original --audio when --ambient).")
    ap.add_argument("--quality", choices=list(QUALITY), default="fast")
    ap.add_argument("--duration", type=int, default=10, help="seconds (50 fps -> ceil(dur*50)+1 frames)")
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--out", required=True, help="output mp4 path")
    ap.add_argument("--raw-aspect", action="store_true",
                    help="skip the standard-container normalize (leave native render dims + SAR). "
                         "By default the output is scaled to the nearest standard container "
                         "(1080x1920 / 1920x1080 / 1080x1080) with SAR 1:1 — this is BOTH the playback "
                         "fix (unset SAR + odd widths read as 'stretched' in many players) AND the "
                         "geometry fix (only the draft/clean tiers are exact 9:16; fast/standard/fluid/"
                         "cinematic render a few % off-aspect, which the normalize corrects).")
    ap.add_argument("--comfy-url", default=os.environ.get("COMFY_URL", "http://127.0.0.1:8188"))
    ap.add_argument("--prefix", default=None,
                    help="output name in ComfyUI's output/ folder. Defaults to msr/<--out basename>, so the "
                         "run's files (video + -audio + workflow .png) are recognizable by the clip name.")
    args = ap.parse_args()

    res, sigmas, distill = QUALITY[args.quality]
    # name the run's output/ files after the deliverable so they're recognizable + reproducible
    prefix = args.prefix or ("msr/" + os.path.splitext(os.path.basename(args.out))[0])
    indir = win_input_dir()
    tmp = tempfile.mkdtemp(prefix="msr_")

    # stage references — pre-fit EACH to the EXACT render canvas (letterbox, no stretch) so the node's
    # resize is a no-op and LiconMSR can't anamorphically distort the subject. A subject ref MUST be a
    # PORTRAIT subject that fills a ~9:16 frame (single view, or views stacked VERTICALLY) — _warn_wide_ref
    # flags a landscape sheet, which can't be saved: letterboxed it becomes a thin strip and the model
    # DUPLICATES it (stacked bodies). (Root-cause + fix nailed 2026-06; see SKILL.md.)
    CW, CH = canvas_dims(args.background, res)
    _warn_wide_ref(args.subject1, CW, CH)
    if args.subject2: _warn_wide_ref(args.subject2, CW, CH)
    s1 = stage_image(fit_letterbox(args.subject1, CW, CH, os.path.join(tmp, "fit_s1.png")),
                     "msr_subject1.png", indir)
    bg = stage_image(fit_letterbox(args.background, CW, CH, os.path.join(tmp, "fit_bg.png")),
                     "msr_background.png", indir)

    # driving audio (+ optional ambient flattening). Workflow needs a real file on the ComfyUI host;
    # we stage it into the input dir and reference by absolute Windows-style path is avoided by using
    # the input dir, which VHS_LoadAudio resolves.
    drive_src = args.audio
    if args.ambient:
        amb = os.path.join(tmp, "ambient.wav"); make_ambient(args.audio, amb); drive_src = amb
    drive_name = "msr_drive.wav"
    run(["cp", drive_src, os.path.join(indir, drive_name)])
    drive_for_comfy = host_path(os.path.join(indir, drive_name))  # VHS_LoadAudio needs a host path

    # build the prompt graph
    j = json.load(open(TEMPLATE))
    j[N_SUBJ1]["inputs"]["image"] = s1
    j[N_BG]["inputs"]["image"] = bg
    # SUBJECT COUNT IS DYNAMIC. LiconMSR's subject inputs (1/2/3/4) are all OPTIONAL. Wire only the
    # references actually given. The old behavior fed subject1 into BOTH slots (subject2 = subject1)
    # when --subject2 was omitted — telling MSR "two identical subjects", which makes it render a
    # STACKED / VERTICALLY-ELONGATED / DUPLICATED figure (worse at higher res×duration). Root cause of
    # the "stretch" hunt, 2026-06. For a single subject: drop LiconMSR input "2" + its orphan nodes.
    if args.subject2:
        s2 = stage_image(fit_letterbox(args.subject2, CW, CH, os.path.join(tmp, "fit_s2.png")),
                         "msr_subject2.png", indir)
        j[N_SUBJ2]["inputs"]["image"] = s2
    else:
        j[N_LICON]["inputs"].pop("2", None)   # unwire the 2nd subject from LiconMSR
        j.pop(N_SUBJ2, None)                   # remove the orphan subject-2 LoadImage
        j.pop(N_SUBJ2_RESIZE, None)            # and its resize node

    j[N_GLOBAL]["inputs"]["value"] = args.global_prompt
    j[N_SEGMENTS]["inputs"]["value"] = "\n|\n".join(p.strip() for p in args.segments.split("|"))
    j[N_AUDIO]["inputs"]["audio_file"] = drive_for_comfy
    j[N_AUDIO]["inputs"]["seek_seconds"] = 0
    j[N_RES]["inputs"]["value"] = res
    j[N_SIGMAS]["inputs"]["sigmas"] = sigmas
    j[N_DISTILL]["inputs"]["strength_model"] = distill
    j[N_DURATION]["inputs"]["value"] = args.duration
    for nid, n in j.items():
        if n.get("class_type") == "Seed (rgthree)":
            n["inputs"]["seed"] = args.seed
    j[N_OUT]["inputs"]["filename_prefix"] = prefix
    # plain: the workflow saves to output/<prefix> with ComfyUI's default naming
    # (video + -audio + workflow .png). No post-management of the output folder.

    # submit
    pid = api(args.comfy_url, "/prompt", {"prompt": j}).get("prompt_id")
    if not pid: die("no prompt_id returned")
    print(f"submitted {pid} (quality={args.quality} res={res} dur={args.duration}s)")

    # poll — VHS emits both a silent .mp4 and a muxed -audio.mp4; prefer the audio one,
    # and use the file's actual type (temp/output) since we render to temp.
    out = None  # (type, subfolder, filename)
    while True:
        time.sleep(8)
        hist = api(args.comfy_url, f"/history/{pid}")
        if not hist: continue
        h = list(hist.values())[0]
        st = h.get("status", {}).get("status_str")
        if st == "success":
            cands = [v for o in h.get("outputs", {}).values()
                     for v in o.get("gifs", []) if v.get("filename", "").endswith(".mp4")]
            pick = ([v for v in cands if v["filename"].endswith("-audio.mp4")] or cands or [None])[0]
            if pick:
                out = (pick.get("type", "temp"), pick.get("subfolder", ""), pick["filename"])
            break
        if st == "error":
            die("render failed — check ComfyUI's user/comfyui.log (a 35ms 'success' usually means a "
                "validation error on an output node that ComfyUI silently ignored).")

    if not out: die("render finished but no mp4 output found")
    typ, sub, name = out
    q = (f"filename={urllib.parse.quote(name)}&subfolder={urllib.parse.quote(sub)}"
         f"&type={urllib.parse.quote(typ)}")
    raw = os.path.join(tmp, "raw.mp4")
    urllib.request.urlretrieve(args.comfy_url.rstrip("/") + "/view?" + q, raw)

    # post-mux the real soundtrack over the grounded motion (ambient mode)
    if args.ambient:
        track = args.soundtrack or args.audio
        run(["ffmpeg","-nostdin","-loglevel","error","-y","-i",raw,"-i",track,
             "-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","aac","-shortest", args.out])
    else:
        run(["cp", raw, args.out])

    if not args.raw_aspect:
        normalize_container(args.out)

    print(f"done -> {args.out}")

if __name__ == "__main__":
    main()
