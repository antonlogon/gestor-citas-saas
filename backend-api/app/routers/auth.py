from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app import schemas
from app.core.security import create_access_token, verify_password
from app.crud import crud_cliente, crud_empleado
from app.database import get_db

# ==========================================
# ROUTER: AUTENTICACIÓN
# Flujo OAuth2 Password + JWT Bearer. Permite el login tanto de
# clientes como de empleados usando su email como identificador.
# ==========================================

router = APIRouter(
    tags=["Autenticación"],
)


@router.post("/login", response_model=schemas.Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Autentica a un usuario (cliente o empleado) y devuelve un token JWT.

    El campo `username` del formulario OAuth2 corresponde al email. Se busca
    primero en la tabla Cliente y, si no hay coincidencia, en la tabla Empleado.

    REGLA DE IDENTIDAD: el email identifica a UNA persona en TODA la plataforma.
    Es único entre clientes, entre empleados y de forma cruzada entre ambas
    tablas (UNIQUE en BD + guard en crud_usuario), así que este lookup no es
    ambiguo: a lo sumo hay una cuenta con ese email y `.first()` la resuelve.

    LIMITACIÓN Y EVOLUCIÓN (decisión de alcance, no un descuido): una misma
    persona NO puede darse de alta en dos clínicas distintas con el mismo
    correo. Si en el futuro hiciera falta soportarlo, la evolución natural es
    separar IDENTIDAD de PERTENENCIA: una tabla `usuarios` global (email +
    contraseña) y una tabla de pertenencia que la relacione con cada empresa y
    su rol, que es el modelo habitual de las plataformas multi-tenant con
    cuentas compartidas. Hoy el email vive en clientes/empleados, no en una
    entidad de identidad propia.
    """
    # El error es idéntico en todos los casos para no revelar si el
    # email existe (evita enumeración de usuarios).
    credenciales_invalidas = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Email o contraseña incorrectos.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    email = form_data.username

    # 1) Intentamos autenticar como CLIENTE.
    cliente = crud_cliente.get_cliente_by_email_global(db, email=email)
    if cliente is not None and verify_password(
        form_data.password, cliente.password_hash
    ):
        usuario, tipo = cliente, "cliente"
    else:
        # 2) Si no, intentamos como EMPLEADO.
        empleado = crud_empleado.get_empleado_by_email(db, email=email)
        if empleado is not None and verify_password(
            form_data.password, empleado.password_hash
        ):
            usuario, tipo = empleado, "empleado"
        else:
            raise credenciales_invalidas

    # Emitimos el token con los claims necesarios para reconstruir al usuario.
    access_token = create_access_token(
        data={"sub": usuario.email, "tipo": tipo, "id": usuario.id}
    )
    return schemas.Token(access_token=access_token, token_type="bearer")
