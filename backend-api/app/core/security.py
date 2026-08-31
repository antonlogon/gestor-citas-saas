from datetime import datetime, timedelta, timezone
from typing import Optional, Union

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app import models
from app.core.config import settings
from app.database import get_db

# ==========================================
# CORE DE SEGURIDAD
# Fuente única para: hashing de contraseñas (Bcrypt), emisión y
# validación de tokens JWT, y resolución del usuario autenticado.
# ==========================================

# Contexto de hashing. bcrypt es el algoritmo recomendado; passlib gestiona
# el salt de forma transparente y permite marcar esquemas como obsoletos.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Esquema OAuth2: FastAPI extraerá el token del header "Authorization: Bearer".
# tokenUrl apunta al endpoint de login (ver app/routers/auth.py).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


# ------------------ CONTRASEÑAS ------------------

def hash_password(password: str) -> str:
    """Genera un hash Bcrypt de la contraseña, apto para almacenar en BD."""
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Comprueba si una contraseña en claro coincide con el hash almacenado."""
    return pwd_context.verify(password, password_hash)


# ------------------ TOKENS JWT ------------------

def create_access_token(
    data: dict, expires_delta: Optional[timedelta] = None
) -> str:
    """Genera un JWT firmado con la información (claims) proporcionada.

    Args:
        data: Claims a incluir en el token (p. ej. sub, tipo, id).
        expires_delta: Duración personalizada; por defecto usa la de settings.

    Returns:
        El token JWT codificado como string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


# ------------------ USUARIO AUTENTICADO ------------------

# Tipo del usuario resuelto: puede ser un Cliente o un Empleado.
UsuarioAutenticado = Union[models.Cliente, models.Empleado]


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> UsuarioAutenticado:
    """Decodifica el JWT y devuelve el objeto de usuario (Cliente o Empleado).

    Se usará como dependencia (`Depends(get_current_user)`) para proteger
    endpoints. Lanza 401 si el token es inválido, ha expirado o el usuario
    ya no existe.
    """
    credenciales_invalidas = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        email: Optional[str] = payload.get("sub")
        tipo: Optional[str] = payload.get("tipo")
        user_id: Optional[int] = payload.get("id")
        if email is None or tipo not in ("cliente", "empleado") or user_id is None:
            raise credenciales_invalidas
    except JWTError:
        raise credenciales_invalidas

    # Resolvemos el usuario en la tabla correcta según el claim "tipo".
    modelo = models.Cliente if tipo == "cliente" else models.Empleado
    usuario = db.query(modelo).filter(modelo.id == user_id).first()
    if usuario is None:
        raise credenciales_invalidas

    return usuario


# ------------------ AUTORIZACIÓN POR ROL (RBAC) ------------------
# La autorización tiene DOS niveles independientes:
#   1) Tipo de usuario (claim "tipo" del JWT): un Cliente tiene acceso muy
#      limitado (su perfil, el catálogo de servicios y sus propias citas);
#      un Empleado es personal de la empresa. -> require_empleado
#   2) Rol del empleado dentro del tenant (models.RolEmpleado, leído de la BD,
#      NO del token): ADMIN administra la empresa (empresas, personal y
#      catálogo de servicios); PERSONAL hace el trabajo diario (clientes y
#      citas). -> require_admin
# El rol se resuelve del objeto recargado por get_current_user en CADA petición
# y NUNCA se cachea en el JWT: así, degradar o desactivar a alguien surte efecto
# de inmediato, sin esperar a que caduque su token.

def es_empleado(usuario: UsuarioAutenticado) -> bool:
    """True si el usuario autenticado es personal de la empresa (Empleado)."""
    return isinstance(usuario, models.Empleado)


def es_cliente(usuario: UsuarioAutenticado) -> bool:
    """True si el usuario autenticado es un Cliente (paciente)."""
    return isinstance(usuario, models.Cliente)


def es_admin(usuario: UsuarioAutenticado) -> bool:
    """True si el usuario es un Empleado con rol ADMIN.

    Comprueba primero que sea Empleado (un Cliente nunca tiene rol) y luego
    su columna `rol`, que se lee del objeto recargado de la BD.
    """
    return isinstance(usuario, models.Empleado) and usuario.rol == models.RolEmpleado.ADMIN


def require_empleado(
    current_user: UsuarioAutenticado = Depends(get_current_user),
) -> models.Empleado:
    """Dependencia que exige que el usuario sea un Empleado (de cualquier rol).

    Los clientes reciben 403 Forbidden. Blinda el trabajo diario del personal
    (gestión de clientes y citas, lectura de empresas, empleados y servicios)
    que un cliente no debe realizar.
    """
    if not es_empleado(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acción reservada al personal de la empresa (empleados).",
        )
    return current_user


def require_cliente(
    current_user: UsuarioAutenticado = Depends(get_current_user),
) -> models.Cliente:
    """Dependencia que exige que el usuario sea un Cliente (paciente).

    Simétrica a require_empleado. Los empleados reciben 403 Forbidden. Es
    imprescindible allí donde el código asume que `current_user` es un paciente
    y usa su id como cliente_id: los ids COLISIONAN entre las tablas clientes y
    empleados (el cliente 1 y el empleado 1 son personas distintas), así que sin
    esta guarda un empleado operaría sobre las citas del cliente con su mismo id.
    """
    if not es_cliente(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "El asistente virtual es solo para pacientes. El personal debe "
                "usar la aplicación de escritorio."
            ),
        )
    return current_user


def require_admin(
    current_user: UsuarioAutenticado = Depends(get_current_user),
) -> models.Empleado:
    """Dependencia que exige que el usuario sea un Empleado con rol ADMIN.

    Tanto los clientes como los empleados con rol PERSONAL reciben 403. Blinda
    las acciones de administración del tenant: alta/edición/borrado de la
    empresa y del personal, y gestión del catálogo de servicios. El rol se lee
    del objeto recargado en la petición (ver get_current_user), no del JWT.
    """
    if not es_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acción reservada a administradores de la empresa (rol ADMIN).",
        )
    return current_user
