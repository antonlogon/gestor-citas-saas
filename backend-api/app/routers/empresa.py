from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import schemas
from app.core.security import require_admin, require_empleado
from app.crud import crud_empresa
from app.database import get_db

# ==========================================
# ROUTER: EMPRESAS
# La empresa ES el tenant: un usuario autenticado solo puede ver o
# modificar su PROPIA empresa (la de su token). Cualquier otro id se
# trata como inexistente (404) para no revelar otros tenants.
# ==========================================

router = APIRouter(
    prefix="/empresas",
    tags=["Empresas"],
)


@router.get("/", response_model=List[schemas.Empresa])
def listar_empresas(
    db: Session = Depends(get_db),
    current_user=Depends(require_empleado),
):
    """Devuelve únicamente la empresa del usuario autenticado."""
    empresa = crud_empresa.get_empresa(db, empresa_id=current_user.empresa_id)
    return [empresa] if empresa is not None else []


@router.get("/{empresa_id}", response_model=schemas.Empresa)
def obtener_empresa(
    empresa_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_empleado),
):
    """Recupera la propia empresa. Cualquier otro id devuelve 404."""
    if empresa_id != current_user.empresa_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ninguna empresa con id {empresa_id}.",
        )
    db_empresa = crud_empresa.get_empresa(db, empresa_id=empresa_id)
    if db_empresa is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ninguna empresa con id {empresa_id}.",
        )
    return db_empresa


@router.put("/{empresa_id}", response_model=schemas.Empresa)
def actualizar_empresa(
    empresa_id: int,
    empresa: schemas.EmpresaUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """Actualiza la propia empresa. Reservado a ADMIN. Otro id devuelve 404."""
    if empresa_id != current_user.empresa_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ninguna empresa con id {empresa_id}.",
        )
    db_empresa = crud_empresa.update_empresa(db, empresa_id=empresa_id, empresa=empresa)
    if db_empresa is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ninguna empresa con id {empresa_id}.",
        )
    return db_empresa


@router.delete("/{empresa_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_empresa(
    empresa_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """Elimina la propia empresa y sus datos asociados. Reservado a ADMIN.

    Otro id devuelve 404. Este era el vector de escalada: antes cualquier
    empleado podía borrar el tenant completo (FKs en CASCADE); ahora exige ADMIN.
    """
    if empresa_id != current_user.empresa_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ninguna empresa con id {empresa_id}.",
        )
    db_empresa = crud_empresa.delete_empresa(db, empresa_id=empresa_id)
    if db_empresa is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ninguna empresa con id {empresa_id}.",
        )
