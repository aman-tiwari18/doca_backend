from fastapi import FastAPI
from router import search, rca, basic, categoryanalysis, feedback
# , rca, bulk, priority
from router import authentication, user
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
import warnings
from repository import models
from repository.database import engine
from repository.JWTToken import SECRET_KEY

# Filter out the warnings you want to suppress
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

# Configure CORS
origins = ["http://localhost:3001", "http://127.0.0.1:3001", "http://localhost:3000", "http://127.0.0.1:3000"]
app=FastAPI(
    # expose documentation at /docs
    root_path="/consumer_api",
)

# Add the session middleware to the app
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

models.Base.metadata.create_all(engine)

app.include_router(authentication.router)
app.include_router(user.router)
app.include_router(search.router)
app.include_router(rca.router)
app.include_router(basic.router)
app.include_router(categoryanalysis.router)
app.include_router(feedback.router)
# app.include_router(login.router)



