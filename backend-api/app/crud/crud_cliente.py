from typing import List, Optional

from sqlalchemy.orm import Session

from app import models, schemas
from app.core.security import hash_password

# ==========================================
# CAPA CRUD: CLIENTE
# Lógica de acceso a datos. No conoce HTTP: devuelve objetos o None,
# y es el router quien decide qué código de estado responder.
#
# AISLAMIENTO MULTI-TENANT: salvo el lookup global de login, todas las
# operaciones exigen empresa_id y filtran por él, de modo que un usuario
# jamás puede leer ni modificar clientes de otra empresa.
# ==========================================


def get_cliente(
    db: Session, cliente_id: int, empresa_id: int
) -> Optional[models.Cliente]:
    """Recupera un cliente por su ID, restringido a su empresa.

    Args:
        db: Sesión de SQLAlchemy inyectada por dependencia.
        cliente_id: Identificador único del cliente.
        empresa_id: Empresa (tenant) del usuario autenticado.

    Returns:
        El cliente encontrado o None si no existe o es de otra empresa.
    """
    return (
        db.query(models.Cliente)
        .filter(
            models.Cliente.id == cliente_id,
            models.Cliente.empresa_id == empresa_id,
        )
        .first()
    )


def get_cliente_by_email_global(db: Session, email: str) -> Optional[models.Cliente]:
    """Busca un cliente por su email en toda la plataforma.

    USO EXCLUSIVO DEL LOGIN: es el único punto donde todavía no hay un usuario
    autenticado del que derivar la empresa. El email es ÚNICO en toda la
    plataforma (UNIQUE en BD + unicidad cruzada en crud_usuario), así que a lo
    sumo hay una coincidencia y `.first()` la devuelve sin ambigüedad.

    Args:
        db: Sesión de SQLAlchemy.
        email: Correo electrónico a buscar.

    Returns:
        El cliente encontrado o None si no existe.
    """
    return db.query(models.Cliente).filter(models.Cliente.email == email).first()


def get_clientes(
    db: Session,
    empresa_id: int,
    skip: int = 0,
    limit: int = 100,
) -> List[models.Cliente]:
    """Lista los clientes de una empresa con paginación.

    Args:
        db: Sesión de SQLAlchemy.
        empresa_id: Empresa (tenant) del usuario autenticado.
        skip: Número de registros a saltar (offset).
        limit: Número máximo de registros a devolver.

    Returns:
        Lista de clientes de esa empresa (puede estar vacía).
    """
    return (
        db.query(models.Cliente)
        .filter(models.Cliente.empresa_id == empresa_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def create_cliente(
    db: Session, cliente: schemas.ClienteCreate, empresa_id: int
) -> models.Cliente:
    """Crea un nuevo cliente en la empresa del usuario autenticado.

    Args:
        db: Sesión de SQLAlchemy.
        cliente: Datos validados del cliente a crear.
        empresa_id: Empresa (tenant) a la que se asigna el cliente.

    Returns:
        El cliente recién creado, con su ID asignado por la BD.
    """
    datos = cliente.model_dump(exclude={"password"})
    db_cliente = models.Cliente(
        **datos, empresa_id=empresa_id, password_hash=hash_password(cliente.password)
    )
    db.add(db_cliente)
    db.commit()
    db.refresh(db_cliente)
    return db_cliente


def update_cliente(
    db: Session, cliente_id: int, cliente: schemas.ClienteUpdate, empresa_id: int
) -> Optional[models.Cliente]:
    """Actualiza parcialmente un cliente de la propia empresa.

    Args:
        db: Sesión de SQLAlchemy.
        cliente_id: Identificador del cliente a actualizar.
        cliente: Campos a modificar (los no enviados se conservan).
        empresa_id: Empresa (tenant) del usuario autenticado.

    Returns:
        El cliente actualizado o None si no existe o es de otra empresa.
    """
    db_cliente = get_cliente(db, cliente_id, empresa_id)
    if db_cliente is None:
        return None

    # exclude_unset=True ignora los campos que el cliente no envió
    datos = cliente.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(db_cliente, campo, valor)

    db.commit()
    db.refresh(db_cliente)
    return db_cliente


def delete_cliente(
    db: Session, cliente_id: int, empresa_id: int
) -> Optional[models.Cliente]:
    """Elimina un cliente de la propia empresa (y sus citas por cascada).

    Args:
        db: Sesión de SQLAlchemy.
        cliente_id: Identificador del cliente a eliminar.
        empresa_id: Empresa (tenant) del usuario autenticado.

    Returns:
        El cliente eliminado o None si no existía o es de otra empresa.
    """
    db_cliente = get_cliente(db, cliente_id, empresa_id)
    if db_cliente is None:
        return None

    db.delete(db_cliente)
    db.commit()
    return db_cliente
