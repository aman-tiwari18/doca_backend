# JWT Key Rotation Guide

## 🔄 How Key Rotation Works

Your JWT implementation now supports **graceful key rotation** without invalidating existing user sessions.

### Architecture

1. **Current Key (`SECRET_KEY`)**: Used to sign new tokens
2. **Previous Key (`SECRET_KEY_PREVIOUS`)**: Used to verify old tokens during transition
3. **Config-based**: All keys stored in `resources/config.json`

---

## 📅 When to Rotate Keys

**Recommended schedule:** Every **90 days**

**Immediate rotation required if:**
- Key is suspected to be compromised
- Employee with key access leaves
- Security audit recommendation
- Compliance requirements

---

## 🚀 How to Rotate Keys

### Option 1: Automated Script (Recommended)

```bash
cd /home/aman/Downloads/consumer_affairs_dashboard-aws/api
python3 scripts/rotate_jwt_key.py
```

This script will:
1. ✅ Generate a new cryptographically strong key (512 bits)
2. ✅ Move current key to `SECRET_KEY_PREVIOUS`
3. ✅ Update `config.json` automatically
4. ✅ Create a backup of config.json
5. ✅ Update rotation dates

### Option 2: Manual Rotation

1. **Generate a new key:**
   ```bash
   python3 -c "import secrets; print(secrets.token_hex(64))"
   ```

2. **Edit `resources/config.json`:**
   ```json
   {
     "JWT": {
       "SECRET_KEY": "<NEW_KEY_HERE>",
       "SECRET_KEY_PREVIOUS": "<OLD_KEY_HERE>",
       "KEY_ROTATION_DATE": "2026-01-19",
       "NEXT_ROTATION_DATE": "2026-04-19"
     }
   }
   ```

3. **Restart the application:**
   ```bash
   # If using systemd
   sudo systemctl restart your-app

   # If running manually
   # Stop the current process and restart
   uvicorn main:app --reload
   ```

---

## 🔍 What Happens During Rotation

### Timeline

**Before Rotation:**
- All tokens signed with `SECRET_KEY` (old key)
- Users are logged in with valid tokens

**Immediately After Rotation:**
- New logins get tokens signed with `SECRET_KEY` (new key)
- Old tokens still valid (verified with `SECRET_KEY_PREVIOUS`)
- **No users are logged out** ✅

**After Token Expiration (60 minutes):**
- All old tokens have expired naturally
- All active tokens signed with new key
- Safe to remove `SECRET_KEY_PREVIOUS`

### Code Flow

```python
def verify_token(token: str):
    # Try current key first
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload  # ✅ Token valid with new key
    except JWTError:
        pass
    
    # If current key fails, try previous key
    if SECRET_KEY_PREVIOUS:
        try:
            payload = jwt.decode(token, SECRET_KEY_PREVIOUS, algorithms=[ALGORITHM])
            return payload  # ✅ Token valid with old key
        except JWTError:
            pass
    
    return None  # ❌ Token invalid
```

---

## 🧹 Cleanup After Rotation

**Wait time:** `ACCESS_TOKEN_EXPIRE_MINUTES` (default: 60 minutes)

After all old tokens have expired:

1. **Edit `resources/config.json`:**
   ```json
   {
     "JWT": {
       "SECRET_KEY": "<CURRENT_KEY>",
       "SECRET_KEY_PREVIOUS": "",  // ← Clear this
       ...
     }
   }
   ```

2. **Restart application** (optional, but recommended)

---

## 📊 Monitoring Rotation

### Check Current Configuration

```python
from repository.JWTToken import get_config

config = get_config()
print(f"Algorithm: {config['ALGORITHM']}")
print(f"Token expiry: {config['ACCESS_TOKEN_EXPIRE_MINUTES']} minutes")
print(f"Has previous key: {config['HAS_PREVIOUS_KEY']}")
```

### Check Rotation Dates

```bash
cat resources/config.json | grep -A 2 "KEY_ROTATION_DATE"
```

---

## 🔒 Security Best Practices

### ✅ DO:
- Rotate keys every 90 days
- Keep `config.json` in `.gitignore`
- Use different keys for dev/staging/production
- Backup config.json before rotation
- Document rotation dates
- Test rotation in staging first

### ❌ DON'T:
- Commit `config.json` to version control
- Share keys via email/chat
- Reuse old keys
- Skip rotation schedule
- Remove `SECRET_KEY_PREVIOUS` too early

---

## 🚨 Emergency Key Rotation

If a key is **compromised**, follow these steps immediately:

1. **Rotate the key:**
   ```bash
   python3 scripts/rotate_jwt_key.py
   ```

2. **Force all users to re-login:**
   - Set `SECRET_KEY_PREVIOUS` to empty string
   - Restart application
   - All existing tokens become invalid

3. **Investigate the breach:**
   - Check access logs
   - Review who had access to config.json
   - Update security procedures

---

## 📝 Rotation Checklist

- [ ] Backup current `config.json`
- [ ] Run rotation script or manually update keys
- [ ] Verify new key is 128 characters (512 bits)
- [ ] Restart application
- [ ] Test login with new tokens
- [ ] Verify old tokens still work (if `SECRET_KEY_PREVIOUS` is set)
- [ ] Wait for token expiration period
- [ ] Remove `SECRET_KEY_PREVIOUS`
- [ ] Document rotation in your change log
- [ ] Schedule next rotation (90 days)

---

## 🛠️ Troubleshooting

### Issue: "All users logged out after rotation"
**Cause:** `SECRET_KEY_PREVIOUS` not set or incorrect  
**Solution:** Restore from backup and try again

### Issue: "New logins fail after rotation"
**Cause:** New `SECRET_KEY` not loaded  
**Solution:** Restart the application

### Issue: "Config.json not found"
**Cause:** Wrong path or file moved  
**Solution:** Check path in `JWTToken.py` line 8

---

## 📞 Support

For questions or issues:
1. Check application logs: `tail -f api/logs/*.log`
2. Verify config.json syntax: `python3 -m json.tool resources/config.json`
3. Test token generation: `python3 -c "from repository.JWTToken import create_access_token; print(create_access_token({'test': 'user'}))"`

---

## 📚 Additional Resources

- [JWT Best Practices (RFC 8725)](https://tools.ietf.org/html/rfc8725)
- [OWASP JWT Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)
- [Python Secrets Module](https://docs.python.org/3/library/secrets.html)
