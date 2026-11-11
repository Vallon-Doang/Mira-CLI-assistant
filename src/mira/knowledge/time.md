## Set the system clock and timezone
---
os: linux
keywords: clock, time, timezone, ntp, timedatectl, date, sync
aliases: fix clock, fix the clock, wrong clock, clock is wrong, set clock, set the clock, set time, set the timezone, change timezone, change the timezone, timezone, sync time, ntp sync, time is wrong, system clock
direct: true
---
Check the current time, timezone, and NTP state:

```bash
timedatectl status
```

Set the timezone:

```bash
sudo timedatectl set-timezone REGION/CITY
```

Enable automatic network time:

```bash
sudo timedatectl set-ntp true
```

If NTP is unavailable, set the time manually after disabling NTP:

```bash
sudo timedatectl set-ntp false
sudo date -s "YYYY-MM-DD HH:MM:SS"
```

Warning: changing the clock can affect logs, certificates, and scheduled jobs.
