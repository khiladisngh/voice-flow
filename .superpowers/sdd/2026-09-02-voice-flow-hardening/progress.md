# SDD ledger — plan: docs/superpowers/plans/2026-09-02-voice-flow-hardening.md
Base commit: 2036f89

## Preflight Scans & Rulings
- Task 7 PassEnvironment: Verified that WAYLAND_DISPLAY, XDG_RUNTIME_DIR, DBUS_SESSION_BUS_ADDRESS are already present in systemd user manager on Fedora Plasma 6.
- Ruling: Retain PassEnvironment= in service as defense-in-depth; prioritize entrypoint and cleanup. Cost if wrong: zero.
