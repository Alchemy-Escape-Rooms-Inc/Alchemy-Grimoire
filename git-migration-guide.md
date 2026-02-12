# Git Migration Guide: Moving Off OneDrive

## The Problem: Why OneDrive + Git Don't Mix

You're currently storing git repositories inside OneDrive at `C:\Users\joshu\OneDrive\`. This causes problems because:

### How OneDrive Breaks Git

**OneDrive thinks .git is just another folder to sync.**

When you use git and OneDrive at the same time:
- Git creates thousands of tiny files inside `.git/` (index, objects, logs, etc.)
- OneDrive sees these files and tries to sync them **while git is still using them**
- If OneDrive syncs a file that git is currently reading, the file gets corrupted
- Git's internal tracking files (called the "index") get out of sync with reality

**OneDrive creates conflict copies.**
- If you edit a file on two machines at once (your main PC + the escape room workstation), OneDrive creates copies like:
  - `main.cpp` (your version)
  - `main.cpp - Copy.cpp` (the other machine's version)
- Git doesn't understand these conflict copies—it sees them as new, untracked files
- Your git repository becomes polluted with phantom files

**OneDrive sync delays block git operations.**
- When you run `git add .` or `git commit`, git locks files
- OneDrive might hold those file locks for 100-500ms (syncing to the cloud)
- This causes random failures: `"error: unable to write object to file..."`
- It happens unpredictably—sometimes it works, sometimes it doesn't

**The .git folder grows large.**
- Every commit adds objects to `.git/objects/`
- OneDrive now has to sync thousands of new tiny files
- Your entire OneDrive slows down (not just your git repos)
- You hit OneDrive quota limits faster

**Bottom line**: OneDrive treats git's internal database like regular documents. But `.git` is a **database**, not a folder of documents. Two systems can't sync a database simultaneously without corrupting it.

---

## Recommended New Folder Structure

**Create a new folder hierarchy on your C: drive (NOT in OneDrive):**

```
C:\Users\joshu\Repos\                         ← ROOT (NOT in OneDrive)
  ├── Alchemy-Escape-Rooms-Inc\              ← Organization account repos
  │   ├── New-Cannons\
  │   ├── Compass\
  │   ├── CabinDoor\
  │   ├── Cannon1\
  │   ├── Cannon2\
  │   ├── RoseCompass\
  │   ├── ShipMotion1\
  │   ├── ShipMotion2\
  │   ├── ShipMotion3\
  │   ├── BarrelPiston\
  │   ├── JungleDoor\
  │   ├── JungleMotion1\
  │   ├── JungleMotion2\
  │   ├── JungleMotion3\
  │   ├── Driftwood\
  │   ├── SeaShells\
  │   ├── CoveSlidingDoor\
  │   ├── WaterFountain\
  │   ├── SunDial\
  │   ├── RuinsWallPanel\
  │   ├── MonkeyTombEntrance\
  │   ├── TridentCabinet\
  │   ├── MagicMirror2\
  │   ├── StarTable\
  │   ├── TridentAltar\
  │   ├── Hieroglyphics\
  │   ├── WatchTower\
  │   └── ... (all 27 Alchemy-Escape-Rooms-Inc repos)
  │
  └── AlchemyEscapeRooms\                     ← Legacy account repos
      ├── CabinDoor_S3\
      ├── ... (4 repos from old account)
```

**Why this structure:**
- Everything in `C:\Users\joshu\Repos\` (completely outside OneDrive)
- Organized by GitHub organization
- Easy to find any repo quickly
- No sync conflicts ever

---

## Step-by-Step Migration Plan

### Phase 1: Prepare (Take 5 minutes)

**1.1 Create the new folder structure**
```bash
# Windows PowerShell or CMD
mkdir C:\Users\joshu\Repos\Alchemy-Escape-Rooms-Inc
mkdir C:\Users\joshu\Repos\AlchemyEscapeRooms
```

### Phase 2: Verify No Uncommitted Work (Take 10-15 minutes)

**2.1 Check for uncommitted changes in each OneDrive repo**

For each of your current OneDrive repositories:
```bash
cd "C:\Users\joshu\OneDrive\path\to\repo"
git status
```

**Expected output**:
```
On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean
```

**If you see changes:**
- Commit them: `git add . && git commit -m "message"`
- Or discard them: `git restore .` (WARNING: deletes unsaved work)

**2.2 Check for unpushed commits**
```bash
git log --oneline --graph origin/main..HEAD
```

If this shows any commits, push them:
```bash
git push origin main
```

**Do this for all 31 repos before moving forward.**

### Phase 3: Clone Fresh from GitHub (Take 20-30 minutes)

**3.1 Clone Alchemy-Escape-Rooms-Inc repos**

Open PowerShell and run:
```bash
cd C:\Users\joshu\Repos\Alchemy-Escape-Rooms-Inc

# Clone all 27 organization repos
git clone https://github.com/Alchemy-Escape-Rooms-Inc/New-Cannons.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/Compass.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/CabinDoor.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/Cannon1.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/Cannon2.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/RoseCompass.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/ShipMotion1.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/ShipMotion2.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/ShipMotion3.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/BarrelPiston.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/JungleDoor.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/JungleMotion1.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/JungleMotion2.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/JungleMotion3.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/Driftwood.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/SeaShells.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/CoveSlidingDoor.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/WaterFountain.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/SunDial.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/RuinsWallPanel.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/MonkeyTombEntrance.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/TridentCabinet.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/MagicMirror2.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/StarTable.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/TridentAltar.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/Hieroglyphics.git
git clone https://github.com/Alchemy-Escape-Rooms-Inc/WatchTower.git
```

**3.2 Clone AlchemyEscapeRooms repos**

```bash
cd C:\Users\joshu\Repos\AlchemyEscapeRooms

git clone https://github.com/AlchemyEscapeRooms/CabinDoor_S3.git
# ... (clone your 4 legacy repos here)
```

### Phase 4: Verify Clones Match GitHub (Take 10 minutes)

**4.1 Spot-check a few clones**

For 3-4 random repos:
```bash
cd C:\Users\joshu\Repos\Alchemy-Escape-Rooms-Inc\Compass

# Check the git log matches GitHub
git log --oneline -n 5

# Check status is clean
git status

# Check remote is correct
git remote -v
```

Expected output:
```
origin  https://github.com/Alchemy-Escape-Rooms-Inc/Compass.git (fetch)
origin  https://github.com/Alchemy-Escape-Rooms-Inc/Compass.git (push)

On branch main
Your branch is up to date with 'origin/main'.
nothing to commit, working tree clean
```

If anything looks wrong, **stop and fix it before continuing**.

### Phase 5: Update Tools (Take 10 minutes)

**5.1 Update IDE / PlatformIO configurations**

If you use PlatformIO or Arduino IDE:
- Old path: `C:\Users\joshu\OneDrive\...\Compass\src\main.cpp`
- New path: `C:\Users\joshu\Repos\Alchemy-Escape-Rooms-Inc\Compass\src\main.cpp`

In VS Code:
- Update any workspace files (`.code-workspace`)
- Update PlatformIO project folders
- Update Arduino IDE sketchbook location if needed

**5.2 Update any scripts or shortcuts**
- Batch files that cd into repos
- Desktop shortcuts to repo folders
- Build scripts that reference old paths

### Phase 6: Exclude from OneDrive (Take 5 minutes)

**CRITICAL: This prevents OneDrive from trying to sync your new Repos folder.**

**On Windows 10/11:**

1. Right-click `C:\Users\joshu\Repos` folder
2. Select **Properties**
3. Click **Advanced** (you may need to scroll down)
4. Check the box: **"This folder is not synced"** (or similar wording)
5. Click **Apply** → **OK**

**Alternative method (if above doesn't work):**
1. Open OneDrive settings (system tray icon → gear → Settings)
2. Go to **Sync and backup** → **Manage backup**
3. Uncheck **Documents** folder if `Repos` is inside it
4. Or: Click **"Choose folders"** and uncheck the Repos folder

**Verify it worked:**
- Right-click `C:\Users\joshu\Repos`
- You should see a circle with a line through it (not synced indicator)
- NOT a green checkmark (that means it IS syncing)

**Do NOT use "Free up space"** — that's not the same as excluding from sync.

### Phase 7: Clean Up Old Locations (Take 5 minutes)

Once you've verified everything works for 1-2 days:

**Option A: Delete old OneDrive copies** (safest)
- Go to `C:\Users\joshu\OneDrive\`
- Delete the old repo folders
- Alternatively, just leave them there (they won't sync anymore)

**Option B: Archive old copies**
- Move to `C:\Users\joshu\OneDrive\OLD_REPOS_ARCHIVE\`
- Keep as backup for 30 days, then delete

**Never just rename or leave them**—you'll forget they're there and create confusion later.

---

## Git Tool Recommendation: VS Code with Built-in Git

### Why NOT GitHub Desktop or CLI-only?

**GitHub Desktop**:
- Extra application to switch to
- Slower than integrated tools
- Duplicate window management

**CLI-only**:
- Fast and powerful
- But you don't need it for 95% of daily work
- Harder to learn for beginners

**VS Code with Git Integration**: **RECOMMENDED**

### Why VS Code?

1. **You're already using it**
   - PlatformIO extension runs in VS Code
   - ESP32 code editing in VS Code
   - One tool instead of three

2. **Excellent built-in git GUI**
   - Left sidebar: Source Control tab shows all changed files
   - Click a file to see diffs visually (red/green highlighting)
   - Stage individual files or hunks with one click
   - Commit message box right there
   - Push/pull buttons obvious and always visible

3. **PlatformIO integration**
   - Write code → See changes in Source Control → Stage → Commit → Push
   - Then upload to hardware
   - All in one window

4. **Status at a glance**
   - Number of changes shown on Source Control icon
   - Branch name shown at bottom
   - "Ahead/Behind" indicator shows if you need to push or pull
   - Merge conflicts highlighted visually

### Basic VS Code Git Workflow

**1. Open your repo folder**
```bash
code C:\Users\joshu\Repos\Alchemy-Escape-Rooms-Inc\Compass
```

**2. Make code changes**
- Edit files normally
- Unsaved files show white dot on tab

**3. View changes**
- Click Source Control icon (left sidebar)
- See all changed files listed
- Click a file to see diff (red = removed, green = added)

**4. Stage changes**
- Click the "+" button next to a file to stage it
- Or right-click → Stage

**5. Write commit message**
- In the commit message box at top, type: `"fix: Compass MQTT topic mismatch"`
- Press Ctrl+Enter to commit (or click Commit button)

**6. Push to GitHub**
- At bottom: click the cloud icon or "Sync" button
- Or use keyboard: Ctrl+Shift+P → "Git: Push"

**7. When working on escape room workstation**
- Before editing: Ctrl+Shift+P → "Git: Pull"
- After testing: Stage → Commit → Push
- Back at main machine: Pull before editing

### Essential git Commands to Know (Terminal)

You still need to know these for when VS Code acts weird:

```bash
# Check status
git status

# See differences
git diff

# Pull latest from GitHub
git pull

# Push to GitHub
git push

# See commit history
git log --oneline -n 10

# If you accidentally committed, undo last commit (but keep changes)
git reset --soft HEAD~1
```

Learn these 5 commands. Don't need much else day-to-day.

---

## Standard .gitignore Template

Create a `.gitignore` file in the root of each repo with this content:

```
# Build artifacts
.pio/
build/
*.o
*.elf
*.bin
*.hex

# IDE files
.vscode/
.idea/
*.code-workspace

# OS files
.DS_Store
Thumbs.db
desktop.ini

# Credentials (NEVER commit these)
.env
.env.*
*.key
*.pem
credentials.json
secrets.json

# Arduino IDE
*.ino.globals.h

# PlatformIO
.pio/
lib_deps/

# Logs
*.log

# OneDrive conflict files (in case old copies ever appear)
*- Copy*
*-conflict-*
```

**How to add it:**
1. Create file: `C:\Users\joshu\Repos\Alchemy-Escape-Rooms-Inc\Compass\.gitignore`
2. Paste the content above
3. Stage and commit: `git add .gitignore && git commit -m "add: .gitignore for Arduino/ESP32 projects"`
4. Push: `git push origin main`

**Do this for all 31 repos.**

---

## Migration Checklist

Use this checklist to track your progress:

```
PREPARATION
[ ] Create C:\Users\joshu\Repos\Alchemy-Escape-Rooms-Inc\ folder
[ ] Create C:\Users\joshu\Repos\AlchemyEscapeRooms\ folder

VERIFICATION (Do for all 31 repos)
[ ] Repo 1: git status clean? git log pushed?
[ ] Repo 2: ...
... (continue for all)

CLONING
[ ] Cloned all 27 Alchemy-Escape-Rooms-Inc repos
[ ] Cloned all 4 AlchemyEscapeRooms repos

VERIFICATION (Spot check 5 repos)
[ ] Repo A: git log matches? Remote correct?
[ ] Repo B: ...
[ ] Repo C: ...
[ ] Repo D: ...
[ ] Repo E: ...

TOOLS UPDATE
[ ] Updated PlatformIO project paths
[ ] Updated any IDE shortcuts/configs
[ ] Updated any build scripts

ONEDRIVE EXCLUSION
[ ] Excluded C:\Users\joshu\Repos\ from OneDrive sync
[ ] Verified it's not syncing (circle icon, not checkmark)

TESTING (Work normally for 1-2 days)
[ ] Edited code at main machine, committed, pushed
[ ] Pulled on escape room workstation
[ ] Edited on workstation, committed, pushed
[ ] Pulled at main machine—changes show up
[ ] No sync conflicts, no "Copy" files

CLEANUP
[ ] Deleted old OneDrive repo copies
[ ] Saved this guide for future reference

ALL DONE!
```

---

## Troubleshooting Migration

### "Could not find repository"
- Make sure you're in the right folder: `cd C:\Users\joshu\Repos\Alchemy-Escape-Rooms-Inc\Compass`
- Make sure `.git` folder exists (it's hidden, show hidden files)

### "Authentication failed"
- GitHub personal access token expired or invalid
- VS Code will prompt to authenticate; follow the GitHub login flow
- Or use: `git config --global credential.helper wincred` to use Windows credential manager

### "Files still appearing in OneDrive"
- OneDrive might be syncing old copies from before exclusion
- Wait 5-10 minutes for sync to complete
- Right-click folder → OneDrive → Free up space (this won't work; ignore it)
- Settings → Sync and backup → Manage backup → uncheck the folder explicitly

### Merge conflicts when pulling
- This happens when you edit the same file on two machines
- VS Code shows conflict markers (<<<, ===, >>>)
- Click the file → "Accept Current Change" or "Accept Incoming Change"
- Commit the merge

### "Fatal: the index file is corrupt"
- This is the OneDrive + Git corruption we're trying to avoid
- If it happens after migration: delete repo and clone fresh from GitHub
- If it still happens: you might still have a OneDrive copy being synced; verify exclusion

---

## Going Forward: Daily Workflow

After migration, your workflow is simple:

**At your main machine:**
1. Start work: `git pull` (get latest)
2. Make changes, test code
3. Stage and commit in VS Code
4. Push: Ctrl+Shift+P → "Git: Push" or click cloud icon

**At escape room workstation:**
1. Arrive: `git pull` (get latest from GitHub)
2. Edit code, test on hardware
3. Commit and push before leaving
4. At main machine: `git pull` before editing

**Golden rule**: Pull before you edit, push before you leave.

No more OneDrive conflicts. No more "Copy" files. No more .git corruption.

Just git doing what it does best.
