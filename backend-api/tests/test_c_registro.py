"""BLOQUE C: registro público de clínicas (onboarding de tenants).

POST /registro/ es público: crea la empresa y su primer empleado ADMIN en una
sola transacción y devuelve un token usable de inmediato. El test estrella es el
de ATOMICIDAD: si falla el insert del empleado con la empresa ya en flush, no
puede quedar una empresa huérfana (un tenant irrecuperable desde la API).
"""
from app import models
from app.database import SessionLocal


def _cuerpo(slug="clinica-nueva", email="fundador@nueva.com", password="password123",
            nombre_empresa="Clinica Nueva"):
    return {
        "empresa_nombre": nombre_empresa,
        "slug": slug,
        "admin_nombre": "Fundador",
        "admin_email": email,
        "admin_password": password,
    }


# --- Alta correcta -> 201, token usable ya, primer empleado ADMIN -----------
def test_registro_correcto(client, auth):
    r = client.post("/registro/", json=_cuerpo())
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert cuerpo["empleado"]["rol"] == "ADMIN"

    # El token devuelto funciona sin un login posterior.
    token = cuerpo["access_token"]
    r_empresas = client.get("/empresas/", headers=auth(token))
    assert r_empresas.status_code == 200, r_empresas.text
    assert r_empresas.json()[0]["slug"] == "clinica-nueva"


# --- Slug duplicado -> 409 --------------------------------------------------
def test_slug_duplicado(client):
    assert client.post("/registro/", json=_cuerpo(slug="clinica-dup",
                                                  email="a@dup.com")).status_code == 201
    r = client.post("/registro/", json=_cuerpo(slug="clinica-dup", email="b@dup.com"))
    assert r.status_code == 409, r.text


# --- Slug normalizado: "Clinica DOS" -> "clinica-dos" -----------------------
def test_slug_normalizado(client):
    r = client.post("/registro/", json=_cuerpo(slug="Clinica DOS",
                                               email="dos@nueva.com"))
    assert r.status_code == 201, r.text
    assert r.json()["empresa"]["slug"] == "clinica-dos"


# --- Contraseña por debajo del mínimo -> 422 (validación de esquema) --------
def test_password_corta_422(client):
    r = client.post("/registro/", json=_cuerpo(password="corta"))  # 5 < 8
    assert r.status_code == 422, r.text


# --- ATOMICIDAD: fallo en el insert del empleado -> sin empresa huérfana -----
def test_atomicidad_sin_empresa_huerfana(client):
    """Fuerza un fallo de BD en el empleado con la empresa ya en flush.

    El email es válido para EmailStr pero de 109 caracteres, por encima del
    VARCHAR(100) de la columna: el INSERT del empleado revienta DESPUÉS de que
    la empresa haya hecho flush. Se comprueba que el rollback dejó la tabla
    empresas sin ninguna fila con ese slug (no hay tenant huérfano).
    """
    slug = "clinica-orfana"
    email_largo = "a" * 64 + "@" + "b" * 40 + ".com"  # 109 chars: pasa EmailStr
    r = client.post("/registro/", json=_cuerpo(slug=slug, email=email_largo))
    assert r.status_code == 400, r.text  # no 201 y, sobre todo, no 500

    db = SessionLocal()
    try:
        huerfanas = (
            db.query(models.Empresa).filter(models.Empresa.slug == slug).count()
        )
    finally:
        db.close()
    assert huerfanas == 0, "Quedó una empresa huérfana: la atomicidad falló."
