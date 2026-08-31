"""BLOQUE G: tercera invariante de agenda — horario de apertura por tenant.

Una cita es válida solo si su INTERVALO COMPLETO [inicio, inicio+duracion] cabe
dentro de un mismo tramo de apertura del día de esa clínica. El horario vive POR
EMPRESA (columna JSON), así que cada tenant valida contra el suyo. La regla vive
en ``crud_cita._validar_dentro_horario`` y alcanza los tres caminos de escritura
(creación por API, reprogramación y asistente vía create/update).

El horario por defecto (empresa A) es L-V 09:00-14:00 y 16:00-20:00, S-D cerrado.
Las fechas son fijas y futuras para no depender del reloj:
    2030-01-07 -> LUNES     (día laborable)
    2030-01-12 -> SÁBADO    (cerrado por defecto)
    2030-01-13 -> DOMINGO   (cerrado por defecto)
El servicio de ``datos_base`` dura 30 minutos: es la duración sobre la que se
construyen los casos de "termina justo al cierre" y "empieza dentro, termina
fuera".
"""
from datetime import datetime, timedelta

from app import models
from app.database import SessionLocal

LUNES = "2030-01-07"
SABADO = "2030-01-12"
DOMINGO = "2030-01-13"


def _post_cita(client, auth, datos, dia, hora, token=None):
    """POST /citas/ para el empleado/servicio de la empresa A en dia+hora."""
    cuerpo = {
        "fecha_hora": f"{dia}T{hora}:00",
        "cliente_id": datos.a.cliente_id,
        "empleado_id": datos.a.admin_id,
        "servicio_id": datos.a.servicio_id,
    }
    cabecera = auth(token or datos.a.token_personal)
    return client.post("/citas/", json=cuerpo, headers=cabecera)


def _set_horario(empresa_id, horario):
    """Fija el horario de apertura de una empresa (para el caso multi-tenant)."""
    db = SessionLocal()
    try:
        empresa = db.get(models.Empresa, empresa_id)
        empresa.horario_apertura = horario
        db.commit()
    finally:
        db.close()


def _insertar_cita_fuera_horario(datos, dia_hora: datetime):
    """Inserta directamente en BD (sin pasar por la validación) una cita futura y
    FUERA de horario, para simular datos preexistentes que hay que poder seguir
    gestionando sin tocar su fecha."""
    db = SessionLocal()
    try:
        cita = models.Cita(
            empresa_id=datos.a.empresa_id,
            cliente_id=datos.a.cliente_id,
            empleado_id=datos.a.admin_id,
            servicio_id=datos.a.servicio_id,
            fecha_hora=dia_hora,
            estado=models.EstadoCita.PENDIENTE,
        )
        db.add(cita)
        db.commit()
        db.refresh(cita)
        return cita.id
    finally:
        db.close()


# --- G1: dentro de horario -> 201 -------------------------------------------
def test_dentro_de_horario_crea(client, auth, datos_base):
    r = _post_cita(client, auth, datos_base, LUNES, "10:00")  # 10:00-10:30 en 09-14
    assert r.status_code == 201, r.text


# --- G2: sábado y domingo (cerrado) -> 422 ----------------------------------
def test_sabado_cerrado_rechazada(client, auth, datos_base):
    r = _post_cita(client, auth, datos_base, SABADO, "10:00")
    assert r.status_code == 422, r.text
    assert "cerrada" in r.json()["detail"].lower()  # mensaje útil, no genérico


def test_domingo_cerrado_rechazada(client, auth, datos_base):
    r = _post_cita(client, auth, datos_base, DOMINGO, "10:00")
    assert r.status_code == 422, r.text


# --- G3: antes de abrir y después de cerrar -> 422 --------------------------
def test_antes_de_abrir_rechazada(client, auth, datos_base):
    r = _post_cita(client, auth, datos_base, LUNES, "08:00")  # antes de las 09:00
    assert r.status_code == 422, r.text


def test_despues_de_cerrar_rechazada(client, auth, datos_base):
    r = _post_cita(client, auth, datos_base, LUNES, "20:30")  # tras cerrar a las 20:00
    assert r.status_code == 422, r.text


# --- G4: dentro del cierre de mediodía -> 422 -------------------------------
def test_cierre_mediodia_rechazada(client, auth, datos_base):
    r = _post_cita(client, auth, datos_base, LUNES, "14:30")  # entre 14:00 y 16:00
    assert r.status_code == 422, r.text


# --- G5: empieza dentro y TERMINA FUERA (13:45 + 30 = 14:15) -> 422 ----------
# El caso sutil: la hora de inicio SÍ cae en horario, pero el intervalo completo
# se sale del tramo. Debe rechazarse igual.
def test_empieza_dentro_termina_fuera_rechazada(client, auth, datos_base):
    r = _post_cita(client, auth, datos_base, LUNES, "13:45")
    assert r.status_code == 422, r.text


# --- G6: TERMINA EXACTAMENTE AL CIERRE (13:30 + 30 = 14:00) -> 201 -----------
# El cierre es inclusivo, igual que en el solape una cita que empieza cuando otra
# acaba no solapa.
def test_termina_justo_al_cierre_crea(client, auth, datos_base):
    r = _post_cita(client, auth, datos_base, LUNES, "13:30")
    assert r.status_code == 201, r.text


# --- G7: el mensaje indica el horario REAL del día --------------------------
def test_mensaje_indica_horario_real(client, auth, datos_base):
    r = _post_cita(client, auth, datos_base, LUNES, "08:00")
    assert r.status_code == 422, r.text
    detalle = r.json()["detail"]
    assert "09:00" in detalle and "14:00" in detalle and "20:00" in detalle


# --- G8: reprogramar una cita a fuera de horario -> 422 ---------------------
def test_reprogramar_fuera_de_horario_rechazada(client, auth, datos_base):
    creada = _post_cita(client, auth, datos_base, LUNES, "10:00")
    assert creada.status_code == 201, creada.text
    cita_id = creada.json()["id"]
    # Mover a un sábado (cerrado) -> rechazo por horario.
    r = client.put(
        f"/citas/{cita_id}",
        json={"fecha_hora": f"{SABADO}T10:00:00"},
        headers=auth(datos_base.a.token_personal),
    )
    assert r.status_code == 422, r.text


# --- G9: CANCELAR una cita preexistente fuera de horario, SIN tocar su fecha,
#         está permitido (protege el historial). ----------------------------
def test_cancelar_cita_preexistente_fuera_horario_ok(client, auth, datos_base):
    # Cita futura pero en sábado (fuera del horario por defecto), insertada directa.
    cita_id = _insertar_cita_fuera_horario(datos_base, datetime(2030, 1, 12, 11, 0))
    r = client.put(
        f"/citas/{cita_id}",
        json={"estado": "CANCELADA"},  # NO se envía fecha_hora
        headers=auth(datos_base.a.token_personal),
    )
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "CANCELADA"


# --- G9b: reenviar la MISMA fecha fuera de horario + cambio de estado -> 200 -
# El escritorio manda siempre fecha_hora aunque no se toque; reenviar la misma
# fecha no es "mover", así que no debe dispararse la validación de horario.
def test_confirmar_cita_fuera_horario_misma_fecha_ok(client, auth, datos_base):
    fecha = datetime(2030, 1, 12, 11, 0)
    cita_id = _insertar_cita_fuera_horario(datos_base, fecha)
    r = client.put(
        f"/citas/{cita_id}",
        json={"fecha_hora": f"{fecha.strftime('%Y-%m-%dT%H:%M:%S')}",
              "estado": "CONFIRMADA"},
        headers=auth(datos_base.a.token_personal),
    )
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "CONFIRMADA"


# --- G10: dos clínicas con horarios DISTINTOS validan cada una contra el suyo
# Demuestra que el horario es REALMENTE por inquilino y no una constante. La
# empresa B se reconfigura para abrir todos los días 10:00-18:00 (incluido el
# sábado). Entonces la MISMA fecha/hora es válida en una y no en la otra.
def test_horarios_distintos_por_tenant(client, auth, datos_base):
    # B abre todos los días de 10:00 a 18:00 (incluidos fines de semana).
    _set_horario(
        datos_base.b.empresa_id,
        [[{"inicio": "10:00", "fin": "18:00"}] for _ in range(7)],
    )

    def post_b(dia, hora):
        return client.post(
            "/citas/",
            json={
                "fecha_hora": f"{dia}T{hora}:00",
                "cliente_id": datos_base.b.cliente_id,
                "empleado_id": datos_base.b.admin_id,
                "servicio_id": datos_base.b.servicio_id,
            },
            headers=auth(datos_base.b.token_admin),
        )

    # SÁBADO: A está cerrada (rechaza), B abre (acepta).
    assert _post_cita(client, auth, datos_base, SABADO, "12:00").status_code == 422
    assert post_b(SABADO, "12:00").status_code == 201

    # LUNES 09:00: A abre a las 09:00 (acepta), B abre a las 10:00 (rechaza 09:00).
    assert _post_cita(client, auth, datos_base, LUNES, "09:00").status_code == 201
    assert post_b(LUNES, "09:00").status_code == 422
