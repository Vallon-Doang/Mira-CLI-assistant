# firewalld

## Allow HTTP through the firewall
---
os: linux
keywords: firewalld, firewall, http, allow, service, web, port
aliases: allow http, open http, permit http, http firewall
direct: true
---
```bash
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --reload
```

Verify:

```bash
sudo firewall-cmd --list-services
```

Warning: this exposes the HTTP port to the network. Only allow services you intend to serve.

## Allow HTTPS through the firewall
---
os: linux
keywords: firewalld, firewall, https, allow, service, tls, ssl
aliases: allow https, open https, https firewall
direct: true
---
```bash
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

## Open a TCP or UDP port
---
os: linux
keywords: firewalld, firewall, open, port, tcp, udp, allow
aliases: open port, allow port, firewall port
direct: true
---
```bash
sudo firewall-cmd --permanent --add-port=8080/tcp
sudo firewall-cmd --reload
```

Use `8080/udp` for UDP. Verify with `sudo firewall-cmd --list-ports`.

Warning: opening a port exposes it to the active zone. Prefer a named service when one exists.

## List firewall rules
---
os: linux
keywords: firewalld, firewall, list, rules, show, zones, ports
aliases: list firewall rules, show firewall, firewall-cmd list
direct: true
---
```bash
sudo firewall-cmd --list-all
```

This shows the active zone, services, ports, and rich rules.

## Reload the firewall
---
os: linux
keywords: firewalld, firewall, reload, apply, changes
aliases: reload firewall, apply firewall changes
direct: true
---
```bash
sudo firewall-cmd --reload
```

Runtime-only changes are lost on reload; use `--permanent` for changes that must survive.

## Check firewalld status
---
os: linux
keywords: firewalld, firewall, status, running, state, service
aliases: firewall status, is firewall running, firewalld status
direct: true
---
```bash
systemctl status firewalld
firewall-cmd --state
```

`running` means the daemon is active.

## Remove a service or port
---
os: linux
keywords: firewalld, firewall, remove, close, service, port, block
aliases: close port, remove firewall rule, block port
direct: true
---
```bash
sudo firewall-cmd --permanent --remove-service=http
sudo firewall-cmd --permanent --remove-port=8080/tcp
sudo firewall-cmd --reload
```

Warning: this can cut off access you still need, including remote SSH. Keep an existing session open until you verify the new rule.

## Inspect firewall zones
---
os: linux
keywords: firewalld, firewall, zone, zones, active, interface
aliases: firewall zones, active zone, list zones
direct: false
---
```bash
sudo firewall-cmd --get-active-zones
sudo firewall-cmd --zone=public --list-all
```

The default zone is usually `public`; the active zone depends on the interface.
