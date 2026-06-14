# Git Workflow Guide

## 📋 Table of Contents
1. [Initial Setup](#initial-setup)
2. [Daily Workflow](#daily-workflow)
3. [Pushing to GitHub](#pushing-to-github)
4. [Resolving Merge Conflicts](#resolving-merge-conflicts)
5. [Common Scenarios](#common-scenarios)
6. [Best Practices](#best-practices)

---

## Initial Setup

### **Configure SSH Authentication (Recommended)**

SSH is more secure and convenient than HTTPS:

```bash
# Check current remote URL
git remote -v

# If using HTTPS, switch to SSH
git remote set-url origin git@github.com:username/repository.git

# Verify the change
git remote -v
# Should show: git@github.com:username/repository.git
```

### **Generate SSH Key (If Needed)**

```bash
# Generate SSH key
ssh-keygen -t ed25519 -C "your_email@example.com"

# Add to GitHub
# 1. Copy public key: cat ~/.ssh/id_ed25519.pub
# 2. Go to: GitHub → Settings → SSH and GPG keys → New SSH key
# 3. Paste the key

# Test connection
ssh -T git@github.com
```

---

## Daily Workflow

### **Standard Development Cycle**

```bash
# 1. Start your day - pull latest changes
git pull origin main

# 2. Make your changes
# ... edit files ...

# 3. Check what changed
git status
git diff

# 4. Stage changes
git add .
# Or specific files:
# git add file1.py file2.md

# 5. Commit with meaningful message
git commit -m "feat: Add mockup benchmark script"

# 6. Push to GitHub
git push origin main
```

### **Commit Message Convention**

Use conventional commits format:

```
feat: Add new feature
fix: Fix bug
docs: Update documentation
refactor: Code refactoring
test: Add tests
chore: Maintenance tasks
```

**Examples:**
```bash
git commit -m "feat: Add MSSQL commands module"
git commit -m "fix: Resolve CCSID encoding issue"
git commit -m "docs: Update UDF presentation"
git commit -m "refactor: Extract CLI commands to modules"
```

---

## Pushing to GitHub

### **Scenario 1: Clean Push (No Conflicts)**

```bash
git add .
git commit -m "feat: Your changes"
git push origin main
```

### **Scenario 2: Remote Has New Commits**

```bash
# Pull and merge first
git pull origin main

# Resolve conflicts if any (see below)

# Then push
git push origin main
```

### **Scenario 3: Divergent Histories (Unrelated Histories)**

This happens when local and remote started independently:

```bash
# Pull with unrelated histories flag
git pull origin main --allow-unrelated-histories

# Choose merge strategy:
# Option A: Merge (default)
git pull origin main --allow-unrelated-histories --no-rebase

# Option B: Rebase (cleaner history)
git pull origin main --allow-unrelated-histories --rebase

# Then push
git push origin main
```

### **Scenario 4: Force Push (Overwrite Remote)**

⚠️ **WARNING:** This deletes remote commits!

```bash
# Only use if you're sure remote can be overwritten
git push origin main --force

# Safer: force push with lease (won't overwrite others' work)
git push origin main --force-with-lease
```

**When to use force push:**
- ✅ Fresh repository with only README/license
- ✅ You own the repo and want to replace history
- ❌ Shared repository with collaborators
- ❌ Important remote commits you want to keep

---

## Resolving Merge Conflicts

### **What is a Merge Conflict?**

When Git can't automatically combine changes from different commits:

```
Your local:  A → B → C
Remote:      A → D → E
                 ↓
           CONFLICT in file.txt
```

### **Option 1: Keep Your Local Version (Most Common)**

```bash
# When in conflict during rebase or merge:

# Keep YOUR version
git checkout --ours conflicted_file.txt

# Mark as resolved
git add conflicted_file.txt

# Continue
git rebase --continue
# or
git commit  # if in merge
```

### **Option 2: Keep Remote Version**

```bash
# Accept THEIR version
git checkout --theirs conflicted_file.txt

# Mark as resolved
git add conflicted_file.txt

# Continue
git rebase --continue
```

### **Option 3: Manual Merge**

```bash
# Open the conflicted file
nano conflicted_file.txt

# You'll see conflict markers:
<<<<<<< HEAD
Your changes
=======
Their changes
>>>>>>> branch-name

# Edit to combine both changes as you want
# Remove the markers (<<<<, ====, >>>>)

# Save and mark resolved
git add conflicted_file.txt
git rebase --continue
```

### **Multiple Conflicts During Rebase**

Rebase stops at EACH conflict. Repeat for each:

```bash
# Conflict 1
git checkout --ours file1.txt
git add file1.txt
git rebase --continue

# Conflict 2
git checkout --ours file2.txt
git add file2.txt
git rebase --continue

# ... repeat until done
```

### **Abort Rebase (If Something Goes Wrong)**

```bash
# Cancel the rebase, return to original state
git rebase --abort
```

---

## Common Scenarios

### **Scenario A: Repository Renamed on GitHub**

```bash
# 1. Rename on GitHub (via web UI or gh CLI)

# 2. Update local remote URL
cd /path/to/repo
git remote set-url origin git@github.com:username/new-name.git

# 3. Verify
git remote -v

# 4. Continue working normally
git pull origin main
git push origin main
```

### **Scenario B: Fresh Push to New Repository**

```bash
# Initialize (if not done)
git init
git add .
git commit -m "Initial commit"

# Add remote
git remote add origin git@github.com:username/repo.git

# Push
git push -u origin main
```

### **Scenario C: Large Files Rejected**

```bash
# Remove large files from history
git filter-branch --tree-filter 'rm -f large_file.bin' HEAD

# Or use .gitignore
echo "*.bin" >> .gitignore
git add .gitignore
git commit -m "chore: Add gitignore for large files"
```

### **Scenario D: Accidentally Committed Sensitive Data**

```bash
# Remove from last commit
git reset HEAD~1
# Edit .gitignore
git add .
git commit -m "fix: Remove sensitive data"

# If already pushed, force push (WARNING!)
git push origin main --force
```

---

## Best Practices

### ✅ **DO:**

1. **Pull before you start working**
   ```bash
   git pull origin main
   ```

2. **Commit frequently with clear messages**
   ```bash
   git add .
   git commit -m "feat: Add benchmark script"
   ```

3. **Use SSH authentication**
   ```bash
   git remote set-url origin git@github.com:user/repo.git
   ```

4. **Test before pushing**
   ```bash
   # Make sure code works
   ./test.sh
   git push origin main
   ```

5. **Keep commits atomic**
   - One feature/fix per commit
   - Don't mix unrelated changes

### ❌ **DON'T:**

1. **Don't force push to shared branches**
   ```bash
   # BAD on main/shared branches
   git push origin main --force
   ```

2. **Don't commit large binary files**
   ```bash
   # BAD
   git add *.jar *.exe *.zip
   ```

3. **Don't commit secrets**
   ```bash
   # BAD - passwords, API keys, tokens
   git add .env config.yml
   ```

4. **Don't ignore merge conflicts**
   - Always review conflict markers
   - Test after resolving

5. **Don't work directly on main**
   - Use feature branches for big changes
   ```bash
   git checkout -b feature/new-script
   # ... work ...
   git push origin feature/new-script
   ```

---

## Quick Reference

### **Most Common Commands**

```bash
# Check status
git status

# See changes
git diff

# Add files
git add .

# Commit
git commit -m "message"

# Pull latest
git pull origin main

# Push changes
git push origin main

# Switch to SSH
git remote set-url origin git@github.com:user/repo.git

# Resolve conflict (keep yours)
git checkout --ours file.txt
git add file.txt
git rebase --continue
```

### **Emergency Commands**

```bash
# Undo last commit (keep changes)
git reset --soft HEAD~1

# Undo last commit (discard changes)
git reset --hard HEAD~1

# Cancel merge
git merge --abort

# Cancel rebase
git rebase --abort

# Discard all local changes
git checkout -- .
git clean -fd
```

---

## Troubleshooting

### **Error: Authentication Failed**

```bash
# Switch from HTTPS to SSH
git remote set-url origin git@github.com:username/repository.git

# Or generate Personal Access Token:
# GitHub → Settings → Developer settings → Personal access tokens
```

### **Error: Updates Were Rejected**

```bash
# Pull first
git pull origin main

# Then push
git push origin main
```

### **Error: Divergent Branches**

```bash
git pull origin main --allow-unrelated-histories
# Resolve conflicts
git push origin main
```

### **Error: Merge Conflict in README.md**

```bash
# Keep your version
git checkout --ours README.md
git add README.md
git rebase --continue
```

---

## Additional Resources

- **Git Documentation:** https://git-scm.com/doc
- **Conventional Commits:** https://www.conventionalcommits.org/
- **GitHub CLI:** https://cli.github.com/
- **SSH Setup:** https://docs.github.com/en/authentication/connecting-to-github-with-ssh

---

**Remember:** When in doubt, `git status` tells you what's happening! 🎯
