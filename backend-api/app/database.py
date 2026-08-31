from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

# URL de conexión (Usuario:Contraseña@Servidor:Puerto/NombreBaseDeDatos).
# Se externaliza mediante la variable de entorno DATABASE_URL (ver .env / .env.example).
# Por defecto apunta al puerto 3307 que configuramos en Docker para evitar conflictos.
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# El "Motor": Es la tubería principal que gestiona la conexión con MySQL
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# La Fábrica de Sesiones: Cada vez que FastAPI necesite hablar con la BD, usará esto
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# La Clase Base: Todos nuestros modelos de datos heredarán de aquí
# (Equivalente a la anotación @Entity en Java/Hibernate)
Base = declarative_base()

# Dependencia para inyectar la sesión de base de datos en los endpoints
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()