# The Alchemy Grimoire

**A Living Operations Manual for Alchemy Escape Rooms Inc.**
**Game: "A Mermaid's Tale" — Fort Lauderdale, Florida**
**Last Updated: February 12, 2026**

---

## What Is This?

The Alchemy Grimoire is your single source of truth for every prop, every wire, every MQTT topic, every debug issue, and every procedure in the "A Mermaid's Tale" escape room. If something breaks at 6 PM on a Friday with a group in the room, this is the document you open.

---

## Table of Contents

| # | Document | Description | Lines |
|---|----------|-------------|-------|
| 1 | [Operations Manual](operations-manual.md) | Every prop/device — hardware, pins, MQTT topics, how to reset, how to test | 1,595 |
| 2 | [Network & Infrastructure](network-infrastructure.md) | MQTT broker setup, IP addresses, ports, M3/BAM integration, protocol standard | 545 |
| 3 | [Debug Log & Known Issues](debug-log.md) | 24 documented issues (16 resolved, 8 active), troubleshooting decision trees | 1,488 |
| 4 | [System Checker Integration](system-checker-integration.md) | WatchTower dashboard — how it works, device inventory, pre-game checklist | 339 |
| 5 | [Wiring Reference](wiring-reference.md) | Pin-by-pin tables for every prop, I2C registry, relay logic, voltage levels | 482 |
| 6 | [Code Health Report](code-health-report.md) | Audit of all 31 repos — consistency, security, error handling, versions | 216 |
| 7 | [TODO & Action Items](todo.md) | Prioritized checklist: 8 critical, 15 important, 24 nice-to-have | 283 |
| 8 | [Git Migration Guide](git-migration-guide.md) | Move repos out of OneDrive, folder structure, .gitignore template | 529 |
| 9 | [Git Best Practices](git-best-practices.md) | Commit strategy, two-machine workflow, commit message format | 596 |

**Total: ~6,000 lines of documentation across 9 documents**

---

## Quick Links

### "Something Is Broken Right Now"
→ Start with the [Troubleshooting Decision Trees](debug-log.md#troubleshooting-decision-trees) in the Debug Log

### "I Need to Reset a Prop"
→ [Operations Manual](operations-manual.md) — find the prop, look at the "How to Reset" section

### "What MQTT Topic Does X Use?"
→ [Operations Manual](operations-manual.md) — every prop has an MQTT Topics table
→ [Network Infrastructure](network-infrastructure.md#alchemy-mqtt-protocol-standard) — the protocol standard

### "Is Everything Online Before a Game?"
→ [System Checker](system-checker-integration.md#pre-game-checklist) — pre-game verification procedure

### "I Need to Wire Up a New Prop"
→ [Wiring Reference](wiring-reference.md) — pin tables, I2C addresses, voltage levels

### "What Should I Fix Next?"
→ [TODO](todo.md) — prioritized from critical to nice-to-have

### "How Do I Use Git Properly?"
→ [Git Best Practices](git-best-practices.md) — commit strategy, two-machine workflow
→ [Git Migration Guide](git-migration-guide.md) — move repos out of OneDrive

---

## GitHub Repositories

| Organization | URL | Repos |
|---|---|---|
| Primary (current) | [Alchemy-Escape-Rooms-Inc](https://github.com/Alchemy-Escape-Rooms-Inc) | 27 |
| Legacy (personal) | [AlchemyEscapeRooms](https://github.com/AlchemyEscapeRooms) | 4 |
| **Total** | | **31** |

---

## How to Keep This Updated

This Grimoire is only useful if it stays current. When you:

- **Add a new prop** → Add its section to the Operations Manual, Wiring Reference, and WatchTower config
- **Fix a bug** → Add a resolution entry to the Debug Log
- **Change wiring** → Update the Wiring Reference
- **Add/change MQTT topics** → Update the Operations Manual AND Network Infrastructure
- **Create a new repo** → Update the Code Health Report

---

*Built by Claude for Clifford at Alchemy Escape Rooms Inc.*
*Generated from analysis of 31 GitHub repositories, 6,000+ lines of source code, and documented debug history.*
