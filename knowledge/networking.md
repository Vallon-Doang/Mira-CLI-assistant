# Networking

## Check listening ports
---
os: linux
keywords: listening, ports, port, ss, netstat, open, sockets, services
aliases: listening ports, open ports, check ports, what is listening
direct: true
---
```bash
ss -tulpn
```

`-t` TCP, `-u` UDP, `-l` listening, `-p` process, `-n` numeric. Run with `sudo` to see process names owned by other users.

## Show IP addresses
---
os: linux
keywords: ip, address, network, interface, ipv4, ipv6
aliases: my ip, ip address, show ip, network address
direct: true
---
```bash
ip -brief address
```

Short form:

```bash
hostname -I
```

## Show the default gateway and routes
---
os: linux
keywords: route, gateway, default, routing, ip
aliases: default gateway, routing table, show routes
direct: true
---
```bash
ip route
```

The `default via ...` line is the gateway.

## Resolve a DNS name
---
os: linux
keywords: dns, resolve, lookup, dig, nslookup, name
aliases: dns lookup, resolve hostname, check dns
direct: true
---
```bash
resolvectl query example.com
```

Or, if `dig` is installed:

```bash
dig example.com +short
```

## Test network connectivity
---
os: linux
keywords: ping, connectivity, network, reachable, test
aliases: test connectivity, ping host, network test
direct: true
---
```bash
ping -c 4 1.1.1.1
```

If the IP responds but a hostname does not, DNS is the likely problem.

## Inspect HTTP response headers
---
os: linux
keywords: curl, http, headers, response, web, request
aliases: http headers, curl headers, check website
direct: true
---
```bash
curl -I https://example.com
```

Use `curl -v` for the full request and TLS details.

## List NetworkManager connections
---
os: linux
keywords: networkmanager, nmcli, connection, wifi, ethernet, network
aliases: network connections, list connections, nmcli
direct: true
---
```bash
nmcli connection show
```

Active connections:

```bash
nmcli connection show --active
```

## Find what is using a port
---
os: linux
keywords: port, in use, process, lsof, ss, listening, conflict
aliases: port in use, what uses port, port conflict
direct: true
---
```bash
sudo ss -tulpn | grep :8080
```

Or:

```bash
sudo lsof -i :8080
```
