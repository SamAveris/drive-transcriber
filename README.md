# Drive Video Transcriber

Watches a Google Drive folder for new videos and automatically transcribes
them using the OpenAI Whisper API, writing each transcript back to a
`Transcripts` subfolder in Drive.

Designed to run unattended on a schedule (cron, Task Scheduler, or a cloud
scheduler) -- see "Scheduling it" below.

## How it decides what's "new"

Rather than a local state file, the script tags each processed video with a
custom Drive property (`transcript_status = done` or `failed`). This means:
- You can run it from anywhere (a VM, your laptop, a serverless function) and it won't reprocess files.
- To force a re-run on a specific video, remove the property in the Drive UI (File info > Details) or clear it via the API.
- Files that fail once are marked `failed` and skipped on future runs, so a broken file doesn't burn API credits every cycle. Fix the issue, clear the property, and it'll be picked up again.

## 1. Set up Google Cloud access

1. Create (or reuse) a project at https://console.cloud.google.com
2. Enable the **Google Drive API** for that project (APIs & Services > Enable APIs).
3. Create a **service account** (IAM & Admin > Service Accounts > Create).
4. Create a key for it (JSON), download it, and save it as `service_account.json` in this folder.
5. Open the JSON file and copy the `client_email` value -- it looks like `xxx@yyy.iam.gserviceaccount.com`.
6. In Google Drive, **share your source folder and output folder with that email** (Viewer is enough for the source folder, Editor for the output folder).

## 2. Set up OpenAI access

1. Get an API key from https://platform.openai.com/api-keys
2. Export it as an environment variable wherever the script runs:
   ```bash
   export OPENAI_API_KEY="sk-..."
   ```

## 3. Install and configure

```bash
pip install -r requirements.txt
cp config.example.json config.json
```

Edit `config.json`:
- `source_folder_id` -- the Drive folder you upload videos into. (Grab this from the folder's URL: the long string after `/folders/`.)
- `output_folder_id` -- where the `Transcripts` subfolder should be created. Can be the same folder.
- `service_account_file` -- path to the JSON key from step 1.
- `chunk_minutes` -- how long each audio chunk is before sending to Whisper (20 min default keeps chunks safely under the 25MB API limit).

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
*/15 * * * * cd /path/to/drive-transcriber && OPENAI_API_KEY=sk-... /usr/bin/python3 main.py >> transcriber.log 2>&1
```

**Option B -- Windows Task Scheduler:** create a Basic Task that runs
`python main.py` in this folder on a repeating trigger (e.g. every 15 min).

**Option C -- fully cloud-hosted, no machine to keep on (Google Cloud Run + Cloud Scheduler):**
Containerize this script (a minimal Dockerfile with `ffmpeg` installed plus
`pip install -r requirements.txt`), deploy it as a Cloud Run job, and trigger
it on a schedule with Cloud Scheduler. This avoids needing a personal
machine running 24/7. I'm happy to build the Dockerfile and deployment
config if you want to go this route -- just say the word.

## Notes on cost and limits

- Whisper API pricing is per audio-minute -- check current pricing at
  https://openai.com/api/pricing before running this against a large backlog.
- Long videos are chunked automatically; there's no hard cap on video length
  in this script, but very long videos will mean more API calls and cost.
- If a video's audio track is silent/empty or the video has no audio stream,
  ffmpeg extraction will fail and the file will be marked `failed` --
  check `transcriber.log` (if using cron) for details.
