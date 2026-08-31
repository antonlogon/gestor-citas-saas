import logging

from fastapi import FastAPI

from app.routers import (
    auth,
    chatbot,
    cita,
    cliente,
    empleado,
    empresa,
    registro,
    servicio,
)

# Configuración del registro (logging) de la aplicación.
#
# Sin esto no se ve NADA de lo que registra el código propio: el módulo estándar
# `logging` descarta los mensajes cuando nadie ha instalado un manejador, y
# uvicorn solo configura los suyos (`uvicorn`, `uvicorn.access`). Los loggers de
# la aplicación propagan a la raíz, que por defecto está vacía, de modo que una
# traza escrita con logger.info() se pierde en silencio y sin error. Se detectó
# así: la medición de consumo de tokens del asistente se ejecutaba y no aparecía
# en ningún sitio.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")

# Inicializamos la aplicación FastAPI
app = FastAPI(
    title="API NexaCita",
    description="Backend inteligente para reservas y gestión de clínicas",
    version="1.0.0",
)

# Registro de routers: cada módulo de negocio vive en app/routers/
app.include_router(auth.router)
app.include_router(registro.router)
app.include_router(empresa.router)
app.include_router(cliente.router)
app.include_router(empleado.router)
app.include_router(servicio.router)
app.include_router(cita.router)
app.include_router(chatbot.router)


# Endpoint de prueba (Health Check)
@app.get("/", tags=["Health"])
def read_root():
    return {"mensaje": "API de NexaCita funcionando correctamente."}
