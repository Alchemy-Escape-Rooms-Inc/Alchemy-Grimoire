# Projectors — Reassign Outputs & Debugging
## The Alchemy Grimoire — Operations Manual

---

## Overview

This document covers how to reset and reassign projector display outputs on the escape room PC. Use this any time projectors are not detected correctly, showing wrong outputs, or assigned to the wrong displays after a reboot or hardware change.

---

## When to Run This Procedure

- Projectors not detected by Windows after a reboot
- Wrong projector-to-display output assignments
- Scrambled display arrangement after connecting/moving hardware
- After physically moving projectors to different ports
- Before show opening if displays behave unexpectedly

---

## Full Reset Procedure

### Step 1 — Open Registry Editor as Admin
- Press `Win + R` → type `regedit` → right-click → **Run as administrator**

---

### Step 2 — Delete Subfolders in These Registry Locations

**Location 1:**
```
HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Enum\DISPLAY
```
- Navigate to this path
- Delete all **subfolders inside** DISPLAY (e.g. DEL4048, GSV0808..., BNQ, BOE, BXL, etc.)
- **Do NOT delete the DISPLAY folder itself**

**Location 2:**
```
HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\GraphicsDrivers\Configuration
```
- Delete all **subfolders inside** Configuration
- **Do NOT delete the Configuration folder itself**

**Location 3 (recommended):**
```
HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\GraphicsDrivers\Connectivity
```
- Delete all **subfolders inside** Connectivity
- **Do NOT delete the Connectivity folder itself**

---

### Step 3 — If You Get "Error Deleting Key" (Permissions Fix)

1. Right-click the stubborn key → **Permissions** → **Advanced**
2. Click **Change** next to Owner
3. Type `Administrators` → **Check Names** → **OK**
4. Check **"Replace owner on subcontainers and objects"**
5. Click **Apply**
6. Back in Permissions, select Administrators → check **Full Control**
7. Click **OK** and retry the delete

---

### Step 4 — Device Manager Cleanup

1. Open **Device Manager** (`Win + X` → Device Manager)
2. Click **View** → **Show hidden devices**
3. Expand **Monitors**
4. Right-click and **Uninstall** every entry, including grayed-out ghost monitors
5. Confirm any prompts

---

### Step 5 — Reboot

Windows will re-detect all connected projectors and monitors fresh on startup and rebuild the registry entries from scratch.

---

### Step 6 — Reassign Outputs

After reboot, re-enter your display output assignments from scratch:
- Use `Win + P` to switch display mode
- Use **Settings → Display** to set arrangement, resolution, and primary display
- Re-map any projector-specific software output assignments

---

## Why This Works

Windows stores every monitor/projector EDID and display configuration in the registry. These entries accumulate over time — every display ever connected leaves a cached entry. When Windows boots, it reads the old stale entries instead of detecting hardware fresh, causing wrong output assignments. Clearing all three registry locations plus ghost monitors in Device Manager gives Windows a completely clean slate to re-detect from scratch.

---

## Issue History

| Date | Issue | Resolution |
|------|-------|------------|
| Jan 2026 | Projectors not detected / wrong output assignments after reboot | Cleared DISPLAY + Configuration + Connectivity registry subfolders, removed ghost monitors in Device Manager, rebooted |
| Jan 2026 | "Error deleting key" when clearing registry | Took ownership via Permissions → Advanced → change Owner to Administrators |

---

*See also: [Debug Log](debug-log.md) — Issue #25*
