# Drive Video Transcriber

Watches a Google Drive **Inbox** folder for new confessional videos, transcribes
via **OpenAI Whisper API** (default), writes `.txt`/`.srt` to a `Transcripts`
subfolder, and updates a **Google Sheets catalog** with share links and
copy-paste WhatsApp messages.

Designed to run on a schedule on your PC (Task Scheduler) — see below.

**Phase 1 workflow setup:** see [PHASE1_SETUP.md](PHASE1_SETUP.md) (Form intake,
catalog Sheet, folder layout on your dev Google account).

## How it decides what's "new"

Rather than a local state file, the script tags each processed video with a
custom Drive property (`transcript_status = done` or `failed`). This means:
- You can run it from anywhere (a VM, your laptop, a serverless function) and it won't reprocess files.
- To force a re-run on a specific video, remove the property in the Drive UI (File info > Details) or clear it via the API.
- Files that fail once are marked `failed` and skipped on future runs, so a broken file doesn't waste time every cycle. Fix the issue, clear the property, and it'll be picked up again.

## 1. Set up Google Drive access

1. Create (or reuse) a project at https://console.cloud.google.com
2. Enable the **Google Drive API** and **Google Sheets API** (APIs & Services > Enable APIs).
3. Configure the **OAuth consent screen** (APIs & Services > OAuth consent
   screen). External user type is fine for personal Gmail.
4. Create an **OAuth client ID** (APIs & Services > Credentials > Create
   Credentials > OAuth client ID > **Desktop app**). Download the JSON and
   save it as `credentials.json` in this folder.
5. Authorize once (opens a browser):
   ```bash
   pip install -r requirements.txt
   python main.py --auth
   ```
   This saves `token.json` locally. Scheduled runs reuse it and refresh
   automatically -- you won't need to sign in again unless the token is revoked.

   **After upgrading to Phase 1:** delete `token.json` and re-run `--auth` once
   (Sheets scope was added).

**Why OAuth?** Personal Google accounts (Gmail) do not allow service accounts
to upload files -- Google returns "Service Accounts do not have storage quota."
OAuth uses your account, so transcripts upload normally. Service account auth
(`"auth": "service_account"` in config) remains available if you later move
this to a Google Workspace **shared drive**.

## 2. Transcription model (local, no account needed)

Transcription runs entirely on your own machine via `faster-whisper` -- no
API key, no per-minute cost, no account to set up. The first time the
script runs, it downloads the model weights from Hugging Face (a one-time
download, cached locally afterward). After that it works offline.

**You have an NVIDIA GPU, so use it** -- it's dramatically faster than CPU
and lets you comfortably run the larger, more accurate models:

1. Confirm your GPU and driver are visible: open PowerShell and run `nvidia-smi`. It should print your GPU name and a driver/CUDA version in the top-right of the output. If this command isn't found, install the latest driver from nvidia.com/drivers first.
2. The `requirements.txt` already includes `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` -- these are the CUDA runtime libraries faster-whisper needs, installed via pip so you don't need the full NVIDIA CUDA Toolkit. `transcribe.py` automatically registers their DLL locations on Windows at startup, so no manual PATH edits are needed.
3. In `config.json`, keep `"device": "cuda"` and `"compute_type": "float16"`.

| Model       | Notes                                                   |
|-------------|----------------------------------------------------------|
| `base`      | Fast even on CPU; underuses a good GPU                  |
| `small`     | Good quality, very fast on GPU                          |
| `medium`    | **Good default for a gaming GPU** -- strong accuracy, still quick |
| `large-v3`  | Best accuracy; noticeably slower even on GPU, worth it for tricky audio |

If `nvidia-smi` isn't available or you ever want to fall back to CPU-only
(e.g. running this on a different, GPU-less machine later), just set
`"device": "cpu"` and `"compute_type": "int8"` in `config.json` -- no code
changes needed, and `base` or `small` are the more realistic model choices
in that case.

## 3. Install and configure

```bash
pip install -r requirements.txt
```

Create `config.json` with just the settings you need to override. At
minimum that's your two Drive folder IDs:

```json
{
  "source_folder_id": "your-source-folder-id",
  "output_folder_id": "your-output-folder-id"
}
```

Everything else comes from `config.example.json` automatically (model size,
GPU settings, poll size, etc.). When this repo adds new config options, you
don't have to touch `config.json` unless you want to override the new
default.

See `config.example.json` for the full list of available options and their
defaults. Common overrides beyond the folder IDs:
- `service_account_file` -- path to the JSON key from step 1 (defaults to `service_account.json`).
- `whisper_model` -- faster-whisper model size (`medium` is the default).
- `device` / `compute_type` -- set to `cpu` / `int8` if you're not using a GPU.

## 4. Test it manually first

```bash
python main.py
```

You should see it list any unprocessed videos, transcribe them, and drop
`.txt` files into the `Transcripts` subfolder.

## 5. Scheduling it (the "automatic" part)

**Option A -- cron on a machine that's always on (simplest):**
```bash
crontab -e
# run every 15 minutes:
*/15 * * * * cd /path/to/drive-transcriber && /usr/bin/python3 main.py >> transcriber.log 2>&1
```

**Option B -- Windows Task Scheduler:** create a Basic Task that runs
`python main.py` in this folder on a repeating trigger (e.g. every 15 min).

**Option C -- fully cloud-hosted, no machine to keep on (Google Cloud Run + Cloud Scheduler):**
Containerize this script (a minimal Dockerfile with `ffmpeg` installed plus
`pip install -r requirements.txt`), deploy it as a Cloud Run job, and trigger
it on a schedule with Cloud Scheduler. This avoids needing a personal
machine running 24/7. I'm happy to build the Dockerfile and deployment
config if you want to go this route -- just say the word.

## OpenAI Whisper API pilot (local ffmpeg + cloud transcription)

Audio is always extracted on your machine with ffmpeg. Set
`transcription_backend` to `openai` to send the audio to OpenAI instead of
running faster-whisper locally.

1. Add billing/credits at https://platform.openai.com and create an API key.
2. Set the environment variable:
   ```powershell
   $env:OPENAI_API_KEY = "sk-..."
   ```
3. In `config.json`:
   ```json
   {
     "transcription_backend": "openai",
     "openai_model": "whisper-1",
     "output_formats": ["txt", "srt"]
   }
   ```
4. Test on a local video (no Drive):
   ```powershell
   python main.py --local-file "C:\path\to\video.mp4"
   ```
   Writes `.txt` and `.srt` to the `pilot_output/` folder in the project
   (override with `"local_output_dir"` in config).

Models: `whisper-1` (timestamps + SRT), `gpt-4o-mini-transcribe` (cheaper),
`gpt-4o-transcribe` (higher accuracy). Long audio is chunked automatically
(`chunk_minutes`, default 20) to stay under OpenAI's 25MB upload limit.

Switch back to local GPU transcription with `"transcription_backend": "local"`.

## Phase 1 catalog (Form + Sheet + WhatsApp links)

When `catalog_sheet_id` is set in `config.json`, each processed video gets a row
in the **Catalog** tab: contestant, duration, Drive links, and a pre-built
`whatsapp_message`. Form responses on the linked Sheet tab are matched to inbox
files by Drive file ID.

```powershell
python main.py --init-catalog   # write header row once
python main.py                  # poll, transcribe, update catalog
```

Full setup: [PHASE1_SETUP.md](PHASE1_SETUP.md).

## Notes on local processing

- No per-minute cost and no internet needed after the first run (once the
  model weights are cached). On your GPU, even the `medium` model should
  transcribe noticeably faster than the video's actual runtime.
- Since the whole job runs on your machine, keep an eye on GPU load if the
  scheduled task overlaps with gaming or other GPU work at that time --
  they'll compete for the same card.
- If a video's audio track is silent/empty or the video has no audio stream,
  ffmpeg extraction will fail and the file will be marked `failed` --
  check `transcriber.log` (if using cron) for details.
- If `faster-whisper` falls back to CPU speed unexpectedly (transcription
  feels slow despite having a GPU), double check `nvidia-smi` still runs
  and that `device`/`compute_type` in `config.json` are still set to
  `cuda`/`float16` -- a typo here silently falls back to CPU rather than
  erroring.
