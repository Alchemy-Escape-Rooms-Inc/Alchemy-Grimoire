# Grimoire Auto-Regeneration — Setup Guide

## What This Does

Every day at 6 AM, a Python script will:
1. Clone all your escape room repos from GitHub
2. Scan every source file for pin assignments, MQTT topics, broker IPs, bugs, and security issues
3. Send the extracted data to the Claude API for deep analysis
4. Regenerate all 9 dynamic Grimoire documents
5. Push the updated Grimoire to GitHub

Estimated cost: **~$0.50–$1.00 per run** using Claude Sonnet (or ~$2–3 with Opus for deeper analysis).

---

## Step 1: Install Python

If you don't have Python installed:
1. Go to https://python.org/downloads
2. Download the latest Python 3.x
3. **IMPORTANT:** Check the box that says "Add Python to PATH" during installation
4. Open a new Command Prompt and verify: `python --version`

---

## Step 2: Get Your API Keys

### Anthropic API Key
1. Go to https://console.anthropic.com/
2. Sign up or log in
3. Go to API Keys → Create Key
4. Copy the key (starts with `sk-ant-`)

### GitHub PAT (you already have this)
Use the same PAT you used earlier. If it's expired, create a new one:
1. Go to https://github.com/settings/tokens
2. Generate new token (fine-grained)
3. Select the `Alchemy-Escape-Rooms-Inc` organization
4. Grant "Contents" read/write permission
5. Copy the token

---

## Step 3: Configure the Script

1. Navigate to the `scripts` folder in the Grimoire repo
2. Copy `.env.example` to `.env`
3. Edit `.env` and fill in your keys:

```
ANTHROPIC_API_KEY=sk-ant-api03-your-actual-key-here
GITHUB_PAT=github_pat_your-actual-token-here
CLAUDE_MODEL=claude-sonnet-4-5-20250929
```

**NEVER commit the `.env` file to GitHub** — it contains your secrets.

---

## Step 4: Test It

Open Command Prompt and run:

```
cd C:\Users\joshu\Repos\Alchemy-Escape-Rooms-Inc\Alchemy-Grimoire\scripts
run_grimoire_update.bat --dry-run
```

The `--dry-run` flag generates the docs but doesn't push to GitHub, so you can review them first.

---

## Step 5: Set Up Windows Task Scheduler

1. Press `Win + R`, type `taskschd.msc`, press Enter
2. Click **"Create Basic Task..."** in the right panel
3. Fill in:
   - **Name:** `Alchemy Grimoire Update`
   - **Description:** `Daily regeneration of the Alchemy Grimoire documentation`
4. **Trigger:** Select "Daily"
   - Start time: `6:00:00 AM`
   - Recur every: `1` days
5. **Action:** Select "Start a program"
   - **Program/script:** `C:\Users\joshu\Repos\Alchemy-Escape-Rooms-Inc\Alchemy-Grimoire\scripts\run_grimoire_update.bat`
   - **Start in:** `C:\Users\joshu\Repos\Alchemy-Escape-Rooms-Inc\Alchemy-Grimoire\scripts`
6. Check **"Open the Properties dialog..."** before finishing
7. In Properties:
   - Check **"Run whether user is logged on or not"**
   - Check **"Run with highest privileges"**
   - Under Conditions: Uncheck "Start only if computer is on AC power" (if you want it to run on battery too)
   - Under Settings: Check "If the task fails, restart every 5 minutes" (up to 3 times)

---

## Running Manually

You can run the script anytime from Command Prompt:

```
cd C:\Users\joshu\Repos\Alchemy-Escape-Rooms-Inc\Alchemy-Grimoire\scripts

REM Full regeneration + push to GitHub
run_grimoire_update.bat

REM Just scan repos, don't regenerate docs
run_grimoire_update.bat --scan-only

REM Generate docs but don't push (preview mode)
run_grimoire_update.bat --dry-run

REM Use Opus for deeper analysis (costs more)
run_grimoire_update.bat --model claude-opus-4-5-20251101
```

---

## Checking the Log

The batch file logs success/failure to `grimoire_log.txt` in the scripts folder:

```
type C:\Users\joshu\Repos\Alchemy-Escape-Rooms-Inc\Alchemy-Grimoire\scripts\grimoire_log.txt
```

---

## Troubleshooting

**"Python not found"**
→ Reinstall Python and make sure "Add to PATH" is checked. Open a NEW Command Prompt after installing.

**"ANTHROPIC_API_KEY not set"**
→ Make sure your `.env` file exists in the scripts folder and has the correct key.

**"Failed to clone [repo]"**
→ Your GitHub PAT may have expired. Generate a new one and update `.env`.

**"Push failed"**
→ Your GitHub PAT needs "Contents" write permission on the Alchemy-Grimoire repo.

**Script runs but docs are low quality**
→ Try using `--model claude-opus-4-5-20251101` for deeper analysis (costs ~$2-3 per run instead of ~$0.50).

---

## Cost Estimate

| Model | Cost per Run | Monthly (daily) |
|-------|-------------|-----------------|
| Claude Sonnet | ~$0.50-1.00 | ~$15-30/month |
| Claude Opus | ~$2.00-3.00 | ~$60-90/month |

Most of the cost comes from sending source code to the API. The script only sends the main source files (not libraries or build artifacts) to keep costs down.
