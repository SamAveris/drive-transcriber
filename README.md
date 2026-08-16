# Drive Video Transcriber

Watches a Google Drive folder for new videos, extracts audio locally with
ffmpeg, transcribes via the **OpenAI Whisper API** by default, and writes
`.txt` and `.srt` files to a `Transcripts` subfolder in Drive.

Designed to run unattended on a schedule (cron, Task Scheduler, or a cloud
scheduler) -- see "Scheduling it" below.

## How it decides what's "new"

Rather than a local state file, the script tags each processed video with a
custom Drive property (`transcript_status = done` or `failed`). This means:
- You can run it from anywhere (a VM, your laptop, a serverless function) and it won't reprocess files.
- To force a re-run on a specific video, remove the property in the Drive UI (File info > Details) or clear it via the API.
- Files that fail once are marked `failed` and skipped on future runs, so a broken file doesn't waste time every cycle. Fix the issue, clear the property, and it'll be picked up again.

## 1. Set up Google Drive access

1. Create (or reuse) a project at https://console.cloud.google.com
2. Enable the **Google Drive API** (APIs & Services > Enable APIs).
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

**Why OAuth?** Personal Google accounts (Gmail) do not allow service accounts
to upload files -- Google returns "Service Accounts do not have storage quota."
OAuth uses your account, so transcripts upload normally. Service account auth
(`"auth": "service_account"` in config) remains available if you later move
this to a Google Workspace **shared drive**.

## 2. Set up OpenAI transcription

Transcription uses the OpenAI Whisper API (`whisper-1` by default). Audio is
still extracted on your machine with ffmpeg -- only the speech-to-text step
runs in the cloud.

1. Add billing/credits at https://platform.openai.com and create an API key.
2. Set the environment variable wherever the script runs:
   ```powershell
   $env:OPENAI_API_KEY = "sk-..."
   ```
   To persist on Windows:
   ```powershell
   [System.Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "sk-...", "User")
   ```
   Restart the terminal (or Cursor) after persisting.

Default model is `whisper-1` ($0.006/min). Alternatives in config:
`gpt-4o-mini-transcribe` (cheaper), `gpt-4o-transcribe` (higher accuracy).
Long audio is chunked automatically (`chunk_minutes`, default 20) to stay
under OpenAI's 25MB upload limit.

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

Everything else comes from `config.example.json` automatically (OpenAI
model, output formats, poll size, etc.). When this repo adds new config
options, you don't have to touch `config.json` unless you want to override
the new default.

See `config.example.json` for the full list of available options and their
defaults. Common overrides beyond the folder IDs:
- `openai_model` -- `whisper-1` (default), `gpt-4o-mini-transcribe`, etc.
- `output_formats` -- `["txt", "srt"]` by default.
- `transcription_backend` -- set to `"local"` for GPU faster-whisper instead.

## 4. Test it manually first

```bash
python main.py
```

Or test a local video without Drive:

```powershell
python main.py --local-file "C:\path\to\video.mp4"
```

Outputs land in Drive (`Transcripts/`) or locally in `pilot_output/`.

## 5. Scheduling it (the "automatic" part)

Ensure `OPENAI_API_KEY` is set in the environment for the scheduled task
(Task Scheduler → Environment variables, or set system-wide).

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

## Local GPU transcription (optional)

To run faster-whisper on your own GPU instead of the OpenAI API, set in
`config.json`:

```json
{
  "transcription_backend": "local",
  "whisper_model": "medium",
  "device": "cuda",
  "compute_type": "float16"
}
```

Requires an NVIDIA GPU (`nvidia-smi`), CUDA libs in `requirements.txt`, and
no per-minute API cost. Useful for offline use or if you want to keep audio
off third-party servers.

| Model       | Notes                                                   |
|-------------|----------------------------------------------------------|
| `medium`    | Good default for a gaming GPU                           |
| `large-v3`  | Best accuracy; slower even on GPU                         |

## Notes

- **API cost:** ~$0.006/min with `whisper-1` -- check usage at
  https://platform.openai.com/usage
- If a video's audio track is silent/empty or the video has no audio stream,
  ffmpeg extraction will fail and the file will be marked `failed` --
  check `transcriber.log` (if using cron) for details.
- Drive filenames with colons (e.g. `07:55` from phone timestamps) are
  sanitized automatically on Windows (`07-55`).
