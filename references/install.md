# MSR install (one-time, ComfyUI)

MSR rides LiconStudio's LTX 2.3 Multiple-Subject-Reference workflow. You need ComfyUI with
these custom nodes + models, then point the skill at it (`COMFY_URL`, default `localhost:8188`;
`COMFY_INPUT_DIR` if your input folder isn't the battlestation default).

## Custom nodes (clone into `ComfyUI/custom_nodes`, restart)
| Node pack | Provides | Source |
|---|---|---|
| ComfyUI-Licon-MSR | `LiconMSR` | `github.com/liconstudio/ComfyUI-Licon-MSR` (pip: `opencv-python`) |
| ComfyUI-PromptRelay | `PromptRelayEncode` | `github.com/kijai/ComfyUI-PromptRelay` (pip: `word2number`) |
| ComfyUI_Comfyroll_CustomNodes | `CR Float To Integer` | `github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes` |

Plus the LTX 2.3 base nodes (ComfyUI-LTXVideo, KJNodes, VHS, rgthree, RES4LYF, ComfyUI-Custom-Scripts).

## Models
LoRAs → `models/loras/ltx2/`:
- `ltx-2.3-22b-distilled-lora-384-1.1.safetensors` — Lightricks/LTX-2.3 (~7.6 GB)
- `LTX2.3rl-lora-zghhui-OmniNFT.safetensors` — this exact filename is a **rename** of Kijai's
  `LTX-2.3-OmniNFT-RL-Lora_bf16.safetensors` (`Kijai/LTX2.3_comfy/loras/`, ~617 MB). Same weights.
- `LTX-2.3-Licon-MSR-V1.safetensors` — `LiconStudio/LTX-2.3-Multiple-Subject-Reference` (~624 MB)

Also: `gemma_3_12B_it_fp8_scaled.safetensors`, `ltx-2.3_text_projection_bf16.safetensors`
(clip/text-encoders root — **NO `ltx2\` prefix**), `LTX23_video_vae_bf16.safetensors`, and a
combined LTX-2.3-22b checkpoint. Default checkpoint = `ltx-2.3-22b-dev-fp8.safetensors` (fits a
32 GB GPU; the full bf16 dev is ~46 GB and won't). The fp8 also serves the audio VAE.

## The two gotchas that cost the most time
1. **Per-output silent validation.** If a model path in an output node's dependency chain
   fails to resolve, ComfyUI prints `Failed to validate prompt for output N ... Output will be
   ignored` to its log and runs the *other* valid outputs — so the API returns a `prompt_id`
   and "success" in ~35 ms with **no video**. Always read `ComfyUI/user/comfyui.log` when a
   render finishes suspiciously fast. The template ships with the known path fixes baked in.
2. **Audio path must be HOST-readable.** `VHS_LoadAudio` opens the file on the ComfyUI host,
   not where the script runs. Driving a Windows ComfyUI from WSL, a `/mnt/c/...` path throws
   `audio_file is not a valid path` — the script converts it with `wslpath -w` automatically
   (override `COMFY_HOST_PATHSTYLE=native` for same-OS setups). Image refs are fine as bare
   filenames (LoadImage resolves them against the input dir); only the audio needs a full path.
3. **Headless workflow conversion.** This MSR graph (GetNode/SetNode/reroutes, no subgraphs)
   converts cleanly to an API prompt via ComfyUI's `app.graphToPrompt()` in a CDP-driven
   browser. The bundled `assets/msr_base.json` is already converted — you only edit values.

## Reference-image generation (not part of this skill, but required)
- IP characters → ChatGPT image model (knows the character; e.g. a `chatgpt-images`-style tool).
- Original characters/objects/scenes → a local text-to-image model (e.g. Ideogram 4).
- Ask for a **turnaround sheet**: same subject, front + back + 3/4 + two face close-ups, plain
  backdrop, consistent identity/wardrobe across panels.
