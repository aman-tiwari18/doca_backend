# Refresh Token Implementation Guide

## 🔄 Overview

Your API now supports **Access Token + Refresh Token** authentication pattern for seamless token rotation without requiring users to re-login.

### Token Types

| Token Type | Lifetime | Purpose | Storage |
|------------|----------|---------|---------|
| **Access Token** | 60 minutes | API authentication | Memory/SessionStorage |
| **Refresh Token** | 7 days | Get new access tokens | LocalStorage (HttpOnly cookie recommended) |

---

## 🚀 How It Works

### 1. **Login** - Get Both Tokens

**Endpoint:** `POST /consumer_api/login`

**Request:**
```bash
curl -X POST "http://localhost:8000/consumer_api/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=your_username&password=your_password"
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": "your_username",
  "expires_in": 3600
}
```

### 2. **Use Access Token** - Make API Calls

**Endpoint:** Any protected endpoint

**Request:**
```bash
curl -X GET "http://localhost:8000/consumer_api/get_current_user" \
  -H "Authorization: Bearer <access_token>"
```

### 3. **Refresh Token** - Get New Access Token

**When:** Before access token expires (e.g., after 50 minutes)

**Endpoint:** `POST /consumer_api/refresh`

**Request:**
```bash
curl -X POST "http://localhost:8000/consumer_api/refresh" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "your_refresh_token_here"}'
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

---

## 💻 Client-Side Implementation

### React/JavaScript Example

```javascript
// auth.js - Authentication service

class AuthService {
  constructor() {
    this.accessToken = null;
    this.refreshToken = localStorage.getItem('refresh_token');
    this.tokenExpiryTime = null;
  }

  // Login
  async login(username, password) {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);

    const response = await fetch('http://localhost:8000/consumer_api/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: formData
    });

    if (!response.ok) {
      throw new Error('Login failed');
    }

    const data = await response.json();
    
    // Store tokens
    this.accessToken = data.access_token;
    this.refreshToken = data.refresh_token;
    localStorage.setItem('refresh_token', data.refresh_token);
    
    // Calculate expiry time (refresh 5 minutes before expiry)
    this.tokenExpiryTime = Date.now() + (data.expires_in - 300) * 1000;
    
    // Start auto-refresh timer
    this.startTokenRefreshTimer();
    
    return data;
  }

  // Refresh access token
  async refreshAccessToken() {
    if (!this.refreshToken) {
      throw new Error('No refresh token available');
    }

    const response = await fetch('http://localhost:8000/consumer_api/refresh', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        refresh_token: this.refreshToken
      })
    });

    if (!response.ok) {
      // Refresh token expired or invalid - need to re-login
      this.logout();
      throw new Error('Session expired. Please login again.');
    }

    const data = await response.json();
    
    // Update access token
    this.accessToken = data.access_token;
    this.tokenExpiryTime = Date.now() + (data.expires_in - 300) * 1000;
    
    return data;
  }

  // Auto-refresh timer
  startTokenRefreshTimer() {
    // Clear existing timer
    if (this.refreshTimer) {
      clearTimeout(this.refreshTimer);
    }

    // Calculate time until refresh needed
    const timeUntilRefresh = this.tokenExpiryTime - Date.now();

    if (timeUntilRefresh > 0) {
      this.refreshTimer = setTimeout(async () => {
        try {
          await this.refreshAccessToken();
          console.log('✅ Token refreshed automatically');
          this.startTokenRefreshTimer(); // Restart timer
        } catch (error) {
          console.error('❌ Token refresh failed:', error);
        }
      }, timeUntilRefresh);
    }
  }

  // Make authenticated API call
  async apiCall(url, options = {}) {
    // Check if token needs refresh
    if (Date.now() >= this.tokenExpiryTime) {
      await this.refreshAccessToken();
    }

    // Add authorization header
    const headers = {
      ...options.headers,
      'Authorization': `Bearer ${this.accessToken}`
    };

    const response = await fetch(url, {
      ...options,
      headers
    });

    // If 401, try refreshing token once
    if (response.status === 401) {
      await this.refreshAccessToken();
      
      // Retry request with new token
      headers.Authorization = `Bearer ${this.accessToken}`;
      return fetch(url, { ...options, headers });
    }

    return response;
  }

  // Logout
  logout() {
    this.accessToken = null;
    this.refreshToken = null;
    localStorage.removeItem('refresh_token');
    
    if (this.refreshTimer) {
      clearTimeout(this.refreshTimer);
    }
  }

  // Check if user is authenticated
  isAuthenticated() {
    return !!this.refreshToken;
  }
}

// Export singleton instance
export const authService = new AuthService();
```

### Usage Example

```javascript
// Login
try {
  const result = await authService.login('username', 'password');
  console.log('Logged in as:', result.user);
} catch (error) {
  console.error('Login failed:', error);
}

// Make API calls (auto-refreshes token if needed)
try {
  const response = await authService.apiCall(
    'http://localhost:8000/consumer_api/get_current_user'
  );
  const user = await response.json();
  console.log('Current user:', user);
} catch (error) {
  console.error('API call failed:', error);
}

// Logout
authService.logout();
```

---

## 🔒 Security Best Practices

### ✅ DO:

1. **Store refresh tokens securely**
   - Use HttpOnly cookies (best)
   - Or encrypted localStorage
   - Never in plain sessionStorage

2. **Refresh proactively**
   - Refresh 5 minutes before expiry
   - Don't wait for 401 errors

3. **Handle token expiry gracefully**
   - Redirect to login when refresh token expires
   - Show user-friendly messages

4. **Use HTTPS in production**
   - Tokens transmitted over secure connections only

5. **Implement token rotation**
   - Optionally issue new refresh token on each refresh

### ❌ DON'T:

1. **Don't store tokens in**
   - URL parameters
   - Plain cookies (without HttpOnly)
   - Browser history

2. **Don't share tokens**
   - Between different users
   - Across different devices (unless intended)

3. **Don't ignore expiry**
   - Always check token expiration
   - Handle expired tokens properly

---

## 📊 Token Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│                         USER LOGIN                          │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  Access Token (60 min) │
              │  Refresh Token (7 days)│
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │   Make API Calls       │◄──────┐
              │   (with access token)  │       │
              └────────────┬───────────┘       │
                           │                   │
                           │ After 55 min      │
                           ▼                   │
              ┌────────────────────────┐       │
              │  Refresh Access Token  │       │
              │  (with refresh token)  │       │
              └────────────┬───────────┘       │
                           │                   │
                           │ Get new access    │
                           └───────────────────┘
                           
                           │ After 7 days
                           ▼
              ┌────────────────────────┐
              │  Refresh Token Expires │
              │  → User must re-login  │
              └────────────────────────┘
```

---

## 🧪 Testing

### Test Login
```bash
# Login and save tokens
curl -X POST "http://localhost:8000/consumer_api/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test&password=test123" \
  | jq '.'

# Save the tokens
ACCESS_TOKEN="<access_token_from_response>"
REFRESH_TOKEN="<refresh_token_from_response>"
```

### Test API Call with Access Token
```bash
curl -X GET "http://localhost:8000/consumer_api/get_current_user" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

### Test Token Refresh
```bash
curl -X POST "http://localhost:8000/consumer_api/refresh" \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\": \"$REFRESH_TOKEN\"}" \
  | jq '.'
```

### Test Expired Access Token
```bash
# Wait 60+ minutes or use an old token
curl -X GET "http://localhost:8000/consumer_api/get_current_user" \
  -H "Authorization: Bearer <old_access_token>"
# Should return 401

# Refresh to get new token
curl -X POST "http://localhost:8000/consumer_api/refresh" \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\": \"$REFRESH_TOKEN\"}"
# Should return new access token
```

---

## ⚙️ Configuration

Edit `resources/config.json`:

```json
{
  "JWT": {
    "ACCESS_TOKEN_EXPIRE_MINUTES": 60,    // Change access token lifetime
    "REFRESH_TOKEN_EXPIRE_DAYS": 7,       // Change refresh token lifetime
    ...
  }
}
```

**Recommended values:**
- **Access Token:** 15-60 minutes
- **Refresh Token:** 7-30 days

---

## 🆘 Troubleshooting

### Issue: "Invalid or expired refresh token"
**Cause:** Refresh token expired (7 days) or invalid  
**Solution:** User must login again

### Issue: "Invalid token type. Expected refresh token"
**Cause:** Sent access token to /refresh endpoint  
**Solution:** Use refresh token, not access token

### Issue: Access token not refreshing automatically
**Cause:** Client-side timer not working  
**Solution:** Check `startTokenRefreshTimer()` implementation

### Issue: 401 errors on API calls
**Cause:** Access token expired  
**Solution:** Call `/refresh` endpoint to get new access token

---

## 📚 Additional Resources

- [OAuth 2.0 Refresh Tokens](https://oauth.net/2/grant-types/refresh-token/)
- [JWT Best Practices](https://tools.ietf.org/html/rfc8725)
- [OWASP Token Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)

---

## ✅ Summary

| Feature | Status |
|---------|--------|
| Access Token (60 min) | ✅ Implemented |
| Refresh Token (7 days) | ✅ Implemented |
| Token Refresh Endpoint | ✅ Implemented |
| Token Type Validation | ✅ Implemented |
| Auto-refresh Support | ✅ Client-side example provided |
| Key Rotation Support | ✅ Works with rotated keys |

**Your API is now production-ready with modern token management!** 🎉
