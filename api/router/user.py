from fastapi import APIRouter, Depends
from typing import List
from sqlalchemy.orm import Session
from repository import schemas, models, database
from repository.hashing import Hash
from fastapi.security import OAuth2PasswordBearer
from typing import Annotated
from router.authentication import get_current_user
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")




get_db = database.get_db
router = APIRouter(
    tags=['Users']
)

@router.post('/create_user/', response_model=schemas.ShowUser)
async def create_user(token : Annotated[str, Depends(oauth2_scheme)], request: schemas.User, db: Session = Depends(get_db)):
    
    user = await get_current_user(token, db)
    user = user.username.lower()
    
    new_user = models.User(username=request.username.lower(), email=request.email, password=Hash.hash(request.password), disabled=request.disabled)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.get('/get_all_users/', response_model=List[schemas.ShowUser])
async def show_all(token : Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(get_db)):
    
    user = await get_current_user(token, db)
    user = user.username.lower()
    
    users = db.query(models.User).all()
    return users


# @router.post('/save_user_feedback/')
# async def save_user_feedback(feedback: schemas.UserFeedback, db: Session = Depends(get_db)):
    

#     new_feedback = models.UserFeedback(username = feedback.username, query = feedback.query, response = feedback.response, feedback=feedback.feedback, rating=feedback.rating)
#     # create table is not existing
#     models.UserFeedback.__table__.create(bind=database.engine, checkfirst=True)
#     db.add(new_feedback)
#     db.commit()
#     db.refresh(new_feedback)
#     return {"message": "Feedback saved successfully"}

# @router.get('/get_user_feedback/{username}', response_model=List[schemas.UserFeedback])
# def get_user_feedback(username: str, db: Session = Depends(get_db)):
#     feedbacks = db.query(models.UserFeedback).filter(models.UserFeedback.username == username).all()
#     return feedbacks