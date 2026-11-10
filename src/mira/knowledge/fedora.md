# Fedora

## Fedora version
---
os: fedora
keywords: fedora, version, release, os, edition
aliases: fedora version, os version, what version
direct: true
---
```bash
cat /etc/os-release
```

Or, for a short summary:

```bash
hostnamectl
```

`VERSION_ID` is the Fedora release number (for example, `44`).

## Install a package
---
os: fedora
keywords: install, package, dnf, software, app
aliases: install package, dnf install, install software
direct: true
---
```bash
sudo dnf install PACKAGE
```

Search first if you are unsure of the package name:

```bash
dnf search TERM
```

## Update the system
---
os: fedora
keywords: update, upgrade, dnf, system, packages
aliases: update system, upgrade fedora, dnf upgrade
direct: true
---
```bash
sudo dnf upgrade --refresh
```

Warning: this installs available updates and may restart services. Reboot if the kernel or graphics drivers were updated.

## Search for a package
---
os: fedora
keywords: search, package, dnf, find, available
aliases: search package, find package, dnf search
direct: true
---
```bash
dnf search TERM
```

Show details before installing:

```bash
dnf info PACKAGE
```

## Remove a package
---
os: fedora
keywords: remove, uninstall, package, dnf, delete
aliases: remove package, uninstall package, dnf remove
direct: true
---
```bash
sudo dnf remove PACKAGE
```

Warning: removing packages can also remove dependencies. Review the transaction summary before confirming.

## List enabled repositories
---
os: fedora
keywords: repository, repo, repolist, rpmfusion, enabled
aliases: list repos, enabled repositories, dnf repolist
direct: true
---
```bash
dnf repolist
```

Add RPM Fusion (if needed) only from the official instructions at <https://rpmfusion.org>.

## Change the hostname
---
os: fedora
keywords: hostname, host, name, rename
aliases: change hostname, set hostname
direct: true
---
```bash
sudo hostnamectl set-hostname NEW_NAME
```

Verify:

```bash
hostnamectl
```

## SELinux status
---
os: fedora
keywords: selinux, enforcing, permissive, disabled, security
aliases: selinux status, check selinux
direct: true
---
```bash
getenforce
```

`Enforcing` means SELinux is active. Do not disable it to work around a denial; inspect the audit log instead:

```bash
sudo ausearch -m AVC -ts recent
```
