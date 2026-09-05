# Phase 1 setup (dev account)

Build the full intake + catalog workflow on **your personal Google account** first.
When ready for production, swap folder IDs, Sheet, Form, and re-run `--auth` on the
production account (see plan cutover checklist).

## 1. Google Cloud OAuth (if not done)

1. Enable **Google Drive API** and **Google Sheets API** in your Cloud project.
2. OAuth consent screen → add your Gmail as a test user.
3. Create **Desktop app** OAuth client → save as `credentials.json`.

**Important:** Phase 1 adds Sheets scope. If you already have `token.json`, delete it
and re-authorize:

```powershell
Remove-Item token.json
python main.py --auth
```

## 2. Drive folders

In your personal Drive, create:

```
Reality Show/
├── Confessionals/
│   └── Inbox/          ← contestants upload here
└── (Transcripts/       ← created automatically by the script)
     lives under parent)
```

Copy folder IDs from the URL (`/folders/FOLDER_ID`):

- **Inbox** → `source_folder_id` in `config.json`
- **Reality Show** (parent) → `output_folder_id` (script creates `Transcripts/` inside)

## 3. Catalog Google Sheet

1. Create a new Google Sheet (e.g. "Confessional Catalog").
2. Add a tab named **Catalog** (or use default and set `catalog_tab` in config).
3. Copy the spreadsheet ID from the URL → `catalog_sheet_id` in `config.json`.

Initialize column headers:

```powershell
python main.py --init-catalog
```

Columns written:

| drive_file_id | filename | contestant | submitted_at | duration | status | video_link | transcript_txt_link | transcript_srt_link | note | whatsapp_message |

## 4. Google Form (contestant upload)

1. Create a Form with:
   - **Name** — dropdown (list your contestants)
   - **Note** — short answer (optional)
   - **Video** — file upload
2. In Form settings → **Collect email addresses** off (optional).
3. Link Form to your **Catalog spreadsheet** (Responses tab → Link to Sheets).
   - This creates a **Form Responses 1** tab on the same spreadsheet.
4. Set Form to store uploaded files in Drive (default: form owner's Drive).
   - Move/copy the Form's upload folder to **Inbox**, or set the Form's upload
     destination to Inbox if your Form UI offers a folder picker.

**Column titles must match config** (defaults):

| Form question | config key | default |
|---------------|------------|---------|
| Name dropdown | `form_contestant_column` | `Name` |
| Note | `form_note_column` | `Note` |
| Video upload | `form_file_column` | `Video` |

If your question titles differ, update `config.json` to match exactly.

## 5. config.json

Minimum for Phase 1:

```json
{
  "source_folder_id": "your-inbox-folder-id",
  "output_folder_id": "your-parent-folder-id",
  "catalog_sheet_id": "your-spreadsheet-id",
  "transcription_backend": "openai",
  "output_formats": ["txt", "srt"],
  "contestant_names": ["Jason Stitt", "Other Name"]
}
```

`contestant_names` is optional — used to guess contestant from filename when Form
matching fails (manual Inbox drops).

Leave `form_response_sheet_id` empty to use the same spreadsheet as the catalog.

## 6. Test end-to-end

1. Submit a test video via the Form (or drop a file in Inbox).
2. Run:

```powershell
python main.py
```

3. Check:
   - **Catalog** tab → row with `ready`, links, `whatsapp_message`
   - **Transcripts/** folder → `.txt` and `.srt`
   - Copy `whatsapp_message` into WhatsApp to verify the link plays on mobile

## 7. Schedule on your PC

Windows Task Scheduler → run `python main.py` every 5 minutes in this folder.
Ensure `OPENAI_API_KEY` is set for the task environment.

## 8. Email notifications (optional)

When a confessional finishes processing, send the WhatsApp copy-paste line to a list of recipients.

1. Enable **Gmail API** in Google Cloud Console (same project as Drive/Sheets).
2. Re-authorize (adds `gmail.send` scope):
   ```powershell
   Remove-Item token.json
   python main.py --auth
   ```
3. In `config.json`:
   ```json
   "notification_emails": ["producer1@gmail.com", "producer2@gmail.com"],
   "production_contestant_names": ["Production"],
   "production_notification_emails": ["sam.averis@gmail.com", "asinensky@gmail.com"]
   ```
   Confessionals whose **Name** is `Production` (or any name in `production_contestant_names`) use the production list; all others use `notification_emails`.
4. Emails are sent **from the same Google account** you used for `--auth`.

Email body includes the ready-to-paste WhatsApp line (with one-sentence summary when analysis is enabled), plus optional note and transcript link.

## 9. AI analysis (auto summaries)

After each confessional is transcribed, optional OpenAI analysis runs automatically:
a **one-sentence summary** (stored in the catalog `summary` column) and **key moments
with timestamps** (embedded at the top of the transcript `.md` file on Drive).

1. Ensure `OPENAI_API_KEY` is set (same key as Whisper).
2. In `config.json`:
   ```json
   "analysis_enabled": true,
   "prompts_file": "prompts.yaml",
   "openai_analysis_model": "gpt-4o-mini"
   ```
3. Edit [`prompts.yaml`](prompts.yaml) to tune prompts — or use **Settings** in the Producer Console (summary + key moments).
4. Run `python main.py --init-catalog` once to add the catalog `summary` column.

Re-run analysis without re-transcribing (updates the existing `.md` on Drive):

```powershell
python main.py --reanalyze --confessional-id <uuid-from-catalog>
```

Analysis failures are logged but do not fail transcription.

## 32FRSFFL Producer Console (Phase 2, Tailscale)

Interactive **32FRSFFL Producer Console** (`producer_app.py`) for producers — Streamlit over **Tailscale** with chat-only access (tailnet members cannot reach RDP, SMB, or other ports on this PC).

### Install

```powershell
pip install -r requirements.txt
```

Ensure `producer.yaml` exists (committed template) and `config.json` includes:

```json
"producer_config_file": "producer.yaml"
```

Access is gated by **Tailscale** only (ACL + Serve). No app password.

### Tailscale setup (chat-only access)

1. Install [Tailscale](https://tailscale.com/download) on the transcriber PC and sign in.
2. Require **2FA** for all tailnet users (Tailscale admin → Settings).
3. Invite each producer individually — do not share one Tailscale login.
4. Tag the transcriber PC in [Machines](https://login.tailscale.com/admin/machines):
   - Edit the machine → add tag **`tag:transcriber`**
5. Apply the ACL in **Access controls** (copy from [`tailscale/producer_acl.json`](tailscale/producer_acl.json)):

```json
{
  "tagOwners": {
    "tag:transcriber": ["autogroup:admin"]
  },
  "acls": [
    {
      "action": "accept",
      "src": ["autogroup:member"],
      "dst": ["tag:transcriber:443"]
    }
  ]
}
```

This allows tailnet members to reach **only** HTTPS on the tagged machine (Tailscale Serve → Producer Console). No other ports or devices are reachable.

Leave **subnet routing**, **exit nodes**, and **Tailscale Funnel** disabled.

**Enable Tailscale Serve** on your tailnet (required for HTTPS access). Run `tailscale serve status` on the transcriber PC — if Serve is not enabled, open the admin link it prints and turn it on for this machine.

### Firewall (run once on transcriber PC)

From PowerShell **as Administrator**:

```powershell
.\register_producer_firewall.ps1
```

This blocks direct access to Streamlit on port 8501 from Tailscale and blocks RDP/SMB from the tailnet. It does **not** change normal internet or home LAN use.

### Run the app

```powershell
.\run_producer_app.bat
```

This starts Streamlit on `127.0.0.1:8501` and exposes it via **Tailscale Serve** at `https://<machine-name>`.

Producers open **`https://<machine-name>`** (MagicDNS — run `tailscale status` on the PC to see the name).

To stop:

```powershell
.\stop_producer_app.bat
```

### Start at boot (optional)

Register a Windows Task Scheduler job (runs 1 minute after you log in, so Tailscale is up):

```powershell
.\register_producer_startup_task.ps1
```

Log: `producer_app.log`. Test manually: `schtasks /Run /TN "Producer Chat"`

**Do not use** Streamlit’s public “External URL” — firewall rules should block it.

Local development on the PC: `http://localhost:8501`

### Normal networking

These changes do **not** affect web browsing, the scheduled transcriber, Drive/Sheets API calls, or home Wi‑Fi/LAN. They only restrict what tailnet users can reach on this machine.

**Chat tab** — pick scope (one confessional, all compact, or all full), then ask questions.

**Browse tab** — transcript and key moments in two columns (left: transcript, right: key moments). Existing confessionals show both side-by-side without row alignment. New confessionals export timestamped `[HH:MM:SS]` lines in the markdown body and align moments to matching transcript rows. Embedded Drive video above the transcript panel.

**Settings tab** — edit chat persona (`producer.yaml`), **summary** and **key moments** pipeline prompts (`prompts.yaml`), and model. Pipeline prompt changes apply to the next confessional and `--reanalyze` runs.

**History tab** — read saved conversations from the local `conversations/` folder.

### Verify access (from a producer device on tailnet)

| Test | Expected |
|------|----------|
| `https://<machine-name>` | Chat loads |
| `http://<machine-name>:8501` | Blocked / timeout |
| RDP to transcriber Tailscale IP | Blocked |

Check Serve is running: `tailscale serve status`

### Daily summary

Morning job appends to `Transcripts/Analysis/daily_summaries.md` on Drive and emails `notification_emails`.

Edit prompt in `producer.yaml` → `daily_summary` section.

```powershell
python producer_daily.py
```

Schedule daily (8:00 AM default):

```powershell
.\register_daily_summary_task.ps1
```

PC must be on at the scheduled time.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `403` or `accessNotConfigured` on Sheets | Enable Google Sheets API in Cloud Console |
| `invalid_scope` / Sheets errors after upgrade | Delete `token.json`, run `python main.py --auth` |
| Contestant empty in catalog | Check Form column names match config; verify file landed in Inbox |
| WhatsApp link asks for login | Script sets link sharing; re-run or share file manually once |
| Form file not matched | Form response URL must contain Drive file ID; widen `form_match_window_minutes` |
| Email notification failed | Enable Gmail API; delete `token.json` and re-run `--auth`; check `notification_emails` |
| Analysis skipped / empty | Set `analysis_enabled: true`; check `prompts.yaml` exists; verify `OPENAI_API_KEY` |
| Re-analyze fails | Catalog row needs `transcript_srt_link`; use confessional_id from Catalog tab |
| Producer Console unreachable | PC awake; Tailscale connected; run `run_producer_app.bat`; check `tailscale serve status` |
| Producer Console ACL denied | Machine tagged `tag:transcriber`; ACL allows `:443`; user invited to tailnet |
| Daily summary not emailed | Check `notification_emails`; Gmail API authorized; run `python producer_daily.py` manually |

## Moving to production later

1. Recreate folders, Form, and Sheet on production Google account.
2. New `credentials.json` / `token.json` via `python main.py --auth`.
3. Update `config.json` IDs — no code changes needed.
