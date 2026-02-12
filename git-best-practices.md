# Git Best Practices for Hardware Development

A practical guide for your one-person, hardware-focused workflow at Alchemy Escape Rooms.

---

## How Often to Commit and Push

### Commit Frequently (Multiple Times Per Day)

**Commit whenever you have something working—even partially:**

Examples of good commit points:
- "Compass reads angle but doesn't publish MQTT yet"
- "Fixed WiFi reconnection logic"
- "Adjust sensor threshold from 150 to 180"
- "Added debug serial output for troubleshooting"
- "Remove unused Pin13 LED code"

**Why?**
- If your workstation crashes, you only lose the most recent work (not hours)
- You can see which change broke something (easier to debug with small commits)
- If you need to revert, you revert one small change, not 10 different things
- It's faster to write 5 tiny commit messages than 1 huge novel

### Push at the End of Every Work Session

**Every time you stop working, push to GitHub.**

This means:
- Before you leave the escape room workstation
- Before you close your laptop for the day
- Before you hand off to another person

**Why?**
- Your code is backed up on GitHub's servers
- If your laptop dies, gets stolen, or gets wiped, your work is safe
- Your other machine can pull and see everything you did
- GitHub is more reliable than your local laptop

### Think of Commits as Save Points in a Video Game

In a video game:
- You don't just quicksave before major boss fights
- You save frequently—after solving a puzzle, after reaching a checkpoint, before a risky move
- If you die, you reload from the last save, not from the beginning

Same with git:
- Don't wait until everything is "done" to commit
- Save after each meaningful chunk of work
- If you need to revert, you have many save points to choose from

---

## Do You Need Branches?

### Short Answer: No

At your scale (one person, hardware projects), **working on main/master is fine.**

**Why branches normally exist:**
- Multiple team members working on different features simultaneously
- One person wants to try a risky change without affecting others
- You need to maintain multiple versions of the code

**You don't have any of these problems.**

### When You MIGHT Use a Branch

**Scenario: You want to try something risky**

Example: You want to completely rewrite the WiFi connection code, but the current code works and you're not sure the rewrite will be better.

**Make a branch:**
```bash
git checkout -b experiment/new-wifi

# Work on the new code, commit frequently
git commit -m "refactor: new WiFi connection library"
git commit -m "feat: add WiFi auto-reconnect"

# Test it thoroughly
```

**If it works:**
```bash
git checkout main
git merge experiment/new-wifi
git push origin main
# Delete the branch
git branch -d experiment/new-wifi
```

**If it doesn't work:**
```bash
git checkout main
# The new-wifi branch just sits there, unused
# Delete it later: git branch -d experiment/new-wifi
```

**Don't overthink it.** Use branches when you're genuinely unsure about a big change.

### Branch Naming Convention

If you do use branches, use names like:
- `experiment/new-wifi` — trying something new
- `bugfix/mqtt-disconnect` — fixing a known bug
- `feature/heartbeat` — adding a new feature
- `cleanup/remove-debug` — code cleanup

Not: `test`, `temp`, `asdf`, `new`, `bob-testing`

---

## How to Verify Local Matches Remote

Three commands to know:

### Command 1: Fetch
```bash
git fetch
```
Downloads all the latest commits from GitHub **without changing your code**.

This is safe. It just updates what you see about the remote.

### Command 2: Status
```bash
git status
```

**Expected output when everything is synced:**
```
On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean
```

**If you see:**
```
Your branch is ahead of 'origin/main' by 2 commits
```
This means you have work that hasn't been pushed yet. Run `git push origin main`.

**If you see:**
```
Your branch is behind 'origin/main' by 3 commits
```
This means there are new commits on GitHub you don't have locally. Run `git pull`.

**If you see:**
```
nothing to commit, working tree clean
```
Perfect—local matches remote.

### Command 3: Diff
```bash
git diff origin/main
```

Shows the exact differences between your local code and what's on GitHub.

Red lines (-) = you deleted these
Green lines (+) = you added these

Use this if you want to see **what** changed, not just whether something changed.

---

## What to Do When Things Get Out of Sync

### Simple Case: You Edited On Two Machines

**Scenario:**
- You edited Compass code on your main machine
- You also edited Compass code on the escape room workstation
- Now you're back at main machine and it's out of sync

**How to fix:**
```bash
git pull
```

That's it. If you didn't edit the **same lines** in the same file, git merges automatically.

If you did edit the same lines, git asks you to manually pick which version to keep (see "Conflict" section below).

Then:
```bash
git push origin main
```

### Conflict: You Edited Same File in Two Places

**Scenario:**
- On main machine: you changed line 15 in Compass.cpp
- On workstation: you ALSO changed line 15 in Compass.cpp differently
- When you `git pull`, you get a conflict

**What git shows you:**
```cpp
<<<<<<< HEAD
    // Your version (what's on this machine)
    angle = readSensor() - 5;
=======
    // Incoming version (from GitHub)
    angle = readSensor() - 10;
>>>>>>> origin/main
```

**In VS Code:**
- Click the conflict line
- You'll see buttons: "Accept Current Change" or "Accept Incoming Change" or "Accept Both Changes"
- Click the one you want
- Save the file
- Commit: `git add . && git commit -m "merge: resolved Compass sensor offset conflict"`

**How to avoid conflicts:**
- Keep the "Pull before you edit, push before you leave" rule
- If you're editing the same file on two machines, designate which machine edits what

### Nuclear Option: Everything Is Broken

**Scenario:**
- Something is seriously wrong with your git history
- You can't figure out what's corrupted
- You just want to start fresh

**Safe solution:**
```bash
# Save any local changes you care about to a temp folder
cp -r C:\Users\joshu\Repos\Alchemy-Escape-Rooms-Inc\Compass C:\Users\joshu\Desktop\Compass_backup

# Delete the broken repo
rm -r C:\Users\joshu\Repos\Alchemy-Escape-Rooms-Inc\Compass

# Clone fresh from GitHub
cd C:\Users\joshu\Repos\Alchemy-Escape-Rooms-Inc\
git clone https://github.com/Alchemy-Escape-Rooms-Inc/Compass.git

# If you had unsaved local changes, manually copy them from backup
# And git add/commit them in the fresh clone
```

**This is always safe** because GitHub has the real source of truth.

### OneDrive Corrupted .git Folder

**Scenario:**
- You see: `fatal: the index file is corrupt`
- This happened because OneDrive was syncing while git used the file

**Solution:**
1. This is why we moved off OneDrive (see git-migration-guide.md)
2. Don't try to fix the .git folder—it's a database, not human-editable
3. Clone fresh from GitHub (see Nuclear Option above)
4. Make sure C:\Users\joshu\Repos\ is excluded from OneDrive sync

---

## Two-Machine Workflow (Main Machine + Escape Room Workstation)

This is your specific situation. Here's the routine:

### Before Editing on Either Machine

**Always do this first:**
```bash
cd C:\Users\joshu\Repos\Alchemy-Escape-Rooms-Inc\Compass
git pull
```

This downloads any changes from the other machine. Only takes 1 second.

### After Editing on a Machine

**When you're done for the session:**
```bash
# See what changed
git status

# Stage all changes
git add .

# Commit with a good message
git commit -m "fix: Compass angle calculation off by 5 degrees"

# Push to GitHub
git push origin main
```

### The Golden Rule: Pull Before Edit, Push Before Leave

**Main Machine:**
1. Arrive at desk: `git pull Compass`
2. Edit code, test
3. Before closing: `git push`

**Escape Room Workstation:**
1. Arrive at workstation: `git pull Compass`
2. Edit code, test on hardware
3. Before leaving: `git push`

**Back at Main Machine:**
1. Before editing: `git pull` (to get the workstation's changes)
2. Edit and test
3. Before leaving: `git push`

**This prevents conflicts because you never edit the same file at the same time on two machines.**

---

## Commit Message Format

Use this format. It'll help you find things later and makes your git log readable.

### Format
```
type: short description (under 50 chars)

Optional longer explanation if needed.
Wrap at 72 characters.
```

### Types

```
fix:      Bug fix ("fix: Compass MQTT topic mismatch")
feat:     New feature ("feat: Add PING/PONG to BarrelPiston")
wiring:   Hardware/wiring change ("wiring: Move relay to GPIO 16")
config:   Configuration change ("config: Update broker IP to 10.1.10.115")
docs:     Documentation ("docs: Add README with pin assignments")
test:     Testing code ("test: Add relay cycling diagnostic")
cleanup:  Code cleanup ("cleanup: Remove commented-out debug code")
refactor: Code rewrite ("refactor: Simplify WiFi connection logic")
perf:     Performance improvement ("perf: Reduce MQTT publish latency")
```

### Examples of Good Commit Messages

```
fix: BarrelPiston publishing to wrong MQTT topic

Was publishing on "BarrelPiston/status" but should be
"MermaidsTale/BarrelPiston/status". Updated broker publish calls.

---

feat: Add 5-minute heartbeat to CabinDoor

Adds periodic status check to ensure device is still responsive.
Publishes "alive" message every 300 seconds to heartbeat topic.

---

wiring: Move LIMIT_OPEN from GPIO 8 to GPIO 9

GPIO 8 is consistently dead. Moved limit switch input to GPIO 9.
Updated pin definitions in config.h.

---

config: Change WiFi SSID from EscapeRoomNet to AlchemyGuest

Network was renamed. Updated SSID and PSK in credentials.h.

---

cleanup: Remove commented-out debug serial code
```

### Examples of BAD Commit Messages (Don't Do This)

```
updated code
- What code? What changed?

fixed bug
- Which bug? How did you fix it?

changes
- This tells me nothing.

asdf
- This is not helpful.

trying stuff
- Be more specific.

WIP
- Work in progress—but what work?

v2
- Version numbers are what git tags are for.
```

---

## Common Workflows

### Workflow 1: Fix a Bug You Just Found

```bash
# See what changed
git status

# Verify the fix is correct
git diff

# Stage the fix
git add .

# Commit
git commit -m "fix: Sensor reading off by 5 degrees"

# Push
git push origin main
```

**Time: 30 seconds**

### Workflow 2: Add a New Feature

```bash
# Make the changes
# ... edit code, test ...

# See all changes
git status

# Stage changes
git add .

# Commit
git commit -m "feat: Add timeout to sensor read

If sensor doesn't respond in 500ms, return error code.
Prevents firmware hang if sensor fails."

# Push
git push origin main
```

**Time: 1 minute**

### Workflow 3: Small Maintenance (Code Cleanup)

```bash
# Make the changes
# ... remove old code, fix formatting ...

# Stage
git add .

# Commit
git commit -m "cleanup: Remove old WiFi fallback code

Dead code path from 2023 version. Unused."

# Push
git push origin main
```

**Time: 30 seconds**

### Workflow 4: Major Rewrite (Risky, Use a Branch)

```bash
# Create a temporary branch
git checkout -b experiment/new-wifi-driver

# Make the changes
# ... big refactor ...

# Commit frequently (you're experimenting)
git commit -m "refactor: WiFi driver first pass"
git commit -m "test: WiFi connects but disconnect buggy"
git commit -m "fix: Disconnect timeout was wrong"

# Test thoroughly on hardware
# ... test, test, test ...

# If it works:
git checkout main
git merge experiment/new-wifi-driver
git push origin main

# If it fails:
# Just don't merge it. Delete the branch later.
git checkout main
```

**Time: Variable, but your experiments don't break main branch**

---

## Recovering From Mistakes

### "I committed something I didn't mean to"

**If you haven't pushed yet:**
```bash
git reset --soft HEAD~1
```

This undoes the last commit but keeps the changes staged. You can re-commit with a better message.

**If you already pushed:**
```bash
git revert HEAD
```

This creates a **new commit that undoes the old one**. The old commit stays in history (for debugging), but the code goes back.

### "I want to see what I changed in the last commit"

```bash
git show HEAD
```

Shows the last commit's changes.

### "I want to see the commit history"

```bash
git log --oneline -n 20
```

Shows the last 20 commits, one per line.

### "I deleted a file by accident"

```bash
git restore filename.cpp
```

Gets it back from git.

### "I made changes I want to discard"

```bash
git restore .
```

Throws away all local changes. **Warning: this can't be undone.**

---

## Quick Reference: Commands You'll Use Weekly

| Task | Command |
|------|---------|
| Pull latest | `git pull` |
| See what changed | `git status` |
| View differences | `git diff` |
| Stage all changes | `git add .` |
| Commit | `git commit -m "message"` |
| Push to GitHub | `git push origin main` |
| See commit history | `git log --oneline -n 10` |
| Undo local changes | `git restore .` |
| Undo last commit (not pushed) | `git reset --soft HEAD~1` |
| See last commit's changes | `git show HEAD` |

---

## Why This Approach Works For You

You have a simple setup:
- One person (you)
- One primary branch (main)
- Multiple escape room devices (27 repos)
- Two work locations (main machine + workstation)

You don't have:
- Multiple developers (so no merge conflicts between people)
- Feature flags (so you don't need branches)
- Release cycles (so you don't need version tags)
- A CI/CD pipeline (so you don't need advanced testing)

**This means:**
- Keep it simple: main branch, frequent commits, push before you leave
- Branches only for experiments (and rarely)
- No complex workflows
- If something breaks, clone fresh and start over—it's faster than debugging

---

## Summary: One Rule That Covers 90% of What You Need

**Pull before you edit. Push before you leave.**

That's it. Do that, and you'll never lose work, never have conflicts, and never be out of sync.

Everything else is just details.
