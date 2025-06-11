'''
This middleware is used to manage admin actions. 
Please regularly rotate the admin key.
'''

from dotenv import load_dotenv
import os
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

load_dotenv(override=True)

ADMIN_KEY = os.getenv("ADMIN_KEY")

security = HTTPBearer() # NOTE: this will raise an HTTPException if no bearer token is provided

def validate_admin_key(
    bearer_token: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> bool:
    if bearer_token is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if bearer_token.credentials != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True