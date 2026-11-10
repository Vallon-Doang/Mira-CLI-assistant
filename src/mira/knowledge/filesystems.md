# Filesystems

## Check available disk space
---
os: linux
keywords: disk, space, df, filesystem, available, free, usage
aliases: disk space, free space, check disk, available space
direct: true
---
```bash
df -h
```

The `Use%` column shows how full each mounted filesystem is. Focus on `/` and any separate `/home` or `/var` mount.

## Check inode usage
---
os: linux
keywords: inode, inodes, df, files, exhausted, usage
aliases: inode usage, check inodes, no space left
direct: true
---
```bash
df -i
```

If inodes are at 100% while `df -h` shows free space, many small files are the cause.

## Show directory size
---
os: linux
keywords: directory, size, du, folder, usage, large
aliases: directory size, folder size, du
direct: true
---
```bash
du -sh DIR
```

Largest entries in the current directory:

```bash
du -h --max-depth=1 . | sort -h
```

## Find large files
---
os: linux
keywords: large, files, find, size, biggest, disk
aliases: find large files, biggest files, large file
direct: true
---
```bash
find . -type f -size +100M -printf '%s %p\n' | sort -nr | head
```

Run it from the directory you want to inspect, not from `/`, unless you accept a long scan.

## List mounted filesystems
---
os: linux
keywords: mount, mounted, filesystem, lsblk, findmnt, partitions
aliases: list mounts, mounted filesystems, show partitions
direct: true
---
```bash
lsblk -f
findmnt
```

`lsblk -f` also shows filesystem type, UUID, and mount point.

## Show a filesystem type
---
os: linux
keywords: filesystem, type, ext4, xfs, btrfs, lsblk, findmnt
aliases: filesystem type, what filesystem, fs type
direct: true
---
```bash
lsblk -f
```

Or for one mount:

```bash
findmnt -T /path
```

## Edit the filesystem table
---
os: linux
keywords: fstab, mount, boot, filesystem, uuid, permanent
aliases: edit fstab, mount at boot, fstab
direct: true
---
The file is `/etc/fstab`. Always back it up first:

```bash
sudo cp /etc/fstab /etc/fstab.bak
sudoedit /etc/fstab
```

Validate before rebooting:

```bash
sudo mount -a
```

Warning: a bad `/etc/fstab` entry can prevent the system from booting. Keep a backup and test with `mount -a`.

## Change file permissions
---
os: linux
keywords: permissions, chmod, chown, owner, mode, access
aliases: change permissions, file permissions, chmod
direct: true
---
```bash
chmod 644 FILE
chmod 755 DIRECTORY
sudo chown USER:GROUP FILE
```

Warning: recursive permission changes (`chmod -R`, `chown -R`) can break system files. Apply them only to the specific tree you intend.

## Find where a path is mounted
---
os: linux
keywords: mount, path, findmnt, where, device
aliases: where mounted, find mount, mount point
direct: true
---
```bash
findmnt -T /path/to/file
```
