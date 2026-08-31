# Cliente móvil — NexaCita

Aplicación del paciente. Kotlin sobre Android, con vistas XML y `viewBinding`. Consulta sus próximas citas y conversa con el asistente virtual.

## Arranque

Abre `frontend-mobile/` como proyecto en Android Studio y ejecútalo en un emulador de **API 26 o superior**. El envoltorio de Gradle descarga todo lo necesario.

La API debe estar escuchando en el puerto 8000 de la máquina anfitriona.

## Organización

```
com.example.appclinica
├── AppClinicaApp        clase Application: enlaza el token con el cliente de red
├── LoginActivity        acceso
├── DashboardActivity    próximas citas + botón del asistente
├── ChatActivity         asistente conversacional
├── SessionManager       persistencia del token en SharedPreferences
├── data/model/          DTO de la API y modelo de UI del chat
└── data/remote/         RetrofitClient, ApiService, ChatApiService, AuthInterceptor
```

## Cosas que conviene saber antes de tocar nada

**`10.0.2.2` no es un error.** Es la dirección con la que el emulador de Android alcanza el `localhost` de la máquina anfitriona; desde dentro del emulador, `127.0.0.1` sería el propio dispositivo virtual. Sobre un teléfono físico hay que sustituirla por la IP del equipo en la red local.

**Hay un único punto de acceso a la red, y debe seguir habiendo uno.** Todo sale de `RetrofitClient`: la URL base y la autenticación se definen en un solo sitio.

Llegó a haber dos configuraciones en paralelo, con dos instancias de Retrofit y dos formas distintas de adjuntar el token. El problema no era la duplicación en sí: era que al cambiar la dirección del servidor había que acordarse de tocar los dos sitios, y actualizar solo uno dejaba media aplicación sin funcionar **en silencio**, sin ningún error de compilación. **No crees una segunda instancia de Retrofit.**

**El token lo inyecta el interceptor.** Ninguna operación de `ApiService` declara la cabecera `Authorization`: la añade `AuthInterceptor` a partir del token vigente, que `AppClinicaApp` enlaza con `SessionManager` antes de que arranque ninguna Activity. No lo pases a mano.

**El saludo y las sugerencias del chat los compone la aplicación, no el modelo.** Es deliberado: el modelo tarda segundos en responder, así que un saludo generado aparecería tarde, gastaría tokens en cada apertura y podría equivocarse.

Y **no viajan en el historial**. El historial que se envía se construye a partir de los mensajes visibles, de modo que la bienvenida se marca con `esBienvenida` y se filtra: es una ayuda de interfaz, no un turno de la conversación.

**No se usa Jetpack Compose.** La interfaz es 100 % vistas XML con Material Components. El proyecto arrastraba Compose desde la plantilla de Android Studio sin usarlo en ninguna pantalla, y se retiró. Si añades una pantalla, hazla con vistas.

**La paleta es la misma que la del escritorio**, replicada como recursos de color con nombres semánticos en `res/values/colors.xml`. Los valores están medidos para alcanzar el nivel AAA de contraste; no los aclares sin volver a medir.

## Limitaciones conocidas

- El identificador de paquete sigue siendo `com.example.appclinica`, el de la plantilla. `com.example` está reservado por convención para ejemplos y Google Play no lo acepta, así que habría que renombrarlo antes de una distribución real.
- La dirección de la API está fijada en el código, igual que en el cliente de escritorio.
- No hay pruebas automatizadas. La verificación del proyecto se concentra en el backend, donde viven las reglas de negocio.

Todo ello está razonado en la memoria del proyecto, en la raíz del repositorio.
