# Git

## Configure Git
---
os: linux
keywords: configure, config, git, username, email, identity, setup
aliases: git config, configure git, set git email, set git name
direct: true
---
```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

Check the result:

```bash
git config --global --list
```

## Show the current branch
---
os: linux
keywords: current, branch, git, show, checkout, head
aliases: current branch, git branch, which branch
direct: true
---
```bash
git branch --show-current
```

Older Git versions:

```bash
git rev-parse --abbrev-ref HEAD
```

## Show repository status
---
os: linux
keywords: status, git, changes, modified, staged, untracked
aliases: git status, working tree, changed files
direct: true
---
```bash
git status
```

Short form:

```bash
git status --short
```

## Commit changes
---
os: linux
keywords: commit, git, add, stage, message, save
aliases: git commit, commit changes, stage and commit
direct: true
---
```bash
git add PATH
git commit -m "Describe the change"
```

Use `git add -p` to review hunks before staging.

## Show commit history
---
os: linux
keywords: log, history, commits, git, graph, recent
aliases: git log, commit history, recent commits
direct: true
---
```bash
git log --oneline --graph --decorate -n 20
```

## Clone a repository
---
os: linux
keywords: clone, git, repository, download, copy
aliases: git clone, clone repo
direct: true
---
```bash
git clone URL
```

This creates a new directory named after the repository.

## Stash changes temporarily
---
os: linux
keywords: stash, git, temporary, save, pop, restore
aliases: git stash, stash changes, save work temporarily
direct: true
---
```bash
git stash
```

Restore the most recent stash:

```bash
git stash pop
```

## Undo the last commit
---
os: linux
keywords: undo, commit, reset, git, revert, last
aliases: undo commit, revert last commit, git reset
direct: true
---
Keep the changes staged:

```bash
git reset --soft HEAD~1
```

Keep them unstaged:

```bash
git reset HEAD~1
```

Warning: `git reset --hard` discards uncommitted work permanently. Use `git revert` instead if the commit was already pushed.

## Show differences
---
os: linux
keywords: diff, changes, git, compare, patch, staged
aliases: git diff, show changes, compare files
direct: true
---
```bash
git diff
git diff --staged
```

## List remotes
---
os: linux
keywords: remote, remotes, git, origin, url
aliases: git remote, list remotes, remote url
direct: true
---
```bash
git remote -v
```
