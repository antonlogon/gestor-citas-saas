# Cliente de escritorio — NexaCita

Panel de gestión para el personal de la clínica. JavaFX 21 sobre Java 21, con el patrón modelo-vista-controlador y las vistas declaradas en FXML.

## Arranque

```bash
./mvnw clean javafx:run
```

No hace falta instalar Maven: el envoltorio lo descarga la primera vez. Sí hace falta un **JDK 21** y que la API esté escuchando en `127.0.0.1:8000`.

## Organización

```
org.example.frontenddesktop
├── NexaCitaApp        punto de entrada (Application)
├── Launcher           lanzador sin módulos, para empaquetar
├── controllers/       un controlador por vista
├── models/            objetos de dominio que devuelve la API
├── services/          acceso HTTP, uno por recurso
└── utils/             diálogos, sesión, serialización y utilidades de interfaz

resources/.../views/   FXML de cada pantalla
resources/.../styles/  theme.css (tokens) + login.css + dashboard.css
```

El proyecto usa el sistema de módulos de Java (`module-info.java`). Al añadir un paquete nuevo con clases que instancie el cargador de FXML por reflexión, hay que abrirlo a `javafx.fxml` o fallará al arrancar.

## Cosas que conviene saber antes de tocar nada

**Compilar no valida el FXML.** `mvn compile` termina con éxito aunque un `fx:id` esté mal escrito, un manejador `onAction` no exista o el `fx:controller` apunte a una clase equivocada: todo eso solo se manifiesta al arrancar la aplicación. Después de tocar una vista, **ejecútala**; no basta con que compile.

De ahí que los diálogos donde se concentra la entrada de datos —alta de cita y de paciente— estén construidos en Java y no en FXML: así los verifica el compilador.

**Si quitas una columna del FXML, quita también su campo `@FXML`.** Si el campo se queda sin su `fx:id` correspondiente, `initialize()` revienta con `NullPointerException` en tiempo de ejecución y la compilación no lo detecta.

**El CSS de JavaFX no es el CSS web.** Es un subconjunto con diferencias que condicionan el diseño:

- No existe `box-shadow`; las sombras se hacen con `-fx-effect: dropshadow(...)`.
- No hay modelos de caja flexibles.
- No hay variables CSS: se usan *looked-up colors* declarados en el selector raíz de `theme.css`.
- Las transformaciones **no afectan al cálculo del layout**, y por eso los iconos son `SVGPath` con las coordenadas ya a tamaño final. No los escales con `-fx-scale-*`.

**`theme.css` va SIEMPRE antes que la hoja específica** en todas las escenas y diálogos:

```java
scene.getStylesheets().addAll(theme, dashboard);
```

Se carga en seis sitios (`NexaCitaApp`, los dos controladores que cambian de escena y los tres diálogos). Si añades una escena nueva, no lo olvides.

**Los colores están medidos, no elegidos.** Cada valor de `theme.css` lleva anotado su ratio de contraste, calculado para alcanzar el nivel AAA de las WCAG. **No los aclares sin volver a medir**: hay tonos que parecen casi iguales y cruzan el umbral.

Tampoco se impone familia tipográfica. Se probó y fue un error: una fuente de trazo fino hacía que un texto casi negro se percibiera gris.

**Toda llamada HTTP va en un `Task` sobre un hilo demonio.** El hilo de la interfaz nunca se bloquea.

## Limitaciones conocidas

- La dirección de la API (`http://127.0.0.1:8000`) está fijada en el código de los seis servicios. Apuntar a otro servidor exige editarla y recompilar.
- Los listados se cargan completos en memoria, recorriendo las páginas de la API, en lugar de filtrar en el servidor. Deja de ser adecuado cuando una clínica acumule años de historial.
- El JSON se serializa con una clase propia (`SimpleJson`) en lugar de una biblioteca. Es una decisión deliberada —cero dependencias y encaja limpio con el sistema de módulos— pero no cubre el caso general.

Todo ello está razonado en la memoria del proyecto, en la raíz del repositorio.
