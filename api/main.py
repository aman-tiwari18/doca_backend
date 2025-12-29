from fastapi import FastAPI
from router import search, rca, basic, categoryanalysis, feedback
# , rca, bulk, priority
from router import authentication, user
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
import warnings
from repository import models
from repository.database import engine
from starlette.middleware.sessions import SessionMiddleware

# Filter out the warnings you want to suppress
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

# Configure CORS
SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
origins = ["*"]
app=FastAPI(
    # expose documentation at /docs
    root_path="/consumer_api",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Add the session middleware to the app
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

models.Base.metadata.create_all(engine)

app.include_router(authentication.router)
app.include_router(user.router)
app.include_router(search.router)
app.include_router(rca.router)
app.include_router(basic.router)
app.include_router(categoryanalysis.router)
app.include_router(feedback.router)
# app.include_router(login.router)



