"""BLOQUE B: control de acceso por rol (ADMIN / PERSONAL).

- Un empleado PERSONAL recibe 403 en los seis endpoints de administración.
- Un ADMIN sí puede usarlos.
- PERSONAL conserva su trabajo diario (clientes, citas, lectura de servicios).
- Salvaguarda del último administrador activo: borrarlo, degradarlo o
  desactivarlo -> 409. Con DOS administradores, degradar a uno SÍ se permite.
"""
import pytest

# Los seis endpoints de administración: (método, ruta con placeholders, cuerpo).
# La ruta se formatea con los ids de la empresa A del test.
CASOS_ADMIN = [
    ("POST", "/empleados/", {"nombre": "Nuevo", "email": "z_rbac@test.com",
                             "password": "password123"}),
    ("PUT", "/empleados/{admin_id}", {"nombre": "Cambiado"}),
    ("DELETE", "/empleados/{admin_id}", None),
    ("PUT", "/empresas/{empresa_id}", {"nombre": "Cambiada"}),
    ("DELETE", "/empresas/{empresa_id}", None),
    ("POST", "/servicios/", {"nombre": "Nuevo", "duracion_minutos": 15, "precio": 10}),
]


def _ruta(plantilla, d):
    return plantilla.format(admin_id=d.a.admin_id, empresa_id=d.a.empresa_id)


# --- PERSONAL recibe 403 en los seis endpoints de administración ------------
@pytest.mark.parametrize("metodo,plantilla,cuerpo", CASOS_ADMIN)
def test_personal_403_en_administracion(
    client, auth, datos_base, metodo, plantilla, cuerpo
):
    r = client.request(
        metodo, _ruta(plantilla, datos_base), json=cuerpo,
        headers=auth(datos_base.a.token_personal),
    )
    assert r.status_code == 403, f"{metodo} {plantilla} -> {r.status_code}: {r.text}"


# --- ADMIN sí puede usar los endpoints de administración --------------------
def test_admin_puede_crear_empleado(client, auth, datos_base):
    r = client.post(
        "/empleados/",
        json={"nombre": "Nuevo", "email": "nuevo_rbac@test.com", "password": "password123"},
        headers=auth(datos_base.a.token_admin),
    )
    assert r.status_code == 201, r.text
    assert r.json()["rol"] == "PERSONAL"  # por defecto, mínimo privilegio


def test_admin_puede_modificar_y_borrar_empleado(client, auth, datos_base):
    # Modifica al empleado PERSONAL (no es el último admin, no dispara salvaguarda).
    r_put = client.put(
        f"/empleados/{datos_base.a.personal_id}", json={"nombre": "Renombrado"},
        headers=auth(datos_base.a.token_admin),
    )
    assert r_put.status_code == 200, r_put.text
    r_del = client.delete(
        f"/empleados/{datos_base.a.personal_id}",
        headers=auth(datos_base.a.token_admin),
    )
    assert r_del.status_code == 204, r_del.text


def test_admin_puede_editar_empresa(client, auth, datos_base):
    r_put = client.put(
        f"/empresas/{datos_base.a.empresa_id}", json={"nombre": "Clinica A Renombrada"},
        headers=auth(datos_base.a.token_admin),
    )
    assert r_put.status_code == 200, r_put.text


def test_admin_puede_borrar_empresa(client, auth, datos_base):
    # Borrar el tenant completo: la cascada de InnoDB elimina clientes,
    # empleados y servicios (ver passive_deletes en models.py).
    r_del = client.delete(
        f"/empresas/{datos_base.a.empresa_id}",
        headers=auth(datos_base.a.token_admin),
    )
    assert r_del.status_code == 204, r_del.text


def test_admin_puede_crear_servicio(client, auth, datos_base):
    r = client.post(
        "/servicios/", json={"nombre": "Limpieza", "duracion_minutos": 20, "precio": 30},
        headers=auth(datos_base.a.token_admin),
    )
    assert r.status_code == 201, r.text


# --- PERSONAL conserva su trabajo diario ------------------------------------
def test_personal_trabajo_diario(client, auth, datos_base):
    cab = auth(datos_base.a.token_personal)
    assert client.get("/clientes/", headers=cab).status_code == 200
    assert client.get("/citas/", headers=cab).status_code == 200
    assert client.get("/servicios/", headers=cab).status_code == 200
    r_crear = client.post(
        "/clientes/",
        json={"nombre": "Paciente", "email": "paciente_rbac@test.com",
              "telefono": "600123123", "password": "password123"},
        headers=cab,
    )
    assert r_crear.status_code == 201, r_crear.text


# --- Salvaguarda del último administrador activo: las tres vías -> 409 -------
def test_salvaguarda_borrar_ultimo_admin(client, auth, datos_base):
    r = client.delete(
        f"/empleados/{datos_base.a.admin_id}", headers=auth(datos_base.a.token_admin)
    )
    assert r.status_code == 409, r.text


def test_salvaguarda_degradar_ultimo_admin(client, auth, datos_base):
    r = client.put(
        f"/empleados/{datos_base.a.admin_id}", json={"rol": "PERSONAL"},
        headers=auth(datos_base.a.token_admin),
    )
    assert r.status_code == 409, r.text


def test_salvaguarda_desactivar_ultimo_admin(client, auth, datos_base):
    r = client.put(
        f"/empleados/{datos_base.a.admin_id}", json={"activo": False},
        headers=auth(datos_base.a.token_admin),
    )
    assert r.status_code == 409, r.text


# --- Caso positivo: con DOS administradores, degradar a uno SÍ se permite ----
def test_degradar_admin_con_dos_admins_permitido(client, auth, datos_base):
    cab = auth(datos_base.a.token_admin)
    # Promocionamos al PERSONAL a ADMIN: ya hay dos administradores activos.
    r_promo = client.put(
        f"/empleados/{datos_base.a.personal_id}", json={"rol": "ADMIN"}, headers=cab
    )
    assert r_promo.status_code == 200, r_promo.text
    # Ahora degradar al admin original ya no deja la empresa sin administración.
    r_degradar = client.put(
        f"/empleados/{datos_base.a.admin_id}", json={"rol": "PERSONAL"}, headers=cab
    )
    assert r_degradar.status_code == 200, r_degradar.text
