# Legacy VLESS/VPN Bot

> **Legacy infrastructure project. Not part of the active portfolio showcase.**

This repository contains an older Telegram/VLESS automation project.

## Security status

A previously tracked runtime secret file was removed from the current branch and added to `.gitignore`. The exposed key material must be treated as compromised and rotated before any reuse.

Removing the file from the current branch does not by itself erase the credential from historical Git objects. A history rewrite and provider/server-side key rotation are still required for complete remediation.

## Repository policy

Runtime secrets, generated VPN keys, client configs, databases and environment files must never be committed.

```text
.env
keys.env
*.db
*.pem
client configs
runtime-generated key material
```

## Portfolio note

This repository is retained as legacy history only. Current production engineering work is represented by the larger FastAPI/PostgreSQL/Redis application repositories on this profile.
