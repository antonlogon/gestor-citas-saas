"""BLOQUE A: regla de no solapamiento de citas (incluida la concurrencia).

Un empleado no puede tener dos citas activas cuyos intervalos [inicio, fin) se
pisen; las canceladas no ocupan hueco. La invariante vive en
``crud_cita.verificar_disponibilidad`` y todos los caminos de escritura pasan
por ella. El test de concurrencia (A8) es el más delicado: ataca el bloqueo
``FOR UPDATE`` con conexiones separadas, algo que solo es real sobre InnoDB.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from app import models, schemas
from app.crud import crud_cita
from app.database import SessionLocal

# Día fijo en el futuro para que las horas de los tests no dependan del reloj.
DIA = "2030-01-07"


def _iso(dt: datetime) -> str:
    """Formatea un datetime al ISO naive que envía el cliente (sin microsegundos)."""
    return dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")


def _futuro_laborable(dias=1, hora=10, minuto=0):
    """Devuelve un datetime futuro en dia LABORABLE y DENTRO del horario de
    apertura por defecto (L-V 09:00-14:00 y 16:00-20:00).

    Hace falta porque ``now() + N dias`` ARRASTRA LA HORA ACTUAL: lanzar la suite
    a las 20:36, o en fin de semana, produce una fecha que la invariante de
    horario rechaza con 422 ANTES de llegar a la regla que el test comprueba.
    El resultado era una prueba que dependia del reloj de quien la ejecutaba.

    Se fija la hora a las 10:00 (con margen de sobra para la duracion del
    servicio) y se salta el fin de semana. Mismo criterio que ``_laborable`` en
    test_f_chatbot_tools.
    """
    d = (datetime.now() + timedelta(days=dias)).replace(
        hour=hora, minute=minuto, second=0, microsecond=0
    )
    while d.weekday() >= 5:  # 5=sabado, 6=domingo
        d += timedelta(days=1)
    return d


def _insertar_cita_pasada(datos, dias=7):
    """Inserta directamente en BD una cita ya pasada y devuelve (id, fecha).

    Se hace por sesión SQLAlchemy, no por la API, porque crear en el pasado pasa
    a estar prohibido: esto simula datos históricos preexistentes que hay que
    poder seguir gestionando.
    """
    db = SessionLocal()
    try:
        fecha = datetime.now().replace(microsecond=0) - timedelta(days=dias)
        cita = models.Cita(
            empresa_id=datos.a.empresa_id,
            cliente_id=datos.a.cliente_id,
            empleado_id=datos.a.admin_id,
            servicio_id=datos.a.servicio_id,
            fecha_hora=fecha,
            estado=models.EstadoCita.PENDIENTE,
        )
        db.add(cita)
        db.commit()
        db.refresh(cita)
        return cita.id, fecha
    finally:
        db.close()


def _crear_cita(client, auth, datos, hora, token=None):
    """POST /citas/ para el empleado/servicio de la empresa A a la hora dada."""
    cuerpo = {
        "fecha_hora": f"{DIA}T{hora}:00",
        "cliente_id": datos.a.cliente_id,
        "empleado_id": datos.a.admin_id,
        "servicio_id": datos.a.servicio_id,
    }
    cabecera = auth(token or datos.a.token_personal)
    return client.post("/citas/", json=cuerpo, headers=cabecera)


# --- A1: franja libre -> 201 ------------------------------------------------
def test_franja_libre_crea_cita(client, auth, datos_base):
    r = _crear_cita(client, auth, datos_base, "09:00")
    assert r.status_code == 201, r.text
    assert r.json()["estado"] == "PENDIENTE"


# --- A2: solapamiento exacto -> 409 -----------------------------------------
def test_solapamiento_exacto_conflicto(client, auth, datos_base):
    assert _crear_cita(client, auth, datos_base, "09:00").status_code == 201
    r = _crear_cita(client, auth, datos_base, "09:00")
    assert r.status_code == 409, r.text


# --- A3: solapamiento parcial por duración (09:15 sobre 09:00-09:30) -> 409 --
def test_solapamiento_parcial_conflicto(client, auth, datos_base):
    assert _crear_cita(client, auth, datos_base, "09:00").status_code == 201
    r = _crear_cita(client, auth, datos_base, "09:15")
    assert r.status_code == 409, r.text


# --- A4: cita contigua (09:30 justo al acabar la anterior) -> 201 -----------
def test_cita_contigua_sin_solape(client, auth, datos_base):
    assert _crear_cita(client, auth, datos_base, "09:00").status_code == 201
    r = _crear_cita(client, auth, datos_base, "09:30")
    assert r.status_code == 201, r.text


# --- A5: una cita cancelada libera la franja --------------------------------
def test_cita_cancelada_libera_franja(client, auth, datos_base):
    r1 = _crear_cita(client, auth, datos_base, "09:00")
    cita_id = r1.json()["id"]
    # Cancelar libera el hueco.
    r_cancel = client.put(
        f"/citas/{cita_id}", json={"estado": "CANCELADA"},
        headers=auth(datos_base.a.token_personal),
    )
    assert r_cancel.status_code == 200, r_cancel.text
    # La misma franja vuelve a estar disponible.
    r2 = _crear_cita(client, auth, datos_base, "09:00")
    assert r2.status_code == 201, r2.text


# --- A6: reactivar una cancelada sobre una franja ya reasignada -> 409 -------
def test_reactivar_cancelada_sobre_franja_ocupada(client, auth, datos_base):
    r1 = _crear_cita(client, auth, datos_base, "09:00")
    cita1 = r1.json()["id"]
    # Se cancela la 1ª y se reserva otra en el mismo hueco.
    client.put(f"/citas/{cita1}", json={"estado": "CANCELADA"},
               headers=auth(datos_base.a.token_personal))
    assert _crear_cita(client, auth, datos_base, "09:00").status_code == 201
    # Reactivar la 1ª ahora chocaría con la 2ª -> 409.
    r = client.put(f"/citas/{cita1}", json={"estado": "CONFIRMADA"},
                   headers=auth(datos_base.a.token_personal))
    assert r.status_code == 409, r.text


# --- A7: reprogramar (PUT fecha_hora) hacia una franja ocupada -> 409 --------
def test_reprogramar_hacia_franja_ocupada(client, auth, datos_base):
    assert _crear_cita(client, auth, datos_base, "09:00").status_code == 201
    r2 = _crear_cita(client, auth, datos_base, "10:00")
    cita2 = r2.json()["id"]
    # Mover la 2ª encima de la 1ª -> conflicto.
    r = client.put(f"/citas/{cita2}", json={"fecha_hora": f"{DIA}T09:00:00"},
                   headers=auth(datos_base.a.token_personal))
    assert r.status_code == 409, r.text


# --- A8: concurrencia -> exactamente 1 crea y el resto reciben conflicto -----
def test_concurrencia_una_sola_cita(datos_base):
    """N peticiones simultáneas sobre la misma franja: 1 crea, N-1 conflicto.

    Cada hilo abre su PROPIA sesión (SessionLocal) y llama a create_cita, que
    comprueba el solape con FOR UPDATE en la misma transacción. Si compartieran
    sesión, el test no probaría nada. Se cuentan éxitos y CitaSolapadaError; un
    tercer grupo ("error") captaría cualquier otro fallo (p. ej. un interbloqueo
    de InnoDB) para no ocultarlo.
    """
    n = 6
    cuerpo = schemas.CitaCreate(
        fecha_hora=f"{DIA}T11:00:00",
        cliente_id=datos_base.a.cliente_id,
        empleado_id=datos_base.a.admin_id,
        servicio_id=datos_base.a.servicio_id,
    )
    empresa_id = datos_base.a.empresa_id

    def intentar(_):
        db = SessionLocal()
        try:
            crud_cita.create_cita(db, cita=cuerpo, empresa_id=empresa_id)
            return "ok"
        except crud_cita.CitaSolapadaError:
            return "conflicto"
        except Exception as exc:  # noqa: BLE001 - queremos ver cualquier otro fallo
            return f"error:{type(exc).__name__}"
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=n) as pool:
        resultados = list(pool.map(intentar, range(n)))

    exitos = resultados.count("ok")
    conflictos = resultados.count("conflicto")
    otros = [r for r in resultados if r not in ("ok", "conflicto")]
    assert otros == [], f"Fallos inesperados en la concurrencia: {otros}"
    assert exitos == 1, f"Se esperaba 1 cita creada, hubo {exitos}: {resultados}"
    assert conflictos == n - 1, f"Se esperaban {n-1} conflictos: {resultados}"


# ==========================================================================
# NO SE PUEDEN AGENDAR NI MOVER CITAS AL PASADO (422, distinto del 409 de solape)
# ==========================================================================


def _post_cita(client, auth, datos, iso):
    """POST /citas/ para la empresa A a la fecha/hora ISO indicada."""
    return client.post(
        "/citas/",
        json={
            "fecha_hora": iso,
            "cliente_id": datos.a.cliente_id,
            "empleado_id": datos.a.admin_id,
            "servicio_id": datos.a.servicio_id,
        },
        headers=auth(datos.a.token_personal),
    )


# --- Crear en el pasado -> 422 ----------------------------------------------
def test_crear_cita_en_pasado_rechazada(client, auth, datos_base):
    iso = _iso(datetime.now() - timedelta(days=1))
    r = _post_cita(client, auth, datos_base, iso)
    assert r.status_code == 422, r.text


# --- Crear a una hora de HOY que ya pasó -> 422 -----------------------------
def test_crear_cita_hora_hoy_pasada_rechazada(client, auth, datos_base):
    iso = _iso(datetime.now() - timedelta(hours=1))
    r = _post_cita(client, auth, datos_base, iso)
    assert r.status_code == 422, r.text


# --- Crear futura -> 201 (sin regresión) ------------------------------------
def test_crear_cita_futura_ok(client, auth, datos_base):
    iso = _iso(_futuro_laborable())
    r = _post_cita(client, auth, datos_base, iso)
    assert r.status_code == 201, r.text


# --- Reprogramar hacia el pasado -> 422 -------------------------------------
def test_reprogramar_hacia_pasado_rechazado(client, auth, datos_base):
    creada = _post_cita(client, auth, datos_base, _iso(_futuro_laborable()))
    assert creada.status_code == 201, creada.text
    cita_id = creada.json()["id"]
    r = client.put(
        f"/citas/{cita_id}",
        json={"fecha_hora": _iso(datetime.now() - timedelta(days=1))},
        headers=auth(datos_base.a.token_personal),
    )
    assert r.status_code == 422, r.text


# --- Cancelar una cita YA PASADA -> 200 (el caso que no debe romperse) -------
def test_cancelar_cita_pasada_ok(client, auth, datos_base):
    cita_id, _ = _insertar_cita_pasada(datos_base)
    r = client.put(
        f"/citas/{cita_id}", json={"estado": "CANCELADA"},
        headers=auth(datos_base.a.token_personal),
    )
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "CANCELADA"


# --- Añadir notas a una cita pasada, sin tocar la fecha -> 200 --------------
def test_anadir_notas_cita_pasada_ok(client, auth, datos_base):
    cita_id, _ = _insertar_cita_pasada(datos_base)
    r = client.put(
        f"/citas/{cita_id}", json={"notas_ia": "Paciente acudió sin incidencias."},
        headers=auth(datos_base.a.token_personal),
    )
    assert r.status_code == 200, r.text


# --- PUT a una cita pasada REENVIANDO su MISMA fecha + cambio de estado -> 200
# Este es el caso que fallaría con el disparador "la petición envió fecha_hora":
# el diálogo de escritorio manda SIEMPRE fecha_hora, aunque no se toque.
def test_put_cita_pasada_misma_fecha_ok(client, auth, datos_base):
    cita_id, fecha = _insertar_cita_pasada(datos_base)
    r = client.put(
        f"/citas/{cita_id}",
        json={"fecha_hora": _iso(fecha), "estado": "CANCELADA",
              "notas_ia": "Cerrada a posteriori."},
        headers=auth(datos_base.a.token_personal),
    )
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "CANCELADA"
