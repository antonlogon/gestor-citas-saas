from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import schemas
from app.core.security import require_admin, require_empleado
from app.crud import crud_empleado, crud_usuario
from app.database import get_db

# ==========================================
# ROUTER: EMPLEADOS
# Capa de controladores: traduce HTTP <-> CRUD.
# Todas las operaciones quedan acotadas a la empresa (tenant) del
# usuario autenticado: el empresa_id sale del token, nunca del cliente.
# ==========================================

router = APIRouter(
    prefix="/empleados",
    tags=["Empleados"],
)


@router.post("/", response_model=schemas.Empleado, status_code=status.HTTP_201_CREATED)
def crear_empleado(
    empleado: schemas.EmpleadoCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """Registra un nuevo empleado en la empresa del usuario autenticado.

    Reservado a ADMIN. Si no se envía `rol`, el empleado se crea como PERSONAL
    (mínimo privilegio).
    """
    # El email identifica una única cuenta en toda la plataforma (clientes y
    # empleados): rechaza el alta si ya está en uso.
    crud_usuario.verificar_email_disponible(db, email=empleado.email)
    return crud_empleado.create_empleado(
        db, empleado=empleado, empresa_id=current_user.empresa_id
    )


@router.get("/", response_model=List[schemas.Empleado])
def listar_empleados(
    skip: int = 0,
    limit: int = 100,
    solo_activos: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(require_empleado),
):
    """Lista los empleados de la propia empresa, con paginación y filtro de activos."""
    return crud_empleado.get_empleados(
        db,
        empresa_id=current_user.empresa_id,
        skip=skip,
        limit=limit,
        solo_activos=solo_activos,
    )


@router.get("/{empleado_id}", response_model=schemas.Empleado)
def obtener_empleado(
    empleado_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_empleado),
):
    """Recupera un empleado de la propia empresa. Devuelve 404 si no existe."""
    db_empleado = crud_empleado.get_empleado(
        db, empleado_id=empleado_id, empresa_id=current_user.empresa_id
    )
    if db_empleado is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ningún empleado con id {empleado_id}.",
        )
    return db_empleado


@router.put("/{empleado_id}", response_model=schemas.Empleado)
def actualizar_empleado(
    empleado_id: int,
    empleado: schemas.EmpleadoUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """Actualiza parcialmente un empleado de la propia empresa. Reservado a ADMIN.

    Devuelve 404 si no existe y 409 CONFLICT si la modificación (degradar a
    PERSONAL o desactivar) dejaría a la empresa sin ningún administrador activo.
    """
    try:
        db_empleado = crud_empleado.update_empleado(
            db,
            empleado_id=empleado_id,
            empleado=empleado,
            empresa_id=current_user.empresa_id,
        )
    except crud_empleado.UltimoAdminError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        )
    if db_empleado is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ningún empleado con id {empleado_id}.",
        )
    return db_empleado


@router.delete("/{empleado_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_empleado(
    empleado_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """Elimina un empleado de la propia empresa. Reservado a ADMIN.

    Devuelve 404 si no existe y 409 CONFLICT si borrarlo dejaría a la empresa
    sin ningún administrador activo.
    """
    try:
        db_empleado = crud_empleado.delete_empleado(
            db, empleado_id=empleado_id, empresa_id=current_user.empresa_id
        )
    except crud_empleado.UltimoAdminError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        )
    if db_empleado is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ningún empleado con id {empleado_id}.",
        )
