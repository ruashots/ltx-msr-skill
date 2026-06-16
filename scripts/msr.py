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

Reference images: use MULTI-VIEW TURNAROUND SHEETS (front/back/side + face), not single
shots — identity must survive motion. Recognizable IP characters -> generate via the
`chatgpt-images` skill (it knows them); original characters -> `ideogram4`.
"""
import argparse, json, os, subprocess, sys, tempfile, time
import urllib.request, urllib.error, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "assets", "msr_base.json")

# --- node ids in the bundled template (validated; see assets/msr_base.json) ---
N_SUBJ1, N_SUBJ2, N_BG = "80", "81", "85"
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
    "cinematic": (1920, "1.0, 0.992, 0.984, 0.975, 0.95, 0.91, 0.85, 0.76, 0.66, 0.54, 0.41, 0.28, 0.14, 0.0", 0.35),  # ~15min@10s
}

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
    ap.add_argument("--comfy-url", default=os.environ.get("COMFY_URL", "http://127.0.0.1:8188"))
    ap.add_argument("--prefix", default="msr/out")
    args = ap.parse_args()

    res, sigmas, distill = QUALITY[args.quality]
    indir = win_input_dir()
    tmp = tempfile.mkdtemp(prefix="msr_")

    # stage references
    s1 = stage_image(args.subject1, "msr_subject1.png", indir)
    s2 = stage_image(args.subject2 or args.subject1, "msr_subject2.png", indir)
    bg = stage_image(args.background, "msr_background.png", indir)

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
    j[N_SUBJ2]["inputs"]["image"] = s2
    j[N_BG]["inputs"]["image"] = bg
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
    j[N_OUT]["inputs"]["filename_prefix"] = args.prefix

    # submit
    pid = api(args.comfy_url, "/prompt", {"prompt": j}).get("prompt_id")
    if not pid: die("no prompt_id returned")
    print(f"submitted {pid} (quality={args.quality} res={res} dur={args.duration}s)")

    # poll
    fn = None
    while True:
        time.sleep(8)
        hist = api(args.comfy_url, f"/history/{pid}")
        if not hist: continue
        h = list(hist.values())[0]
        st = h.get("status", {}).get("status_str")
        if st == "success":
            for o in h.get("outputs", {}).values():
                for v in o.get("gifs", []):
                    if v.get("filename", "").endswith(".mp4"):
                        fn = (v.get("subfolder", ""), v["filename"]); break
            break
        if st == "error":
            die("render failed — check ComfyUI's user/comfyui.log (a 35ms 'success' usually means a "
                "validation error on an output node that ComfyUI silently ignored).")

    if not fn: die("render finished but no mp4 output found")
    sub, name = fn
    q = f"filename={urllib.parse.quote(name)}&subfolder={urllib.parse.quote(sub)}&type=output"
    raw = os.path.join(tmp, "raw.mp4")
    urllib.request.urlretrieve(args.comfy_url.rstrip("/") + "/view?" + q, raw)

    # post-mux the real soundtrack over the grounded motion (ambient mode)
    if args.ambient:
        track = args.soundtrack or args.audio
        run(["ffmpeg","-nostdin","-loglevel","error","-y","-i",raw,"-i",track,
             "-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","aac","-shortest", args.out])
    else:
        run(["cp", raw, args.out])

    print(f"done -> {args.out}")

if __name__ == "__main__":
    main()
