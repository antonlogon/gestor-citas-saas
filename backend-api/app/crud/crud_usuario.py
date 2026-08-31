from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app import models

# ==========================================
# CAPA CRUD: IDENTIDAD DE USUARIO (email único en la plataforma)
# El email identifica a UNA persona en TODO el sistema: no puede repetirse ni
# entre clientes, ni entre empleados, ni de forma cruzada entre ambas tablas.
#
# La BD garantiza la unicidad DENTRO de cada tabla (UNIQUE(email) en clientes y
# en empleados), pero NO la unicidad CRUZADA entre las dos: ese hueco se cierra
# aquí, en la capa de aplicación, y todos los caminos de alta/edición de email
# deben pasar por verificar_email_disponible antes de escribir.
# ==========================================


def email_en_uso(db: Session, email: str) -> Optional[str]:
    """Indica si un email ya está registrado en la plataforma (clientes o empleados).

    Consulta global (sin filtrar por empresa): la identidad de login es única
    para toda la plataforma, no por tenant.

    Args:
        db: Sesión de SQLAlchemy inyectada por dependencia.
        email: Correo electrónico a comprobar.

    Returns:
        "cliente" o "empleado" según en qué tabla exista ya el email, o None
        si está libre.
    """
    if db.query(models.Cliente).filter(models.Cliente.email == email).first():
        return "cliente"
    if db.query(models.Empleado).filter(models.Empleado.email == email).first():
        return "empleado"
    return None


def verificar_email_disponible(db: Session, email: str) -> None:
    """Exige que un email esté libre en toda la plataforma o lanza 409.

    Guard reutilizable para TODOS los caminos de alta y de cambio de email
    (registro, clientes, empleados). Centraliza la unicidad cruzada que la BD
    no puede imponer entre las tablas clientes y empleados, y devuelve un 409
    con mensaje claro en lugar de dejar que aflore un IntegrityError como 500.

    Args:
        db: Sesión de SQLAlchemy.
        email: Correo electrónico que se pretende usar.

    Raises:
        HTTPException: 409 CONFLICT si el email ya pertenece a otra cuenta.
    """
    if email_en_uso(db, email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"El email '{email}' ya está registrado en la plataforma. "
                "Cada correo identifica a una única cuenta."
            ),
        )
