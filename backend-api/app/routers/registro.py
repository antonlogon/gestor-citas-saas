from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app import schemas
from app.core.security import create_access_token
from app.crud import crud_empresa, crud_registro, crud_usuario
from app.database import get_db

# ==========================================
# ROUTER: REGISTRO PÚBLICO (ONBOARDING DE TENANTS)
# Único endpoint —junto a /login— accesible SIN autenticación. Da de alta una
# clínica (tenant) y su primer administrador, rompiendo el círculo imposible
# de "para crear una empresa necesitas un ADMIN que solo puede existir dentro
# de una empresa". No se cuelga de /empresas, que es un recurso administrativo
# del tenant ya existente.
# ==========================================

router = APIRouter(
    prefix="/registro",
    tags=["Registro"],
)


@router.post(
    "/",
    response_model=schemas.RegistroResponse,
    status_code=status.HTTP_201_CREATED,
)
def registrar_clinica(
    datos: schemas.RegistroRequest,
    db: Session = Depends(get_db),
):
    """Registra una nueva clínica (tenant) y su primer administrador (ADMIN).

    Endpoint PÚBLICO. La empresa y el empleado se crean en una única
    transacción (ver crud_registro): nunca queda una empresa sin administrador.
    Devuelve directamente un token JWT válido para el administrador —con los
    mismos claims que /login— para evitar un inicio de sesión posterior.

    ADVERTENCIA DE SEGURIDAD (LIMITACIÓN CONOCIDA, NO UN DESCUIDO): al ser un
    endpoint público de creación, es una superficie de abuso: cualquiera puede
    registrar clínicas de forma ilimitada (sin límite de tasa, sin verificación
    de email ni CAPTCHA). Esta tarea NO implementa protección anti-abuso a
    propósito; debe añadirse (rate limiting, verificación de email, etc.) antes
    de exponer el servicio en producción.

    Args:
        datos: Datos validados de la empresa y de su administrador.
        db: Sesión de SQLAlchemy inyectada por dependencia.

    Returns:
        RegistroResponse con el token del administrador y la empresa y el
        empleado recién creados.

    Raises:
        HTTPException: 409 si el slug ya existe o si el email del administrador
            ya está registrado en la plataforma; 400 si los datos no se pueden
            persistir (p. ej. exceden los límites de la columna).
    """
    # Comprobaciones amables previas. La unicidad real la garantizan los índices
    # UNIQUE de la BD (slug de empresas, email de empleados), cuya violación se
    # captura más abajo por si hay una carrera entre la comprobación y el commit.
    if crud_empresa.get_empresa_by_slug(db, slug=datos.slug) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe una empresa con el slug '{datos.slug}'.",
        )
    # El email del administrador debe ser único en toda la plataforma.
    crud_usuario.verificar_email_disponible(db, email=datos.admin_email)

    try:
        empresa, empleado = crud_registro.registrar_empresa_con_admin(db, datos)
    except IntegrityError:
        # Carrera entre la comprobación previa y el commit: otro registro tomó el
        # mismo slug o el mismo email. Re-consultamos (ya con rollback hecho en
        # la capa CRUD) para distinguir la causa y dar un 409 preciso, nunca 500.
        if crud_empresa.get_empresa_by_slug(db, slug=datos.slug) is not None:
            detalle = f"Ya existe una empresa con el slug '{datos.slug}'."
        elif crud_usuario.email_en_uso(db, email=datos.admin_email) is not None:
            detalle = (
                f"El email '{datos.admin_email}' ya está registrado en la "
                "plataforma. Cada correo identifica a una única cuenta."
            )
        else:
            detalle = "No se pudo completar el registro por un conflicto de datos."
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detalle)
    except SQLAlchemyError:
        # Cualquier otro fallo de BD (ya con rollback hecho en la capa CRUD):
        # lo importante es que NO ha quedado ninguna empresa huérfana.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudieron guardar los datos del registro.",
        )

    # Reutilizamos exactamente los claims que emite /login (ver auth.login):
    # el administrador es un empleado, así que tipo="empleado".
    access_token = create_access_token(
        data={"sub": empleado.email, "tipo": "empleado", "id": empleado.id}
    )
    return schemas.RegistroResponse(
        access_token=access_token,
        empresa=schemas.Empresa.model_validate(empresa),
        empleado=schemas.Empleado.model_validate(empleado),
    )
