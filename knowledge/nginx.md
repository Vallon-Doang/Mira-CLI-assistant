# nginx

## nginx configuration file
---
os: linux
keywords: nginx, config, configuration, path, file, main
aliases: nginx config, nginx configuration, nginx config file
direct: true
---
Main configuration: `/etc/nginx/nginx.conf`

Site and server blocks are commonly in `/etc/nginx/conf.d/*.conf` or `/etc/nginx/sites-enabled/`.

## Test the nginx configuration
---
os: linux
keywords: nginx, test, config, syntax, validate
aliases: test nginx config, nginx -t, validate nginx
direct: true
---
```bash
sudo nginx -t
```

Fix reported errors before reloading.

## Reload or restart nginx
---
os: linux
keywords: nginx, reload, restart, service, apply, systemctl
aliases: reload nginx, restart nginx, nginx reload
direct: true
---
```bash
sudo systemctl reload nginx
```

Use `restart` if a reload is not enough:

```bash
sudo systemctl restart nginx
```

## View nginx logs
---
os: linux
keywords: nginx, logs, error, access, journalctl, troubleshoot
aliases: nginx logs, nginx error log, nginx access log
direct: true
---
```bash
journalctl -u nginx -n 100 --no-pager
```

Files:

```text
/var/log/nginx/error.log
/var/log/nginx/access.log
```

## Check nginx status
---
os: linux
keywords: nginx, status, running, service, active
aliases: nginx status, is nginx running
direct: true
---
```bash
systemctl status nginx
```

## Add an nginx server block
---
os: linux
keywords: nginx, server, block, site, virtualhost, config
aliases: nginx server block, nginx site, add site
direct: false
---
Create `/etc/nginx/conf.d/example.conf`:

```nginx
server {
    listen 80;
    server_name example.com;
    root /var/www/example;
}
```

Then:

```bash
sudo nginx -t
sudo systemctl reload nginx
```
