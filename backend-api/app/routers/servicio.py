from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import schemas
from app.core.security import get_current_user, require_admin
from app.crud import crud_servicio
from app.database import get_db

# ==========================================
# ROUTER: SERVICIOS
# Capa de controladores: traduce HTTP <-> CRUD.
# Todas las operaciones quedan acotadas a la empresa (tenant) del
# usuario autenticado: el empresa_id sale del token, nunca del cliente.
#
# AUTORIZACIÓN: la LECTURA del catálogo es para cualquier usuario autenticado
# (empleados y clientes: la necesitan para reservar). La ESCRITURA (crear,
# reprecio y borrar servicios) se reserva a ADMIN: el catálogo incluye el
# PRECIO, una decisión de negocio, no una tarea diaria de recepción.
# ==========================================

router = APIRouter(
    prefix="/servicios",
    tags=["Servicios"],
)


@router.post("/", response_model=schemas.Servicio, status_code=status.HTTP_201_CREATED)
def crear_servicio(
    servicio: schemas.ServicioCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """Registra un nuevo servicio en la empresa del usuario autenticado. Reservado a ADMIN."""
    return crud_servicio.create_servicio(
        db, servicio=servicio, empresa_id=current_user.empresa_id
    )


@router.get("/", response_model=List[schemas.Servicio])
def listar_servicios(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Lista los servicios de la propia empresa, con paginación."""
    return crud_servicio.get_servicios(
        db, empresa_id=current_user.empresa_id, skip=skip, limit=limit
    )


@router.get("/{servicio_id}", response_model=schemas.Servicio)
def obtener_servicio(
    servicio_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Recupera un servicio de la propia empresa. Devuelve 404 si no existe."""
    db_servicio = crud_servicio.get_servicio(
        db, servicio_id=servicio_id, empresa_id=current_user.empresa_id
    )
    if db_servicio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ningún servicio con id {servicio_id}.",
        )
    return db_servicio


@router.put("/{servicio_id}", response_model=schemas.Servicio)
def actualizar_servicio(
    servicio_id: int,
    servicio: schemas.ServicioUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """Actualiza parcialmente un servicio de la propia empresa. Reservado a ADMIN. 404 si no existe."""
    db_servicio = crud_servicio.update_servicio(
        db,
        servicio_id=servicio_id,
        servicio=servicio,
        empresa_id=current_user.empresa_id,
    )
    if db_servicio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ningún servicio con id {servicio_id}.",
        )
    return db_servicio


@router.delete("/{servicio_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_servicio(
    servicio_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """Elimina un servicio de la propia empresa. Reservado a ADMIN. 404 si no existe."""
    db_servicio = crud_servicio.delete_servicio(
        db, servicio_id=servicio_id, empresa_id=current_user.empresa_id
    )
    if db_servicio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ningún servicio con id {servicio_id}.",
        )
