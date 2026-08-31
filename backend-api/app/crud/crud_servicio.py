from typing import List, Optional

from sqlalchemy.orm import Session

from app import models, schemas

# ==========================================
# CAPA CRUD: SERVICIO
# Lógica de acceso a datos. No conoce HTTP: devuelve objetos o None,
# y es el router quien decide qué código de estado responder.
#
# AISLAMIENTO MULTI-TENANT: todas las operaciones exigen empresa_id y
# filtran por él.
# ==========================================


def get_servicio(
    db: Session, servicio_id: int, empresa_id: int
) -> Optional[models.Servicio]:
    """Recupera un servicio por su ID, restringido a su empresa.

    Args:
        db: Sesión de SQLAlchemy inyectada por dependencia.
        servicio_id: Identificador único del servicio.
        empresa_id: Empresa (tenant) del usuario autenticado.

    Returns:
        El servicio encontrado o None si no existe o es de otra empresa.
    """
    return (
        db.query(models.Servicio)
        .filter(
            models.Servicio.id == servicio_id,
            models.Servicio.empresa_id == empresa_id,
        )
        .first()
    )


def get_servicios(
    db: Session,
    empresa_id: int,
    skip: int = 0,
    limit: int = 100,
) -> List[models.Servicio]:
    """Lista los servicios de una empresa con paginación.

    Args:
        db: Sesión de SQLAlchemy.
        empresa_id: Empresa (tenant) del usuario autenticado.
        skip: Número de registros a saltar (offset).
        limit: Número máximo de registros a devolver.

    Returns:
        Lista de servicios de esa empresa (puede estar vacía).
    """
    return (
        db.query(models.Servicio)
        .filter(models.Servicio.empresa_id == empresa_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def create_servicio(
    db: Session, servicio: schemas.ServicioCreate, empresa_id: int
) -> models.Servicio:
    """Crea un nuevo servicio en la empresa del usuario autenticado.

    Args:
        db: Sesión de SQLAlchemy.
        servicio: Datos validados del servicio a crear.
        empresa_id: Empresa (tenant) a la que se asigna el servicio.

    Returns:
        El servicio recién creado, con su ID asignado por la BD.
    """
    db_servicio = models.Servicio(**servicio.model_dump(), empresa_id=empresa_id)
    db.add(db_servicio)
    db.commit()
    db.refresh(db_servicio)
    return db_servicio


def update_servicio(
    db: Session, servicio_id: int, servicio: schemas.ServicioUpdate, empresa_id: int
) -> Optional[models.Servicio]:
    """Actualiza parcialmente un servicio de la propia empresa.

    Args:
        db: Sesión de SQLAlchemy.
        servicio_id: Identificador del servicio a actualizar.
        servicio: Campos a modificar (los no enviados se conservan).
        empresa_id: Empresa (tenant) del usuario autenticado.

    Returns:
        El servicio actualizado o None si no existe o es de otra empresa.
    """
    db_servicio = get_servicio(db, servicio_id, empresa_id)
    if db_servicio is None:
        return None

    # exclude_unset=True ignora los campos que el cliente no envió
    datos = servicio.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(db_servicio, campo, valor)

    db.commit()
    db.refresh(db_servicio)
    return db_servicio


def delete_servicio(
    db: Session, servicio_id: int, empresa_id: int
) -> Optional[models.Servicio]:
    """Elimina un servicio de la propia empresa (y sus citas por cascada).

    Args:
        db: Sesión de SQLAlchemy.
        servicio_id: Identificador del servicio a eliminar.
        empresa_id: Empresa (tenant) del usuario autenticado.

    Returns:
        El servicio eliminado o None si no existía o es de otra empresa.
    """
    db_servicio = get_servicio(db, servicio_id, empresa_id)
    if db_servicio is None:
        return None

    db.delete(db_servicio)
    db.commit()
    return db_servicio
