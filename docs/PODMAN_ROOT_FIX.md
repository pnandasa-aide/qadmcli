# Podman Root vs Rootless Issue Fix

## ❌ Problem

When running `qadmcli.sh` as normal user (ubuntu), it:
1. **Stuck/hangs** when checking for images
2. **Rebuilds image every time** even though it exists
3. Requires Ctrl+C to continue

---

## 🔍 Root Cause

**Podman has TWO separate storage locations:**

### 1. **Root Podman** (with sudo)
```bash
sudo podman images
# Shows images stored in: /var/lib/containers/storage/
```

### 2. **Rootless Podman** (without sudo)
```bash
podman images
# Shows images stored in: ~/.local/share/containers/storage/
```

**The Problem:**
- All your images were built with **sudo** (root podman)
- When you run `qadmcli.sh` without sudo, it uses **rootless podman**
- Rootless podman has **NO images** → thinks it needs to rebuild
- But the build may hang or fail due to permissions

---

## ✅ Solution: Use `sudo` in qadmcli.sh

### Before (Broken):
```bash
# Check if image exists
if ! podman images ...; then  # ← Rootless podman (empty)
    podman build ...           # ← Tries to build as rootless (hangs)
fi

podman run ...                 # ← Rootless podman (no image found)
```

### After (Fixed):
```bash
# Check if image exists
if ! sudo podman images ...; then  # ← Root podman (has images!)
    sudo podman build ...           # ← Build as root (works)
fi

sudo podman run ...                 # ← Root podman (image found!)
```

---

## 📋 What Was Changed

### File: `qadmcli/qadmcli.sh`

**Changed 4 lines to use `sudo`:**

1. Line 27: `podman images` → `sudo podman images`
2. Line 32: `podman build` → `sudo podman build`
3. Line 48: `podman run` → `sudo podman run`
4. Line 57: `podman run` → `sudo podman run`

---

## 🧪 Verify the Fix

### Test 1: Check if Image is Found

```bash
cd ~/qadmcli
./qadmcli.sh connection test
```

**Expected Output:**
```
📦 Using existing image: qadmcli
🚀 Running: qadmcli connection test
[runs successfully]
```

**NOT:**
```
🔨 Building qadmcli image...  # ← Should NOT rebuild!
```

---

### Test 2: Compare Root vs Rootless

```bash
# Root podman (has images)
sudo podman images | grep qadmcli
# Output: localhost/qadmcli  latest  127bfddc279f  21 minutes ago

# Rootless podman (empty)
podman images | grep qadmcli
# Output: (nothing)
```

---

## 🎯 Why This Happened

### Possible Reasons:

1. **Images built with sudo:**
   ```bash
   sudo podman build -t qadmcli .
   ```

2. **Docker Compose uses root podman:**
   ```bash
   sudo docker-compose up -d
   # or
   sudo podman-compose up -d
   ```

3. **System service runs as root:**
   ```bash
   sudo systemctl start podman
   ```

---

## 🔧 Alternative Solutions

### Option 1: Rebuild Images as Rootless (NOT Recommended)

```bash
# Switch to rootless mode
podman build -t qadmcli -f Containerfile .
```

**Pros:**
- No sudo needed

**Cons:**
- Duplicate images (root + rootless)
- Wastes disk space
- Other tools may still use root podman

---

### Option 2: Configure Podman Rootless (Complex)

```bash
# Enable rootless podman
sudo loginctl enable-linger ubuntu

# Migrate storage (risky)
podman system migrate
```

**Pros:**
- Consistent behavior

**Cons:**
- Complex setup
- May break existing containers
- Requires system changes

---

### Option 3: Use sudo in Scripts (Current Fix) ✅

```bash
sudo podman ...
```

**Pros:**
- Simple
- Works with existing images
- No migration needed

**Cons:**
- Requires sudo password (or passwordless sudo)
- Slight security consideration

---

## 📝 Best Practices

### 1. **Be Consistent with Podman Mode**

Choose ONE:
- ✅ All root (with sudo)
- ✅ All rootless (without sudo)

**Don't mix them!**

---

### 2. **Check Which Mode You're Using**

```bash
# Check if running as root
podman info | grep -i "rootless"
# Output: rootless: true  (rootless)
# Output: rootless: false (root)
```

---

### 3. **Verify Image Location**

```bash
# Root images
sudo podman images

# Rootless images
podman images
```

---

### 4. **Set Up Passwordless Sudo (Optional)**

If you don't want to type password every time:

```bash
# Edit sudoers (as root)
sudo visudo

# Add this line (replace 'ubuntu' with your username)
ubuntu ALL=(ALL) NOPASSWD: /usr/bin/podman
```

**Warning:** This reduces security - only do this on trusted systems!

---

## 🚀 Current Status

### ✅ Fixed Files:
- `qadmcli/qadmcli.sh` - All podman commands now use `sudo`

### 🔍 To Check Other Scripts:

```bash
# Find scripts using podman without sudo
grep -r "podman " --include="*.sh" ~/ | grep -v "sudo podman"
```

---

## 📊 Comparison Table

| Aspect | Root Podman (sudo) | Rootless Podman |
|--------|-------------------|-----------------|
| **Storage** | `/var/lib/containers/` | `~/.local/share/containers/` |
| **Permissions** | Requires sudo | No sudo needed |
| **Performance** | Faster | Slightly slower |
| **Security** | Less secure | More secure |
| **Your Images** | ✅ Has all images | ❌ Empty |
| **Network** | Full access | User namespace |

---

## 💡 Quick Reference

### Check Podman Mode:
```bash
podman info 2>&1 | grep rootless
```

### List Images:
```bash
sudo podman images  # Root
podman images       # Rootless
```

### Build Image:
```bash
sudo podman build -t myimage .  # Root
podman build -t myimage .       # Rootless
```

### Run Container:
```bash
sudo podman run myimage  # Root
podman run myimage       # Rootless
```

---

## ✅ Summary

**Problem:** qadmcli.sh was using rootless podman, but images were stored in root podman

**Solution:** Added `sudo` to all podman commands in qadmcli.sh

**Result:** Script now finds existing images and doesn't rebuild every time

---

**Note: If you have other scripts with similar issues, apply the same fix - add `sudo` to podman commands!**
