from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from repository import schemas, database, models
from sqlalchemy.orm import Session
from repository.hashing import Hash

import repository.JWTToken as token
from typing import Annotated
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext

from jose import JWTError, jwt

from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# Import JWT configuration from JWTToken module
from repository.JWTToken import ALGORITHM, SECRET_KEY, REFRESH_TOKEN_EXPIRE_DAYS


import time
from fastapi import Request, HTTPException

RATE_LIMIT = 5          # max calls
WINDOW_SECONDS = 60     # per 1 minute

request_log = {}       # { key: [timestamps...] }

def rate_limiter(request: Request, key_prefix: str = "ip"):
    now = time.time()

    if key_prefix == "ip":
        key = request.client.host
    else:
        key = key_prefix   # e.g. username or user_id

    timestamps = request_log.get(key, [])

    # keep only last 60s timestamps
    timestamps = [t for t in timestamps if now - t < WINDOW_SECONDS]

    if len(timestamps) >= RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Try again in a minute."
        )

    timestamps.append(now)
    request_log[key] = timestamps

router = APIRouter(
    tags=['Authentication']
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

templates = Jinja2Templates(directory="templates")

router = APIRouter(
    tags=['Authentication']
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

templates = Jinja2Templates(directory="templates")

revoked_tokens = set()

@router.post('/login')
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    """
    Authenticate user and return access token + refresh token.
    
    Returns:
        - access_token: Short-lived token for API access (30 minutes) in response body
        - refresh_token: Long-lived token (1 day) set as HttpOnly cookie (secure from XSS)
    """

    rate_limiter(request)
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    
    if not user:
        raise HTTPException(status_code=401, detail='Invalid Credentials')
    
    if not Hash.verify(user.password, form_data.password):
        raise HTTPException(status_code=404, detail='Incorrect Password')

    # Create both access and refresh tokens
    access_token = token.create_access_token(data={"username": user.username}, token_type="access")
    refresh_token = token.create_access_token(data={"username": user.username}, token_type="refresh")
    
    # Store user data in the session
    request.session["user"] = {"username": user.username}

    # Create response with access token
    response = JSONResponse(content={
        "access_token": access_token,        
        "token_type": "bearer",
        "user": user.username,
        "expires_in": 600  
    })
    
    # Set refresh token as HttpOnly cookie (secure from XSS attacks)
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,           
        secure=True,             
        samesite="lax",          
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,  
        path="/consumer_api"     
    )
    
    return response


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse("secure_login.html", {"request": request})



@router.get("/get_current_user", response_model=schemas.User_get)
async def get_current_user(token_str: Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(database.get_db)):

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


    payload = token.verify_token(token_str)
    
    if not payload:
        raise credentials_exception
    
    username: str = payload.get("username")
    if username is None or username in revoked_tokens:
        raise credentials_exception
    
    token_data = schemas.TokenData(username=username)


    user = db.query(models.User).filter(models.User.username == token_data.username).first()

    if not user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")

    if user is None:
        raise credentials_exception

    return user


@router.post("/refresh")
async def refresh_access_token(request: Request, db: Session = Depends(database.get_db)):
    """
    Get a new access token using the refresh token from HttpOnly cookie.
    
    This endpoint reads the refresh token from the HttpOnly cookie (secure from XSS)
    and issues a new access token if the refresh token is valid.
    
    Returns:
        - access_token: New short-lived access token (30 minutes)
        - token_type: "bearer"
        - expires_in: Token expiration in seconds
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    

    refresh_token = request.cookies.get("refresh_token")
    
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found. Please login again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = token.verify_token(refresh_token)
    
    if not payload:
        raise credentials_exception
    
    token_type = payload.get("type")
    if token_type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Expected refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Extract username
    username: str = payload.get("username")
    if username is None or username in revoked_tokens:
        raise credentials_exception
    
    # Verify user still exists and is active
    user = db.query(models.User).filter(models.User.username == username).first()
    
    if user is None:
        raise credentials_exception
    
    if not user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    
    # Create new access token
    new_access_token = token.create_access_token(
        data={"username": username},
        token_type="access"
    )
    
    # Create new refresh token (Rotation)
    new_refresh_token = token.create_access_token(
        data={"username": username},
        token_type="refresh"
    )

    # Create response with access token
    response = JSONResponse(content={
        "access_token": new_access_token,
        "token_type": "bearer",
        "expires_in": 600  # 10 minutes in seconds
    })
    
    # Set new refresh token as HttpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,           # Cannot be accessed by JavaScript (XSS protection)
        secure=True,             # Only sent over HTTPS (set to False for local development)
        samesite="lax",          # CSRF protection
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,  # 1 day in seconds
        path="/consumer_api"     # Only sent to API endpoints
    )
    
    return response


@router.post("/logout")
async def logout(current_user: schemas.TokenData = Depends(get_current_user)):
    """
    Logout user and clear refresh token cookie.
    """
    # Add the token to the set of revoked tokens
    revoked_tokens.add(current_user.username)
    
    # Create response
    response = JSONResponse(content={"message": "Logout successful"})
    
    # Clear the refresh token cookie
    response.delete_cookie(
        key="refresh_token",
        path="/consumer_api"
    )
    
    return response