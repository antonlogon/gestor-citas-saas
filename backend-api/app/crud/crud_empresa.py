from typing import List, Optional

from sqlalchemy.orm import Session

from app import models, schemas

# ==========================================
# CAPA CRUD: EMPRESA
# Lógica de acceso a datos. No conoce HTTP: devuelve objetos o None,
# y es el router quien decide qué código de estado responder.
# ==========================================


def get_empresa(db: Session, empresa_id: int) -> Optional[models.Empresa]:
    """Recupera una empresa por su ID.

    Args:
        db: Sesión de SQLAlchemy inyectada por dependencia.
        empresa_id: Identificador único de la empresa.

    Returns:
        La empresa encontrada o None si no existe.
    """
    return db.query(models.Empresa).filter(models.Empresa.id == empresa_id).first()


def get_empresa_by_slug(db: Session, slug: str) -> Optional[models.Empresa]:
    """Recupera una empresa por su slug (identificador público del tenant).

    Args:
        db: Sesión de SQLAlchemy.
        slug: Slug único de la empresa (ej. "clinica-sonrisas").

    Returns:
        La empresa encontrada o None si no existe.
    """
    return db.query(models.Empresa).filter(models.Empresa.slug == slug).first()


def get_empresas(db: Session, skip: int = 0, limit: int = 100) -> List[models.Empresa]:
    """Lista empresas con paginación.

    Args:
        db: Sesión de SQLAlchemy.
        skip: Número de registros a saltar (offset).
        limit: Número máximo de registros a devolver.

    Returns:
        Lista de empresas (puede estar vacía).
    """
    return db.query(models.Empresa).offset(skip).limit(limit).all()


def create_empresa(db: Session, empresa: schemas.EmpresaCreate) -> models.Empresa:
    """Crea una nueva empresa (tenant) en la base de datos.

    Args:
        db: Sesión de SQLAlchemy.
        empresa: Datos validados de la empresa a crear.

    Returns:
        La empresa recién creada, con su ID asignado por la BD.
    """
    db_empresa = models.Empresa(**empresa.model_dump())
    db.add(db_empresa)
    db.commit()
    db.refresh(db_empresa)
    return db_empresa


def update_empresa(
    db: Session, empresa_id: int, empresa: schemas.EmpresaUpdate
) -> Optional[models.Empresa]:
    """Actualiza parcialmente una empresa: solo los campos enviados.

    Args:
        db: Sesión de SQLAlchemy.
        empresa_id: Identificador de la empresa a actualizar.
        empresa: Campos a modificar (los no enviados se conservan).

    Returns:
        La empresa actualizada o None si no existe.
    """
    db_empresa = get_empresa(db, empresa_id)
    if db_empresa is None:
        return None

    # exclude_unset=True ignora los campos que el cliente no envió
    datos = empresa.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(db_empresa, campo, valor)

    db.commit()
    db.refresh(db_empresa)
    return db_empresa


def delete_empresa(db: Session, empresa_id: int) -> Optional[models.Empresa]:
    """Elimina una empresa y, por cascada en BD, sus datos asociados.

    Args:
        db: Sesión de SQLAlchemy.
        empresa_id: Identificador de la empresa a eliminar.

    Returns:
        La empresa eliminada o None si no existía.
    """
    db_empresa = get_empresa(db, empresa_id)
    if db_empresa is None:
        return None

    db.delete(db_empresa)
    db.commit()
    return db_empresa
