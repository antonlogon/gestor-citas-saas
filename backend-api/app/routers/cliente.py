from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import schemas
from app.core.security import es_empleado, get_current_user, require_empleado
from app.crud import crud_cliente, crud_usuario
from app.database import get_db

# ==========================================
# ROUTER: CLIENTES
# Capa de controladores: traduce HTTP <-> CRUD.
# Aislamiento por tenant (empresa_id del token) + autorización por rol:
#   - Empleado (personal): CRUD completo sobre los clientes de su empresa.
#   - Cliente: SOLO puede hacer GET de su propio perfil.
# ==========================================

router = APIRouter(
    prefix="/clientes",
    tags=["Clientes"],
)


@router.post("/", response_model=schemas.Cliente, status_code=status.HTTP_201_CREATED)
def crear_cliente(
    cliente: schemas.ClienteCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_empleado),
):
    """Registra un nuevo cliente en la empresa. Solo personal (empleados)."""
    # El email identifica una única cuenta en toda la plataforma (clientes y
    # empleados), no solo dentro de esta empresa.
    crud_usuario.verificar_email_disponible(db, email=cliente.email)
    return crud_cliente.create_cliente(
        db, cliente=cliente, empresa_id=current_user.empresa_id
    )


@router.get("/", response_model=List[schemas.Cliente])
def listar_clientes(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user=Depends(require_empleado),
):
    """Lista los clientes de la propia empresa. Solo personal (empleados)."""
    return crud_cliente.get_clientes(
        db, empresa_id=current_user.empresa_id, skip=skip, limit=limit
    )


@router.get("/me", response_model=schemas.Cliente)
def obtener_mi_perfil(current_user=Depends(get_current_user)):
    """Devuelve el perfil del cliente autenticado (a partir del token).

    Pensado para que la app móvil obtenga sus propios datos (nombre, email...)
    sin conocer de antemano su id. Debe declararse ANTES de `/{cliente_id}`
    para que la ruta literal "me" no se interprete como un id.
    """
    if es_empleado(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este endpoint es solo para clientes.",
        )
    return current_user


@router.get("/{cliente_id}", response_model=schemas.Cliente)
def obtener_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Recupera un cliente.

    - Empleado: cualquier cliente de su empresa.
    - Cliente: únicamente su propio perfil (otro id -> 403).
    """
    if not es_empleado(current_user) and current_user.id != cliente_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo puedes consultar tu propio perfil.",
        )
    db_cliente = crud_cliente.get_cliente(
        db, cliente_id=cliente_id, empresa_id=current_user.empresa_id
    )
    if db_cliente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ningún cliente con id {cliente_id}.",
        )
    return db_cliente


@router.put("/{cliente_id}", response_model=schemas.Cliente)
def actualizar_cliente(
    cliente_id: int,
    cliente: schemas.ClienteUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_empleado),
):
    """Actualiza parcialmente un cliente. Solo personal (empleados)."""
    db_cliente = crud_cliente.get_cliente(
        db, cliente_id=cliente_id, empresa_id=current_user.empresa_id
    )
    if db_cliente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ningún cliente con id {cliente_id}.",
        )
    # Si cambia el email, no puede chocar con ninguna otra cuenta de la
    # plataforma (cliente o empleado, en cualquier empresa).
    if cliente.email is not None and cliente.email != db_cliente.email:
        crud_usuario.verificar_email_disponible(db, email=cliente.email)
    return crud_cliente.update_cliente(
        db, cliente_id=cliente_id, cliente=cliente, empresa_id=current_user.empresa_id
    )


@router.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_empleado),
):
    """Elimina un cliente de la propia empresa. Solo personal (empleados)."""
    db_cliente = crud_cliente.delete_cliente(
        db, cliente_id=cliente_id, empresa_id=current_user.empresa_id
    )
    if db_cliente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe ningún cliente con id {cliente_id}.",
        )
