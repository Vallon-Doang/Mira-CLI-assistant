# Apache (httpd)

## Apache configuration file
---
os: fedora
keywords: apache, httpd, config, configuration, path, file, main
aliases: apache config, apache configuration, httpd config, apache config file
direct: true
---
Main configuration on Fedora: `/etc/httpd/conf/httpd.conf`

Additional configuration: `/etc/httpd/conf.d/*.conf`

Fedora's package and service are named `httpd`. Debian and Ubuntu use `/etc/apache2/apache2.conf`.

Verify the configuration with:

```bash
sudo apachectl configtest
```

## Restart Apache
---
os: fedora
keywords: restart, apache, httpd, reload, service, apply
aliases: restart apache, restart httpd, reload apache
direct: true
---
```bash
sudo systemctl restart httpd
```

Reload is gentler when only configuration changed:

```bash
sudo systemctl reload httpd
```

Verify:

```bash
systemctl status httpd
```

## Check Apache status
---
os: fedora
keywords: status, apache, httpd, running, service, active
aliases: apache status, httpd status, is apache running
direct: true
---
```bash
systemctl status httpd
```

## Test the Apache configuration
---
os: fedora
keywords: test, config, apache, httpd, syntax, validate, configtest
aliases: test apache config, apache configtest, validate apache
direct: true
---
```bash
sudo apachectl configtest
```

A clean result ends with `Syntax OK`. Fix reported errors before restarting.

## View Apache logs
---
os: fedora
keywords: logs, apache, httpd, error, access, journalctl, troubleshoot
aliases: apache logs, httpd logs, apache error log
direct: true
---
```bash
journalctl -u httpd -n 100 --no-pager
```

Files:

```text
/var/log/httpd/error_log
/var/log/httpd/access_log
```

## Add a virtual host
---
os: fedora
keywords: virtualhost, vhost, apache, httpd, site, config, conf
aliases: apache virtual host, add vhost, apache site
direct: false
---
Create a file such as `/etc/httpd/conf.d/example.conf`:

```apache
<VirtualHost *:80>
    ServerName example.com
    DocumentRoot /var/www/example
</VirtualHost>
```

Then test and reload:

```bash
sudo apachectl configtest
sudo systemctl reload httpd
```

## Enable Apache at boot
---
os: fedora
keywords: enable, start, apache, httpd, boot, service
aliases: enable apache, start apache, apache at boot
direct: true
---
```bash
sudo systemctl enable --now httpd
```

## Check which ports Apache listens on
---
os: fedora
keywords: port, ports, apache, httpd, listen, 80, 443
aliases: apache ports, httpd ports, what port apache
direct: false
---
```bash
sudo ss -tulpn | grep httpd
```

The `Listen` directives are in `/etc/httpd/conf/httpd.conf` and `/etc/httpd/conf.d/`.
