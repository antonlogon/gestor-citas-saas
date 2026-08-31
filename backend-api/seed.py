"""Script de SEED: carga datos de prueba en la base de datos.

Crea DOS empresas (tenants) independientes, cada una con sus clientes,
empleados, servicios y una cita. Tener dos tenants permite comprobar el
aislamiento: un usuario de la empresa A no debe poder ver ni tocar datos
de la empresa B.

Las contraseñas se hashean con Bcrypt a través de la capa CRUD, igual que
en la API real.

Uso:
    python seed.py

Es idempotente: si las empresas de prueba ya existen, no duplica nada.
"""
import sys
from datetime import datetime, time, timedelta

from app.database import SessionLocal
from app.crud import (
    crud_cita,
    crud_cliente,
    crud_empleado,
    crud_empresa,
    crud_servicio,
)
from app import schemas
from app.models import Cita, EstadoCita, RolEmpleado
from sqlalchemy import text

# Contraseña común para poder probar el login fácilmente.
PASSWORD_DEMO = "password123"

# ==========================================================================
# CATÁLOGO DE LA CLÍNICA MÉDICA (Empresa A)
# Datos de ejemplo coherentes: cada servicio pertenece a la especialidad de
# algún profesional, y las duraciones y precios son plausibles. Todos los
# correos acaban en @demo.com y comparten PASSWORD_DEMO.
# ==========================================================================

# (nombre, email, especialidad)
ESPECIALISTAS = [
    ("Dr. Javier Soler",    "javier@demo.com",  "Dermatología"),
    ("Dra. Elena Navarro",  "elena@demo.com",   "Pediatría"),
    ("Dr. Tomás Herrera",   "tomas@demo.com",   "Traumatología"),
    ("Dra. Marta Gil",      "marta@demo.com",   "Ginecología"),
]

# (nombre, duración en minutos, precio, especialidad a la que pertenece)
SERVICIOS = [
    ("Empaste dental",           45,  70.00, "Odontología"),
    ("Revisión dermatológica",   30,  60.00, "Dermatología"),
    ("Extirpación de lunar",     45, 120.00, "Dermatología"),
    ("Revisión pediátrica",      30,  50.00, "Pediatría"),
    ("Vacunación infantil",      15,  25.00, "Pediatría"),
    ("Consulta traumatología",   30,  65.00, "Traumatología"),
    ("Infiltración",             30,  90.00, "Traumatología"),
    ("Revisión ginecológica",    40,  80.00, "Ginecología"),
    ("Ecografía",                30,  75.00, "Ginecología"),
]

# (nombre, email, teléfono)
PACIENTES = [
    ("Carlos Molina",  "carlos@demo.com",  "600222333"),
    ("Lucía Ferrer",   "lucia@demo.com",   "600333444"),
    ("Miguel Ortega",  "miguel@demo.com",  "600444555"),
    ("Paula Sanz",     "paula@demo.com",   "600555666"),
    ("David Romero",   "david@demo.com",   "600666777"),
    ("Nuria Castro",   "nuria@demo.com",   "600777888"),
    ("Sergio Ibáñez",  "sergio@demo.com",  "600888999"),
]


def _proxima_apertura() -> datetime:
    """Primer día LABORABLE (L-V) a partir de mañana, a las 10:00.

    La cita de ejemplo se crea vía create_cita, que ahora exige que la cita quepa
    en el horario de apertura (por defecto L-V 09:00-14:00 y 16:00-20:00). Las
    10:00 de un día laborable caen dentro del tramo de mañana, así que el seed no
    depende de en qué día de la semana se ejecute (mañana podría ser sábado).
    """
    fecha = (datetime.now() + timedelta(days=1)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    while fecha.weekday() >= 5:  # 5=sábado, 6=domingo
        fecha += timedelta(days=1)
    return fecha


def sembrar_empresa(db, nombre, slug, cliente, empleado, servicio) -> dict:
    """Crea una empresa con un cliente, un empleado, un servicio y una cita.

    La empresa nace con el horario de apertura por defecto (lo aplica el default
    de la columna Empresa.horario_apertura), así que aquí no hay que sembrarlo
    explícitamente: L-V mañana y tarde con cierre a mediodía, S-D cerrado.
    """
    empresa = crud_empresa.create_empresa(
        db,
        schemas.EmpresaCreate(nombre=nombre, slug=slug, configuracion_estilo=None),
    )
    print(f"Empresa creada: {empresa.nombre} (id={empresa.id})")

    c = crud_cliente.create_cliente(
        db,
        schemas.ClienteCreate(
            nombre=cliente[0], email=cliente[1], telefono=cliente[2],
            password=PASSWORD_DEMO,
        ),
        empresa_id=empresa.id,
    )
    print(f"  Cliente creado:  {c.email} (id={c.id})")

    # El empleado principal de cada tenant se siembra como ADMIN: es quien
    # administra la empresa (personal, catálogo, la propia empresa).
    e = crud_empleado.create_empleado(
        db,
        schemas.EmpleadoCreate(
            nombre=empleado[0], email=empleado[1], especialidad=empleado[2],
            activo=True, rol=RolEmpleado.ADMIN, password=PASSWORD_DEMO,
        ),
        empresa_id=empresa.id,
    )
    print(f"  Empleado creado: {e.email} (id={e.id}, rol={e.rol.value})")

    s = crud_servicio.create_servicio(
        db,
        schemas.ServicioCreate(
            nombre=servicio[0], duracion_minutos=servicio[1], precio=servicio[2],
        ),
        empresa_id=empresa.id,
    )
    print(f"  Servicio creado: {s.nombre} (id={s.id})")

    cita = crud_cita.create_cita(
        db,
        schemas.CitaCreate(
            fecha_hora=_proxima_apertura(),
            notas_ia=None,
            cliente_id=c.id, empleado_id=e.id, servicio_id=s.id,
        ),
        empresa_id=empresa.id,
    )
    print(f"  Cita creada:     id={cita.id}")
    return {"empresa": empresa, "cliente": c, "empleado": e, "servicio": s, "cita": cita}



# ==========================================================================
# GENERACIÓN DE AGENDA DE EJEMPLO
# ==========================================================================

def _dias_laborables(desde: datetime, cuantos: int, hacia_atras: bool = False):
    """Devuelve `cuantos` días laborables (L-V) a partir de `desde`."""
    dias, fecha, paso = [], desde, timedelta(days=-1 if hacia_atras else 1)
    while len(dias) < cuantos:
        fecha += paso
        if fecha.weekday() < 5:
            dias.append(fecha)
    return dias


def _huecos_del_dia(dia: datetime):
    """Horas de inicio válidas dentro del horario por defecto (L-V).

    Se generan en pasos de 30 min sobre los dos tramos (09:00-14:00 y
    16:00-20:00), dejando margen al final para que una cita de hasta 45
    minutos quepa entera y no choque con la invariante de horario.
    """
    huecos = []
    for hora_ini, hora_fin in ((9, 13), (16, 19)):   # último inicio: 13:30 / 19:30
        actual = dia.replace(hour=hora_ini, minute=0, second=0, microsecond=0)
        limite = dia.replace(hour=hora_fin, minute=15, second=0, microsecond=0)
        while actual <= limite:
            huecos.append(actual)
            actual += timedelta(minutes=30)
    return huecos


def sembrar_agenda(db, empresa_id, pacientes, especialistas, servicios_por_especialidad):
    """Crea una agenda de ejemplo repartida entre profesionales y pacientes.

    Las citas FUTURAS se crean vía `crud_cita.create_cita`, de modo que pasan
    por las tres invariantes (horario, no solapamiento, no pasado): si el
    generador produjera algo incoherente, el seed fallaría en vez de meter
    datos inválidos.

    Las citas PASADAS se insertan directamente por sesión, porque la API las
    rechaza por diseño. Representan historial preexistente y sirven para que el
    panel tenga citas antiguas que consultar y cancelar.
    """
    creadas, cancelar, confirmar = [], [], []
    ahora = datetime.now()

    # --- Historial: 2 días laborables hacia atrás, insertadas a mano ---
    for dia in _dias_laborables(ahora, 2, hacia_atras=True):
        for i, hueco in enumerate(_huecos_del_dia(dia)[:3]):
            esp = especialistas[i % len(especialistas)]
            servicio = servicios_por_especialidad[esp.especialidad][0]
            db.add(Cita(
                empresa_id=empresa_id,
                cliente_id=pacientes[(i + dia.day) % len(pacientes)].id,
                empleado_id=esp.id,
                servicio_id=servicio.id,
                fecha_hora=hueco,
                # Alternamos para que el historial no sea uniforme.
                estado=EstadoCita.CONFIRMADA if i % 3 else EstadoCita.CANCELADA,
            ))
    db.commit()

    # --- Hoy: solo huecos que aún no han pasado (create_cita rechaza el pasado) ---
    dias = [ahora] if ahora.weekday() < 5 else []
    dias += _dias_laborables(ahora, 6)

    for indice_dia, dia in enumerate(dias):
        huecos = [h for h in _huecos_del_dia(dia) if h > ahora + timedelta(minutes=5)]
        # Repartimos unas pocas citas por día, alternando profesional y paciente.
        for i, hueco in enumerate(huecos[:: max(1, len(huecos) // 4)][:4]):
            esp = especialistas[(i + indice_dia) % len(especialistas)]
            opciones = servicios_por_especialidad[esp.especialidad]
            servicio = opciones[(i + indice_dia) % len(opciones)]
            cita = crud_cita.create_cita(
                db,
                schemas.CitaCreate(
                    fecha_hora=hueco, notas_ia=None,
                    cliente_id=pacientes[(i * 3 + indice_dia) % len(pacientes)].id,
                    empleado_id=esp.id, servicio_id=servicio.id,
                ),
                empresa_id=empresa_id,
            )
            creadas.append(cita)
            # Una de cada tres se confirma y una de cada siete se cancela, para
            # que los indicadores del panel muestren los tres estados.
            if len(creadas) % 3 == 0:
                confirmar.append(cita.id)
            elif len(creadas) % 7 == 0:
                cancelar.append(cita.id)

    for cita_id in confirmar:
        crud_cita.update_cita(db, cita_id=cita_id,
                              cita=schemas.CitaUpdate(estado=EstadoCita.CONFIRMADA),
                              empresa_id=empresa_id)
    for cita_id in cancelar:
        crud_cita.update_cita(db, cita_id=cita_id,
                              cita=schemas.CitaUpdate(estado=EstadoCita.CANCELADA),
                              empresa_id=empresa_id)
    return len(creadas)


def reiniciar(db) -> None:
    """Vacía las tablas de datos para poder resembrar desde cero.

    No toca `alembic_version`: el esquema lo gestiona Alembic y borrarlo dejaría
    la base de datos creyendo que no tiene migraciones aplicadas.
    """
    db.execute(text("SET FOREIGN_KEY_CHECKS=0"))
    for tabla in ("citas", "clientes", "empleados", "servicios", "empresas"):
        db.execute(text(f"TRUNCATE TABLE `{tabla}`"))
    db.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    db.commit()
    print("Datos anteriores eliminados (el esquema y las migraciones se conservan).")


def seed(reset: bool = False) -> None:
    db = SessionLocal()
    try:
        if reset:
            reiniciar(db)
        if crud_empresa.get_empresa_by_slug(db, slug="clinica-demo") is not None:
            print(
                "Las empresas de prueba ya existen. Nada que sembrar "
                "(el seed es idempotente). Usa --reset para volver a sembrar."
            )
            return

        print("=== Empresa A ===")
        a = sembrar_empresa(
            db, "Clínica Demo", "clinica-demo",
            cliente=("Ana García", "ana@demo.com", "600111222"),
            empleado=("Dra. Laura Ruiz", "laura@demo.com", "Odontología"),
            servicio=("Limpieza dental", 30, 45.00),
        )

        # Segundo empleado de la Empresa A con rol PERSONAL (recepción): sirve
        # para probar la diferencia de permisos frente al ADMIN. Debe recibir
        # 403 en los endpoints de administración y trabajar con clientes/citas.
        recepcion = crud_empleado.create_empleado(
            db,
            schemas.EmpleadoCreate(
                nombre="Sara Recepción", email="sara@demo.com",
                especialidad="Recepción", activo=True,
                rol=RolEmpleado.PERSONAL, password=PASSWORD_DEMO,
            ),
            empresa_id=a["empresa"].id,
        )
        print(
            f"  Empleado creado: {recepcion.email} "
            f"(id={recepcion.id}, rol={recepcion.rol.value})"
        )

        # --- Clínica médica: resto de especialistas, catálogo y pacientes ---
        print("  --- Ampliando la clínica ---")
        especialistas = [a["empleado"]]          # la Dra. Ruiz (Odontología)
        for nombre, email, especialidad in ESPECIALISTAS:
            especialistas.append(crud_empleado.create_empleado(
                db,
                schemas.EmpleadoCreate(
                    nombre=nombre, email=email, especialidad=especialidad,
                    activo=True, rol=RolEmpleado.PERSONAL, password=PASSWORD_DEMO,
                ),
                empresa_id=a["empresa"].id,
            ))
        print(f"  {len(ESPECIALISTAS)} especialistas más creados")

        # Los servicios se agrupan por especialidad para que cada cita se agende
        # con un profesional que realmente presta ese servicio.
        por_especialidad = {a["empleado"].especialidad: [a["servicio"]]}
        for nombre, duracion, precio, especialidad in SERVICIOS:
            servicio = crud_servicio.create_servicio(
                db,
                schemas.ServicioCreate(
                    nombre=nombre, duracion_minutos=duracion, precio=precio,
                ),
                empresa_id=a["empresa"].id,
            )
            por_especialidad.setdefault(especialidad, []).append(servicio)
        print(f"  {len(SERVICIOS)} servicios más creados")

        pacientes = [a["cliente"]]
        for nombre, email, telefono in PACIENTES:
            pacientes.append(crud_cliente.create_cliente(
                db,
                schemas.ClienteCreate(
                    nombre=nombre, email=email, telefono=telefono,
                    password=PASSWORD_DEMO,
                ),
                empresa_id=a["empresa"].id,
            ))
        print(f"  {len(PACIENTES)} pacientes más creados")

        n = sembrar_agenda(db, a["empresa"].id, pacientes, especialistas, por_especialidad)
        print(f"  Agenda sembrada: {n} citas futuras + historial de días anteriores")

        print("\n=== Empresa B ===")
        b = sembrar_empresa(
            db, "Spa Demo", "spa-demo",
            cliente=("Bruno Díaz", "bruno@spa.com", "600333444"),
            empleado=("Dr. Marco Vidal", "marco@spa.com", "Fisioterapia"),
            servicio=("Masaje relajante", 45, 60.00),
        )

        print("\n" + "-" * 56)
        print("Credenciales de prueba (contraseña de todos: password123)")
        print(f"  Empresa A (id={a['empresa'].id}): ana@demo.com  / laura@demo.com (ADMIN) / sara@demo.com (PERSONAL)")
        print(f"  Empresa B (id={b['empresa'].id}): bruno@spa.com / marco@spa.com (ADMIN)")
        print("-" * 56)
        print("Prueba de AISLAMIENTO sugerida:")
        print(f"  1) Login como ana@demo.com (Empresa A).")
        print(f"  2) GET /clientes/  -> solo verás clientes de la Empresa A.")
        print(f"  3) GET /clientes/{b['cliente'].id} (cliente de B) -> debe dar 404.")
        print(f"  4) GET /servicios/{b['servicio'].id} (servicio de B) -> debe dar 404.")
        print("-" * 56)
    finally:
        db.close()


if __name__ == "__main__":
    _reset = "--reset" in sys.argv
    seed(reset=_reset)
