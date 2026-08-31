from pydantic_settings import BaseSettings, SettingsConfigDict

# ==========================================
# CONFIGURACIÓN CENTRAL (pydantic-settings)
# Todos los secretos (URL de base de datos, SECRET_KEY) se leen del entorno
# o de un fichero .env (no versionado). Nunca se dejan quemados en el código.
# Consulta backend-api/.env.example para ver las variables necesarias.
# ==========================================


class Settings(BaseSettings):
    # --- Base de datos ---
    # URL de conexión SQLAlchemy. Formato:
    #   mysql+pymysql://usuario:contraseña@host:puerto/basededatos
    # Se define en .env (ver .env.example). El puerto 3307 corresponde al
    # mapeo de Docker (ver database/docker-compose.yml).
    DATABASE_URL: str

    # --- JWT ---
    # Clave de firma de los tokens. Generar una nueva con:
    #   python -c "import secrets; print(secrets.token_hex(32))"
    # Debe definirse en .env; nunca quemarla en el código.
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # --- Asistente virtual (modelo de lenguaje) ---
    # Proveedor del LLM, con API compatible con OpenAI. Los valores por defecto
    # apuntan a LM Studio en local (desarrollo); para usar un proveedor
    # gestionado basta cambiar estas variables en .env, SIN tocar código.
    LLM_BASE_URL: str = "http://localhost:1234/v1"
    # Clave de API del proveedor. En LM Studio local NO se valida (el valor por
    # defecto es inocuo), pero apuntando a un proveedor real ES UN SECRETO:
    # defínela en .env y nunca la dejes en el código ni la versiones.
    LLM_API_KEY: str = "lm-studio"
    # Identificador del modelo a usar en el proveedor.
    LLM_MODEL: str = "meta-llama-3.1-8b-instruct"
    # Tiempo máximo de espera (segundos) por CADA llamada al modelo, para que una
    # petición no quede bloqueada indefinidamente si el proveedor no responde.
    # Ojo: el bucle de rondas del chatbot puede llamar al modelo varias veces, así
    # que el peor caso por turno es (nº de rondas) x este valor.
    LLM_TIMEOUT_SECONDS: float = 30.0

    # Lee variables desde el entorno o un fichero .env si existe.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# Instancia única reutilizada en toda la aplicación (patrón singleton).
settings = Settings()
