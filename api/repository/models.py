from sqlalchemy import Column, Integer, String, Boolean
from repository.database import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String)
    email = Column(String)
    password = Column(String)
    disabled = Column(Boolean)

class UserFeedback(Base):
    __tablename__ = 'user_feedback'
    username = Column(String, primary_key=True, index=True)
    query = Column(String)
    response = Column(String)
    feedback = Column(String)
    rating = Column(Integer)

# class ComplaintDetails(Base):
#     __tablename__ = 'complaint_details'
#     complaint_number = Column(String, primary_key=True, index=True)
#     company_name = Column(String)
#     sector_name = Column(String)
#     category_name = Column(String)
#     details = Column(String)