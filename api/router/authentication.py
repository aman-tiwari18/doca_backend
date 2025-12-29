from fastapi import APIRouter, Depends, HTTPException, status, Request
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


SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

router = APIRouter(
    tags=['Authentication']
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

templates = Jinja2Templates(directory="templates")

revoked_tokens = set()

@router.post('/login')
def login(request:Request, form_data:OAuth2PasswordRequestForm= Depends(), db:Session = Depends(database.get_db)):
    
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    
    if not user:
        raise HTTPException(status_code=401, detail=f'Invalid Credentials')
    
    if not Hash.verify(user.password, form_data.password):
        raise HTTPException(status_code=404, detail=f'Incorrect Password')

    access_token = token.create_access_token( data={"username": user.username}  )
     # Store user data in the session
    request.session["user"] = {"username": user.username}

    return {"access_token": access_token, "token_type": "bearer", "user": user.username}

# Route to render an HTML form for login
@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse("secure_login.html", {"request": request})


# Route to get the current session data
@router.get("/get_current_user", response_model=schemas.User_get)
async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(database.get_db)):

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # verify token
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("username")
        if username is None or username in revoked_tokens:
            raise credentials_exception
        token_data = schemas.TokenData(username=username)
    except JWTError:
        raise credentials_exception

    # verify user
    user = db.query(models.User).filter(models.User.username == token_data.username).first()

    if not user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")

    if user is None:
        raise credentials_exception

    return user


@router.post("/logout")
async def logout(current_user: schemas.TokenData = Depends(get_current_user)):
    # Add the token to the set of revoked tokens
    revoked_tokens.add(current_user.username)
    return {"message": "Logout successful"}