import copy
from typing import Optional

from sqlalchemy import Column, Integer, String, Boolean, Text, ForeignKey, Numeric, DateTime, Enum, JSON
from sqlalchemy.orm import relationship
import enum
from app.database import Base


# ==========================================
# HORARIO DE APERTURA (POR TENANT)
# El horario vive POR CLÍNICA (columna de Empresa), no como constantes: el
# sistema es multi-inquilino y unos horarios comunes contradirían esa premisa.
#
# FORMATO: lista de EXACTAMENTE 7 posiciones, indexadas igual que
# datetime.weekday() (0=lunes ... 6=domingo). Cada posición es la lista de TRAMOS
# de apertura de ese día; una lista VACÍA significa CERRADO. Cada tramo es un
# objeto {"inicio": "HH:MM", "fin": "HH:MM"} en 24h. El formato admite VARIOS
# tramos por día (p. ej. el cierre de mediodía) y días cerrados.
# ==========================================

# Tramos de un día laborable típico: mañana y tarde con cierre a mediodía.
_TRAMOS_LABORABLES = [
    {"inicio": "09:00", "fin": "14:00"},
    {"inicio": "16:00", "fin": "20:00"},
]

# Horario por defecto sembrado para las clínicas (existentes vía migración y
# nuevas vía el default de la columna): L-V mañana y tarde, S-D cerrado.
HORARIO_APERTURA_POR_DEFECTO = [
    _TRAMOS_LABORABLES,  # lunes
    _TRAMOS_LABORABLES,  # martes
    _TRAMOS_LABORABLES,  # miércoles
    _TRAMOS_LABORABLES,  # jueves
    _TRAMOS_LABORABLES,  # viernes
    [],                  # sábado (cerrado)
    [],                  # domingo (cerrado)
]


def horario_apertura_por_defecto() -> list:
    """Copia PROFUNDA y nueva del horario por defecto.

    Se usa como ``default`` de la columna JSON: debe devolver un objeto fresco en
    cada inserción para no compartir listas/dicts mutables entre filas (la
    trampa clásica del argumento por defecto mutable).
    """
    return copy.deepcopy(HORARIO_APERTURA_POR_DEFECTO)

# Definimos las opciones del ENUM para el estado de las citas
class EstadoCita(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    CONFIRMADA = "CONFIRMADA"
    CANCELADA = "CANCELADA"


# Rol del empleado DENTRO de su empresa (tenant). No es el "tipo" de usuario
# (Cliente vs Empleado, que va en el JWT), sino el nivel de privilegio del
# personal: ADMIN gestiona la empresa (alta/baja de personal, borrado del
# tenant, catálogo de servicios); PERSONAL hace el trabajo diario (clientes,
# citas y lectura del catálogo).
class RolEmpleado(str, enum.Enum):
    ADMIN = "ADMIN"
    PERSONAL = "PERSONAL"

# ==========================================
# ENTIDADES (Equivalente a @Entity en Java)
# ==========================================

class Empresa(Base):
    __tablename__ = "empresas"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    slug = Column(String(50), unique=True, nullable=False)
    configuracion_estilo = Column(Text, nullable=True)
    # Horario de apertura semanal del tenant (ver formato arriba). NOT NULL con
    # default de aplicación: toda empresa nace con el horario por defecto y no
    # existe (por ahora) endpoint para editarlo. La comprobación de que una cita
    # cabe en un tramo vive en crud_cita, como el resto de invariantes de agenda.
    horario_apertura = Column(JSON, nullable=False, default=horario_apertura_por_defecto)

    # Relaciones (Bidireccionales). passive_deletes=True delega el borrado en
    # cascada en la BD (las FKs son ON DELETE CASCADE): al borrar la empresa,
    # InnoDB elimina hijos y nietos. Sin esto, el ORM intentaría poner a NULL el
    # empresa_id (NOT NULL) de los hijos y el DELETE fallaría con IntegrityError.
    clientes = relationship("Cliente", back_populates="empresa", passive_deletes=True)
    empleados = relationship("Empleado", back_populates="empresa", passive_deletes=True)
    servicios = relationship("Servicio", back_populates="empresa", passive_deletes=True)
    citas = relationship("Cita", back_populates="empresa", passive_deletes=True)


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False)
    nombre = Column(String(100), nullable=False)
    # El email es la identidad de login: ÚNICO EN TODA LA PLATAFORMA (una
    # persona, una cuenta). Con eso el login deja de ser ambiguo entre tenants.
    # La unicidad cruzada clientes<->empleados se garantiza además en la capa de
    # aplicación (ver app/crud/crud_usuario.verificar_email_disponible).
    email = Column(String(100), nullable=False, unique=True)
    telefono = Column(String(20), nullable=False)
    password_hash = Column(String(255), nullable=False)

    empresa = relationship("Empresa", back_populates="clientes")
    # passive_deletes: al borrar el cliente, las citas se van por la cascada de
    # la BD (citas.cliente_id es ON DELETE CASCADE), sin nullificar desde el ORM.
    citas = relationship("Cita", back_populates="cliente", passive_deletes=True)


class Empleado(Base):
    __tablename__ = "empleados"

    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False)
    nombre = Column(String(100), nullable=False)
    # Ver nota en Cliente.email: identidad de login, única en toda la plataforma.
    email = Column(String(100), nullable=False, unique=True)
    especialidad = Column(String(100), nullable=True)
    activo = Column(Boolean, default=True)
    # Rol dentro del tenant. NOT NULL: todo empleado tiene un nivel de
    # privilegio explícito. El default de aplicación (PERSONAL) aplica al ALTA
    # de personal nuevo: se concede el mínimo privilegio y un ADMIN promueve
    # después si procede. Ver RolEmpleado y app/core/security.require_admin.
    rol = Column(Enum(RolEmpleado), nullable=False, default=RolEmpleado.PERSONAL)
    password_hash = Column(String(255), nullable=False)

    empresa = relationship("Empresa", back_populates="empleados")
    # passive_deletes: la cascada de la BD borra sus citas al borrar el empleado.
    citas = relationship("Cita", back_populates="empleado", passive_deletes=True)


class Servicio(Base):
    __tablename__ = "servicios"

    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False)
    nombre = Column(String(100), nullable=False)
    duracion_minutos = Column(Integer, nullable=False)
    precio = Column(Numeric(10, 2), nullable=False)

    empresa = relationship("Empresa", back_populates="servicios")
    # passive_deletes: la cascada de la BD borra sus citas al borrar el servicio.
    citas = relationship("Cita", back_populates="servicio", passive_deletes=True)


class Cita(Base):
    __tablename__ = "citas"

    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False)
    cliente_id = Column(Integer, ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False)
    empleado_id = Column(Integer, ForeignKey("empleados.id", ondelete="CASCADE"), nullable=False)
    servicio_id = Column(Integer, ForeignKey("servicios.id", ondelete="CASCADE"), nullable=False)
    fecha_hora = Column(DateTime, nullable=False)
    estado = Column(Enum(EstadoCita), default=EstadoCita.PENDIENTE)
    notas_ia = Column(Text, nullable=True)

    # Relaciones hacia los "padres"
    empresa = relationship("Empresa", back_populates="citas")
    cliente = relationship("Cliente", back_populates="citas")
    empleado = relationship("Empleado", back_populates="citas")
    servicio = relationship("Servicio", back_populates="citas")

    # Nombres "aplanados" de las relaciones. Se exponen como properties para que
    # Pydantic los recoja vía from_attributes en CUALQUIER endpoint (list, detalle
    # y POST), no solo en el listado. La guarda de None evita fallos si la relación
    # no está cargada o no existe. En el listado se precargan con joinedload
    # (crud_cita.get_citas) para no reintroducir el problema N+1.
    @property
    def cliente_nombre(self) -> Optional[str]:
        return self.cliente.nombre if self.cliente else None

    @property
    def empleado_nombre(self) -> Optional[str]:
        return self.empleado.nombre if self.empleado else None

    @property
    def servicio_nombre(self) -> Optional[str]:
        return self.servicio.nombre if self.servicio else None