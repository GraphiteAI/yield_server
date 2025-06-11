from yield_server.utils.auth_utils import validate_jwt
from typing import Optional
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt


error_security = HTTPBearer() # NOTE: this will raise an HTTPException if no bearer token is provided
non_error_security = HTTPBearer(auto_error=False) # NOTE: this will not raise an error

def get_user_id_from_jwt(
    bearer_token: Optional[HTTPAuthorizationCredentials] = Depends(non_error_security)  
) -> Optional[str]:
    '''
    Returns the user ID from the JWT token if given. If not return None.
    '''
    if bearer_token is None:
        return None
    try:
        payload = validate_jwt(bearer_token.credentials)
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="JWT token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid JWT token")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def enforce_user_id_from_jwt(
    bearer_token: HTTPAuthorizationCredentials = Depends(error_security)  
) -> str:
    '''
    Enforces the user ID from the JWT token.
    '''
    try:
        payload = validate_jwt(bearer_token.credentials)
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="JWT token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid JWT token")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def validate_user_jwt(
    bearer_token: Optional[HTTPAuthorizationCredentials] = Depends(error_security)  
) -> Optional[str]:
    '''
    Validates the JWT token and returns the encoded JWT
    '''
    try:
        validate_jwt(bearer_token.credentials)
        return bearer_token.credentials
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="JWT token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid JWT token")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))