from datetime import timedelta, datetime
from jose import jwt, JWTError
import json
from pathlib import Path

# Load JWT configuration from config.json
def load_jwt_config():
    config_path = Path(__file__).parent.parent.parent / "resources" / "config.json"
    with open(config_path, 'r') as f:
        config = json.load(f)
    return config.get("JWT", {})

# Load configuration
jwt_config = load_jwt_config()

SECRET_KEY = jwt_config.get("SECRET_KEY", "")
SECRET_KEY_PREVIOUS = jwt_config.get("SECRET_KEY_PREVIOUS", "")
ALGORITHM = jwt_config.get("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = jwt_config.get("ACCESS_TOKEN_EXPIRE_MINUTES", 10)
REFRESH_TOKEN_EXPIRE_DAYS = jwt_config.get("REFRESH_TOKEN_EXPIRE_DAYS", 1)

if not SECRET_KEY:
    raise ValueError("JWT SECRET_KEY not found in config.json")


def create_access_token(data: dict, token_type: str = "access"):
    """
    Create a JWT token (access or refresh).
    
    Args:
        data: Payload data to encode (e.g., {"username": "user123"})
        token_type: "access" or "refresh" (default: "access")
    
    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    
    # Set expiration based on token type
    if token_type == "refresh":
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Add token metadata
    to_encode.update({
        "exp": expire,
        "type": token_type  # Identify token type
    })
    
    # Sign with current key
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str):
    """
    Verify and decode a JWT token.
    Supports key rotation by trying both current and previous keys.
    
    Args:
        token: JWT token string to verify
    
    Returns:
        Decoded payload dict if valid, None if invalid
    """
    # Try current key first
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        pass
    
    # If current key fails and we have a previous key, try it
    if SECRET_KEY_PREVIOUS:
        try:
            payload = jwt.decode(token, SECRET_KEY_PREVIOUS, algorithms=[ALGORITHM])
            return payload
        except JWTError:
            pass
    
    # Both keys failed
    return None


def get_config():
    """Get current JWT configuration"""
    return {
        "SECRET_KEY": SECRET_KEY,
        "ALGORITHM": ALGORITHM,
        "ACCESS_TOKEN_EXPIRE_MINUTES": ACCESS_TOKEN_EXPIRE_MINUTES,
        "HAS_PREVIOUS_KEY": bool(SECRET_KEY_PREVIOUS)
    }