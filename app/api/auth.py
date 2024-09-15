from fastapi import Depends, HTTPException,APIRouter
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
import os
from app.api.deps import get_db
from app.core.security import authenticate_user,create_access_token


router = APIRouter()

@router.post("/login")
def login(
    db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))),
    )
    return {"access_token":access_token,"token_type":"bearer","expires_in" : f"{os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")} minutes"}
