from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Cookie
from fastapi.security import OAuth2PasswordBearer
from app.database import db

SECRET_KEY = "cemiterio-secret-mude-em-producao-2024"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)

def create_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def authenticate_user(login: str, senha: str):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM usuarios WHERE login=? AND ativo=1", (login,)
        ).fetchone()
    if not row:
        return None
    if not verify_password(senha, row["senha_hash"]):
        return None
    return dict(row)

def get_current_user(token: Optional[str] = Cookie(default=None, alias="access_token")):
    if not token:
        raise HTTPException(status_code=401, detail="Não autenticado")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Token inválido")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")
    with db() as conn:
        row = conn.execute("SELECT * FROM usuarios WHERE id=? AND ativo=1", (user_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    return dict(row)

def require_admin(user=Depends(get_current_user)):
    if user["perfil"] != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")
    return user

def require_operador(user=Depends(get_current_user)):
    if user["perfil"] not in ("admin", "operador"):
        raise HTTPException(status_code=403, detail="Acesso restrito a operadores")
    return user
