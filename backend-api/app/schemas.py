import re
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import EstadoCita, RolEmpleado

# Longitud mínima de contraseña. Hasta ahora el proyecto no validaba
# contraseñas en ningún punto; se fija un mínimo razonable y se aplica al
# menos en el registro público (única alta de credenciales sin autenticar).
MIN_PASSWORD_LENGTH = 8

# Un slug válido es la clave pública del tenant y viaja en URLs: solo letras
# minúsculas, números y guiones. La normalización previa (minúsculas, espacios
# a guiones) se hace en el validador antes de comprobar este patrón.
SLUG_REGEX = re.compile(r"^[a-z0-9-]+$")

# ==========================================
# SCHEMAS (Pydantic V2) - Contratos de la API
# Patrón: Base (campos comunes) -> Create (entrada) -> Read (salida con id)
# ==========================================


# ------------------ EMPRESA ------------------

class TramoHorario(BaseModel):
    """Un tramo de apertura dentro de un día: [inicio, fin] en 'HH:MM' 24h."""
    inicio: str
    fin: str


class EmpresaBase(BaseModel):
    nombre: str
    slug: str
    configuracion_estilo: Optional[str] = None


class EmpresaCreate(EmpresaBase):
    """Datos necesarios para registrar una nueva empresa (tenant)."""
    pass


class EmpresaUpdate(BaseModel):
    """Actualización parcial: solo se modifican los campos enviados."""
    nombre: Optional[str] = None
    slug: Optional[str] = None
    configuracion_estilo: Optional[str] = None


class Empresa(EmpresaBase):
    id: int
    # Horario de apertura semanal: 7 listas (índice 0=lunes ... 6=domingo); cada
    # una son los tramos de ese día y una lista vacía significa CERRADO. Viaja en
    # la salida para que los frontends no ofrezcan huecos fuera de horario.
    horario_apertura: List[List[TramoHorario]]

    # from_attributes permite construir el schema desde un objeto SQLAlchemy
    model_config = ConfigDict(from_attributes=True)


# ------------------ CLIENTE ------------------

class ClienteBase(BaseModel):
    nombre: str
    email: str
    telefono: str


class ClienteCreate(ClienteBase):
    # empresa_id NO se recibe: se deriva del usuario autenticado (token).
    password: str  # En texto plano solo en la entrada; se almacena hasheada


class ClienteUpdate(BaseModel):
    """Actualización parcial: solo se modifican los campos enviados."""
    nombre: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None


class Cliente(ClienteBase):
    id: int
    empresa_id: int

    model_config = ConfigDict(from_attributes=True)


# ------------------ EMPLEADO ------------------

class EmpleadoBase(BaseModel):
    nombre: str
    email: str
    especialidad: Optional[str] = None
    activo: bool = True
    # Rol dentro del tenant. Por defecto PERSONAL (mínimo privilegio) en el alta;
    # promover a ADMIN es una acción explícita. Solo un ADMIN puede fijarlo o
    # cambiarlo, porque el endpoint que lo usa está tras require_admin.
    rol: RolEmpleado = RolEmpleado.PERSONAL


class EmpleadoCreate(EmpleadoBase):
    # empresa_id NO se recibe: se deriva del usuario autenticado (token).
    password: str  # En texto plano solo en la entrada; se almacena hasheada


class EmpleadoUpdate(BaseModel):
    """Actualización parcial: solo se modifican los campos enviados."""
    nombre: Optional[str] = None
    especialidad: Optional[str] = None
    activo: Optional[bool] = None
    # Cambiar el rol es una acción de administración: el endpoint PUT /empleados
    # está protegido por require_admin. Ver la salvaguarda del último admin en
    # crud_empleado.update_empleado.
    rol: Optional[RolEmpleado] = None


class Empleado(EmpleadoBase):
    id: int
    empresa_id: int

    model_config = ConfigDict(from_attributes=True)


# ------------------ SERVICIO ------------------

class ServicioBase(BaseModel):
    nombre: str
    duracion_minutos: int
    precio: Decimal


class ServicioCreate(ServicioBase):
    # empresa_id NO se recibe: se deriva del usuario autenticado (token).
    pass


class ServicioUpdate(BaseModel):
    """Actualización parcial: solo se modifican los campos enviados."""
    nombre: Optional[str] = None
    duracion_minutos: Optional[int] = None
    precio: Optional[Decimal] = None


class Servicio(ServicioBase):
    id: int
    empresa_id: int

    model_config = ConfigDict(from_attributes=True)


# ------------------ CITA ------------------

class CitaBase(BaseModel):
    fecha_hora: datetime
    notas_ia: Optional[str] = None


class CitaCreate(CitaBase):
    # empresa_id NO se recibe: se deriva del usuario autenticado (token).
    cliente_id: int
    empleado_id: int
    servicio_id: int


class CitaUpdate(BaseModel):
    """Actualización parcial: reprogramar, cambiar estado o añadir notas."""
    fecha_hora: Optional[datetime] = None
    estado: Optional[EstadoCita] = None
    notas_ia: Optional[str] = None


class Cita(CitaBase):
    id: int
    empresa_id: int
    cliente_id: int
    empleado_id: int
    servicio_id: int
    estado: EstadoCita

    # Campos "aplanados" para el cliente: se rellenan en el endpoint a partir
    # de las relaciones (JOIN) para evitar que el móvil tenga que resolver IDs.
    servicio_nombre: Optional[str] = None
    empleado_nombre: Optional[str] = None
    cliente_nombre: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CitaResumen(BaseModel):
    """Recuentos agregados de citas (calculados en SQL) para los KPIs del panel.

    Se calculan sobre TODAS las citas del tenant, no sobre una página, para que
    los indicadores no dependan del limit/skip del listado.
    """
    total: int
    hoy: int          # citas de hoy EXCLUYENDO las canceladas (no ocupan agenda)
    pendientes: int
    confirmadas: int
    canceladas: int


# ------------------ AUTENTICACIÓN ------------------

class Token(BaseModel):
    """Respuesta del endpoint de login: token JWT y su tipo (bearer)."""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Datos (claims) que viajan dentro del JWT."""
    sub: str          # email del usuario
    tipo: str         # "cliente" o "empleado"
    id: int           # identificador del usuario en su tabla


# ------------------ REGISTRO PÚBLICO (ONBOARDING DE TENANTS) ------------------

class RegistroRequest(BaseModel):
    """Datos del alta pública de una clínica y su primer administrador.

    Reúne en un solo cuerpo los datos de la Empresa (tenant) y los de su primer
    Empleado, que se creará con rol ADMIN. Los prefijos `empresa_`/`admin_`
    evitan la ambigüedad entre el nombre de la clínica y el del administrador.
    """
    # --- Empresa (tenant) ---
    empresa_nombre: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=3, max_length=50)
    configuracion_estilo: Optional[str] = None
    # --- Administrador (primer empleado, rol ADMIN) ---
    admin_nombre: str = Field(..., min_length=1, max_length=100)
    admin_email: EmailStr
    admin_password: str = Field(..., min_length=MIN_PASSWORD_LENGTH)

    @field_validator("slug", mode="before")
    @classmethod
    def normalizar_y_validar_slug(cls, valor: object) -> object:
        """Normaliza el slug y valida su formato antes del resto de reglas.

        Pasa a minúsculas y convierte los espacios en guiones para admitir
        entradas como "Clínica Sonrisas" -> "clínica-sonrisas", y luego exige el
        patrón SLUG_REGEX para que no entren caracteres que rompan una URL (la
        "í" del ejemplo, por ejemplo, se rechaza). mode="before" garantiza que
        se ejecuta antes de las restricciones de longitud del Field.
        """
        if not isinstance(valor, str):
            return valor
        normalizado = valor.strip().lower().replace(" ", "-")
        if not SLUG_REGEX.fullmatch(normalizado):
            raise ValueError(
                "El slug solo admite letras minúsculas, números y guiones."
            )
        return normalizado


class RegistroResponse(Token):
    """Respuesta del registro: token del administrador + datos ya creados.

    Extiende Token (access_token + token_type) para que el cliente quede
    autenticado sin un login posterior, y adjunta la empresa y el empleado
    recién creados (este último expone rol=ADMIN).
    """
    empresa: Empresa
    empleado: Empleado


# ------------------ CHATBOT (ASISTENTE VIRTUAL) ------------------

class MensajeHistorial(BaseModel):
    """Un turno de la conversación (paciente o asistente)."""
    role: str
    content: str


class ChatRequest(BaseModel):
    """Conversación completa que el paciente envía al asistente virtual."""
    historial: List[MensajeHistorial]


class ChatResponse(BaseModel):
    """Respuesta generada por el asistente virtual."""
    respuesta: str
