# systemd

## Service status
---
os: linux
keywords: status, service, systemctl, running, failed, active
aliases: service status, check service, systemctl status
direct: true
---
```bash
systemctl status NAME
```

The service name usually ends in `.service`; the suffix can be omitted.

## Restart a service
---
os: linux
keywords: restart, service, systemctl, reload
aliases: restart service, systemctl restart
direct: true
---
```bash
sudo systemctl restart NAME
```

Reload instead if the service supports it and you only changed its configuration:

```bash
sudo systemctl reload NAME
```

## Start or stop a service
---
os: linux
keywords: start, stop, service, systemctl
aliases: start service, stop service, systemctl start, systemctl stop
direct: true
---
```bash
sudo systemctl start NAME
sudo systemctl stop NAME
```

## Enable a service at boot
---
os: linux
keywords: enable, disable, boot, startup, service, systemctl
aliases: enable service, start at boot, systemctl enable
direct: true
---
```bash
sudo systemctl enable --now NAME
```

Use `disable` instead of `enable` to stop it starting at boot.

## List failed units
---
os: linux
keywords: failed, failure, units, systemd, systemctl, errors
aliases: failed services, list failed units, systemctl failed
direct: true
---
```bash
systemctl --failed
```

Then inspect a failed unit with `systemctl status NAME` and `journalctl -xeu NAME`.

## View service logs
---
os: linux
keywords: logs, journalctl, journal, service, systemd, log, errors
aliases: service logs, view logs, journalctl service, systemd logs, inspect systemd logs
direct: true
---
```bash
journalctl -u NAME -n 100 --no-pager
```

Add `-b` for the current boot, or `--since "1 hour ago"`.

## Follow logs live
---
os: linux
keywords: follow, logs, journalctl, live, tail, stream
aliases: follow logs, live logs, journalctl follow
direct: true
---
```bash
journalctl -u NAME -f
```

Press `Ctrl+C` to stop following.

## Diagnose a failed service
---
os: linux
keywords: failed, failure, why, service, diagnose, systemd, troubleshoot
aliases: why service failed, service failure, debug service
direct: true
---
```bash
systemctl status NAME
journalctl -xeu NAME --no-pager
```

Read the first error in the journal output; it is usually the root cause. Do not guess before checking the logs.

## Reload systemd units
---
os: linux
keywords: daemon-reload, reload, units, systemd, service, changed
aliases: reload systemd, daemon reload, systemctl daemon-reload
direct: true
---
```bash
sudo systemctl daemon-reload
```

Run this after creating or editing a unit file in `/etc/systemd/system/`.

## Find a service unit file
---
os: linux
keywords: unit, file, service, location, path, systemctl, cat
aliases: service file, unit file, where is service file
direct: true
---
```bash
systemctl cat NAME
```

System-wide units live in `/etc/systemd/system/` and `/usr/lib/systemd/system/`.
