# Troubleshooting

## Check NVIDIA GPU usage
---
os: linux
keywords: gpu, nvidia, nvidia-smi, vram, graphics, usage, memory
aliases: gpu usage, nvidia gpu, check gpu, gpu memory
direct: true
---
```bash
nvidia-smi
```

Live view, refreshed every second:

```bash
watch -n 1 nvidia-smi
```

The `Memory-Usage` row shows VRAM used and total. The `Processes` section shows which programs hold GPU memory.

## Check RAM usage
---
os: linux
keywords: ram, memory, usage, free, mem, available
aliases: ram usage, memory usage, check ram, check memory
direct: true
---
```bash
free -h
```

Top memory consumers:

```bash
ps aux --sort=-%mem | head
```

## Check CPU usage
---
os: linux
keywords: cpu, usage, top, htop, load, processor
aliases: cpu usage, check cpu, processor usage
direct: true
---
```bash
top
```

Or, if installed:

```bash
htop
```

Press `q` to quit.

## Check system load
---
os: linux
keywords: load, load average, uptime, cpu, busy
aliases: load average, system load, uptime
direct: true
---
```bash
uptime
```

Load averages are for 1, 5, and 15 minutes. Compare them with the number of CPU cores.

## Find a running process
---
os: linux
keywords: process, running, find, pgrep, ps, pid
aliases: find process, running process, pgrep
direct: true
---
```bash
pgrep -a NAME
```

Or:

```bash
ps aux | grep NAME
```

## Diagnose a full disk
---
os: linux
keywords: disk, full, space, df, du, large, cleanup
aliases: disk full, no space left, free space, cleanup disk
direct: true
---
```bash
df -h
sudo du -xhd1 / | sort -h
```

For journal space:

```bash
journalctl --disk-usage
sudo journalctl --vacuum-size=500M
```

Warning: deleting files you do not understand can break the system. Inspect first, then remove only known caches or logs.

## Read boot logs
---
os: linux
keywords: boot, logs, journalctl, startup, previous, errors
aliases: boot logs, startup logs, journalctl boot
direct: true
---
```bash
journalctl -b --no-pager
```

Previous boot:

```bash
journalctl -b -1 --no-pager
```

## Read kernel messages
---
os: linux
keywords: kernel, dmesg, messages, hardware, errors, journalctl
aliases: kernel messages, dmesg, kernel log
direct: true
---
```bash
sudo dmesg --level=err,warn
```

Or:

```bash
journalctl -k --no-pager
```

## Find failed systemd services
---
os: linux
keywords: failed, service, failure, systemd, status, journalctl, diagnose
aliases: failed service, service failure, why service failed
direct: true
---
```bash
systemctl --failed
systemctl status NAME
journalctl -xeu NAME --no-pager
```

Start with the first error in the journal rather than guessing.

## Troubleshoot network connectivity
---
os: linux
keywords: network, connectivity, ping, dns, ip, route, troubleshoot
aliases: network troubleshooting, no internet, network problem
direct: false
---
```bash
ip -brief address
ip route
ping -c 4 1.1.1.1
resolvectl query example.com
```

If the IP responds but DNS does not resolve, check `/etc/resolv.conf` and `resolvectl status`.

## Check hardware temperatures
---
os: linux
keywords: temperature, sensors, thermal, heat, fan, cpu
aliases: check temperature, cpu temperature, sensors
direct: true
---
```bash
sensors
```

If the command is missing, install `lm_sensors` with `sudo dnf install lm_sensors`.

## Check for an out-of-memory kill
---
os: linux
keywords: oom, out of memory, killed, memory, kernel, process
aliases: oom killer, oom kill, check oom kill, out of memory, process killed
direct: true
---
```bash
journalctl -k --no-pager | grep -i -E 'out of memory|oom'
```

The kernel log names the process that was killed and the memory state at the time.

## Check open file limits
---
os: linux
keywords: file descriptors, ulimit, limits, open files, too many
aliases: file descriptor limit, ulimit, too many open files
direct: false
---
```bash
ulimit -n
```

System-wide limits:

```bash
systemctl show -p LimitNOFILE
```
