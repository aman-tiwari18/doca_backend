#!/usr/bin/env python3
"""
JWT Key Rotation Script

This script helps you rotate JWT signing keys safely without invalidating all existing tokens.

Usage:
    python scripts/rotate_jwt_key.py

The script will:
1. Generate a new cryptographically strong secret key
2. Move the current key to SECRET_KEY_PREVIOUS
3. Update config.json with the new key
4. Update rotation dates

After rotation, tokens signed with the old key will still work until they expire.
"""

import json
import secrets
from pathlib import Path
from datetime import datetime, timedelta
import shutil


def generate_new_key():
    """Generate a cryptographically strong 512-bit key"""
    return secrets.token_hex(64)


def rotate_keys():
    """Rotate JWT keys in config.json"""
    config_path = Path(__file__).parent.parent.parent / "resources" / "config.json"
    
    # Backup config file
    backup_path = config_path.with_suffix('.json.backup')
    shutil.copy(config_path, backup_path)
    print(f"✅ Backed up config to: {backup_path}")
    
    # Load current config
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    if "JWT" not in config:
        print("❌ JWT configuration not found in config.json")
        return False
    
    # Get current keys
    current_key = config["JWT"].get("SECRET_KEY", "")
    previous_key = config["JWT"].get("SECRET_KEY_PREVIOUS", "")
    
    if not current_key:
        print("❌ No current SECRET_KEY found")
        return False
    
    # Generate new key
    new_key = generate_new_key()
    
    # Rotate keys
    config["JWT"]["SECRET_KEY"] = new_key
    config["JWT"]["SECRET_KEY_PREVIOUS"] = current_key  # Keep old key for validation
    
    # Update rotation dates
    today = datetime.now().strftime("%Y-%m-%d")
    next_rotation = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")
    
    config["JWT"]["KEY_ROTATION_DATE"] = today
    config["JWT"]["NEXT_ROTATION_DATE"] = next_rotation
    
    # Save updated config
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)
    
    print("\n" + "="*70)
    print("🔐 JWT KEY ROTATION COMPLETED")
    print("="*70)
    print(f"\n✅ New key generated and saved to config.json")
    print(f"✅ Previous key preserved for token validation")
    print(f"✅ Rotation date: {today}")
    print(f"✅ Next rotation due: {next_rotation}")
    print("\n" + "="*70)
    print("NEXT STEPS:")
    print("="*70)
    print("1. Restart your application: systemctl restart your-app")
    print("2. Existing tokens will continue to work (validated with old key)")
    print("3. New tokens will be signed with the new key")
    print(f"4. After {config['JWT'].get('ACCESS_TOKEN_EXPIRE_MINUTES', 60)} minutes, all old tokens will expire")
    print("5. Then you can remove SECRET_KEY_PREVIOUS from config.json")
    print("\n⚠️  IMPORTANT:")
    print("   - Keep config.json secure and never commit it to public repos")
    print("   - Backup file saved at: " + str(backup_path))
    print("="*70 + "\n")
    
    return True


if __name__ == "__main__":
    try:
        success = rotate_keys()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Key rotation failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
