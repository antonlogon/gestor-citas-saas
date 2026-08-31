package org.example.frontenddesktop.controllers;

import org.example.frontenddesktop.models.Cita;
import org.example.frontenddesktop.models.Cliente;
import org.example.frontenddesktop.models.Empleado;
import org.example.frontenddesktop.models.Servicio;
import org.example.frontenddesktop.services.CitaService;
import org.example.frontenddesktop.services.ClienteService;
import org.example.frontenddesktop.services.EmpleadoService;
import org.example.frontenddesktop.services.EmpresaService;
import org.example.frontenddesktop.services.ServicioService;
import org.example.frontenddesktop.utils.CitaDialog;
import org.example.frontenddesktop.utils.Dialogs;
import org.example.frontenddesktop.utils.SessionManager;
import org.example.frontenddesktop.utils.UiFactory;

import javafx.application.Platform;
import javafx.beans.property.ReadOnlyStringWrapper;
import javafx.collections.FXCollections;
import javafx.collections.ObservableList;
import javafx.collections.transformation.FilteredList;
import javafx.collections.transformation.SortedList;
import javafx.concurrent.Task;
import javafx.fxml.FXML;
import javafx.geometry.Pos;
import javafx.scene.control.Button;
import javafx.scene.control.ComboBox;
import javafx.scene.control.Label;
import javafx.scene.control.ProgressIndicator;
import javafx.scene.control.TableCell;
import javafx.scene.control.TableColumn;
import javafx.scene.control.TableView;
import javafx.scene.control.TextField;
import javafx.scene.layout.HBox;
import javafx.scene.layout.VBox;
import javafx.stage.Window;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeParseException;
import java.util.List;
import java.util.Optional;
import java.util.function.Predicate;

/**
 * Controlador de la sección de Citas. Carga las citas reales desde la API
 * mediante {@link CitaService} en un hilo de fondo (Task), calcula los KPIs en
 * cliente a partir de la lista cargada y permite buscar/filtrar en vivo sobre la
 * tabla mediante una {@link FilteredList} (sin nuevas llamadas a la API).
 */
public class CitasController {

    // Opciones del filtro por estado. "Todos" es el centinela sin filtro; el
    // resto se comparan (ignorando mayúsculas) con el estado crudo de la API.
    private static final String ESTADO_TODOS = "Todos";

    @FXML
    private TableView<Cita> citasTable;

    @FXML
    private TableColumn<Cita, String> fechaColumn;

    @FXML
    private TableColumn<Cita, String> estadoColumn;

    @FXML
    private TableColumn<Cita, String> clienteColumn;

    @FXML
    private TableColumn<Cita, String> empleadoColumn;

    @FXML
    private TableColumn<Cita, String> servicioColumn;

    @FXML
    private TextField searchField;

    @FXML
    private ComboBox<String> estadoFilter;

    @FXML
    private TableColumn<Cita, Void> accionesColumn;

    @FXML
    private Button nuevaButton;

    @FXML
    private Button refreshButton;

    @FXML
    private ProgressIndicator progressIndicator;

    @FXML
    private Label statusLabel;

    @FXML
    private VBox tarjetaHoy;

    @FXML
    private VBox tarjetaPendientes;

    @FXML
    private VBox tarjetaConfirmadas;

    @FXML
    private VBox tarjetaCanceladas;

    @FXML
    private Label kpiHoy;

    @FXML
    private Label kpiPendientes;

    @FXML
    private Label kpiConfirmadas;

    @FXML
    private Label kpiCanceladas;

    // Filtro "solo hoy" activado desde la tarjeta de KPI. El filtro por ESTADO
    // no necesita variable propia: reutiliza el ComboBox, de modo que al pulsar
    // una tarjeta el desplegable refleja el cambio y el usuario ve qué se aplicó.
    private boolean soloHoy = false;

    private final CitaService citaService = new CitaService();
    private final ClienteService clienteService = new ClienteService();
    private final EmpleadoService empleadoService = new EmpleadoService();
    private final ServicioService servicioService = new ServicioService();
    private final EmpresaService empresaService = new EmpresaService();

    // Lista maestra (todas las citas cargadas) y su vista filtrada para la tabla.
    private final ObservableList<Cita> masterData = FXCollections.observableArrayList();
    private final FilteredList<Cita> filteredData = new FilteredList<>(masterData, cita -> true);

    @FXML
    private void initialize() {
        // Value factories con lambdas: usan los nombres "aplanados" que ya
        // devuelve la API y la fecha formateada en español. El id de la cita no
        // se muestra (ruido de BD): permanece en el modelo para acciones futuras.
        fechaColumn.setCellValueFactory(cell -> text(cell.getValue().getFechaHoraLegible()));
        estadoColumn.setCellValueFactory(cell -> text(cell.getValue().getEstado()));
        clienteColumn.setCellValueFactory(cell -> text(cell.getValue().getClienteNombre()));
        empleadoColumn.setCellValueFactory(cell -> text(cell.getValue().getEmpleadoNombre()));
        servicioColumn.setCellValueFactory(cell -> text(cell.getValue().getServicioNombre()));

        // La columna Estado se pinta como un "badge" de color.
        estadoColumn.setCellFactory(col -> new EstadoBadgeCell());

        // Filtro por estado: "Todos" + los tres estados posibles (Capitalizado).
        estadoFilter.setItems(FXCollections.observableArrayList(
                ESTADO_TODOS, "Pendiente", "Confirmada", "Cancelada"));
        estadoFilter.setValue(ESTADO_TODOS);

        // Búsqueda y filtro en vivo: cualquier cambio recalcula el predicado.
        searchField.textProperty().addListener((obs, oldV, newV) -> actualizarFiltro());
        estadoFilter.valueProperty().addListener((obs, oldV, newV) -> actualizarFiltro());

        // La tabla observa una SortedList sobre la filtrada: así ordenar por
        // cabecera funciona sin lanzar excepción (la FilteredList no es ordenable
        // directamente) y respeta el filtro activo.
        SortedList<Cita> sortedData = new SortedList<>(filteredData);
        sortedData.comparatorProperty().bind(citasTable.comparatorProperty());
        citasTable.setItems(sortedData);
        citasTable.setPlaceholder(UiFactory.tablePlaceholder(
                "M4 8H40V40H4Z M4 16H40 M13 4V12 M31 4V12",
                "No hay citas que mostrar",
                "Cuando existan citas o ajustes los filtros, aparecerán aquí."));

        // Columna de acciones por fila: Editar / Confirmar / Cancelar / Eliminar.
        accionesColumn.setCellFactory(col -> new AccionesCitaCell());

        configurarKpisClicables();

        cargarCitas();
    }

    @FXML
    private void onRefresh() {
        cargarCitas();
    }

    // ------------------ Altas, ediciones, estados y bajas ------------------

    /**
     * Alta de cita: carga en segundo plano las listas de pacientes, profesionales
     * (solo activos) y servicios, abre el formulario y, si se confirma, crea la
     * cita. Las listas se cargan fuera del hilo de la UI; el diálogo se abre ya
     * con los datos resueltos.
     */
    @FXML
    private void onNueva() {
        Task<Listas> carga = new Task<>() {
            @Override
            protected Listas call() throws Exception {
                return new Listas(
                        clienteService.listarTodos(),
                        empleadoService.listarActivos(),
                        servicioService.listarTodos());
            }
        };
        carga.setOnSucceeded(e -> {
            setBusy(false);
            Listas listas = carga.getValue();
            if (listas.empleados().isEmpty() || listas.servicios().isEmpty()) {
                Dialogs.error(ventana(), "Para crear una cita hacen falta al menos un "
                        + "profesional activo y un servicio.");
                return;
            }
            // Preselección del propio profesional si quien agenda es empleado.
            Integer preselección = "empleado".equalsIgnoreCase(SessionManager.getTipo())
                    ? SessionManager.getUserId() : null;
            Optional<CitaDialog.DatosNueva> datos = CitaDialog.abrirNueva(
                    ventana(), listas.clientes(), listas.empleados(), listas.servicios(),
                    preselección, SessionManager.getHorario());
            datos.ifPresent(this::crearCita);
        });
        carga.setOnFailed(e -> mostrarError(carga, "No se pudieron cargar los datos del formulario."));
        lanzar(carga, "carga-formulario-cita");
    }

    /** Envía el alta de la cita a la API. */
    private void crearCita(CitaDialog.DatosNueva d) {
        Task<Cita> task = new Task<>() {
            @Override
            protected Cita call() throws Exception {
                return citaService.crear(d.clienteId(), d.empleadoId(), d.servicioId(),
                        d.fechaHoraIso());
            }
        };
        task.setOnSucceeded(e -> {
            statusLabel.setText("Cita creada.");
            setBusy(false);
            cargarCitas();
        });
        task.setOnFailed(e -> mostrarError(task, "No se pudo crear la cita."));
        lanzar(task, "crear-cita");
    }

    /**
     * Abre el formulario de edición (fecha/hora, estado y notas) y guarda.
     *
     * <p>Antes de abrirlo resuelve en segundo plano la DURACIÓN del servicio de la
     * cita (que el modelo Cita no trae), para que el desplegable de horas ofrezca
     * solo huecos que caben en el horario. Es best-effort: si no se puede cargar,
     * se abre igual sin filtrar por duración (el backend valida de todos modos).
     */
    private void editar(Cita cita) {
        Task<Integer> carga = new Task<>() {
            @Override
            protected Integer call() {
                try {
                    return duracionDeServicio(servicioService.listarTodos(), cita.getServicioId());
                } catch (ServicioService.ServicioException e) {
                    return null;  // sin duración: el diálogo no filtra por ella
                }
            }
        };
        carga.setOnSucceeded(e -> {
            setBusy(false);
            Optional<CitaDialog.DatosEdicion> datos = CitaDialog.abrirEdicion(
                    ventana(), cita, SessionManager.getHorario(), carga.getValue());
            datos.ifPresent(d -> guardarEdicion(cita, d));
        });
        carga.setOnFailed(e -> mostrarError(carga, "No se pudo abrir el formulario de edición."));
        lanzar(carga, "carga-edicion-cita");
    }

    /** Envía la edición (fecha/hora, estado y notas) de una cita a la API. */
    private void guardarEdicion(Cita cita, CitaDialog.DatosEdicion d) {
        Task<Cita> task = new Task<>() {
            @Override
            protected Cita call() throws Exception {
                return citaService.editar(cita.getId(), d.fechaHoraIso(), d.estado(), d.notas());
            }
        };
        task.setOnSucceeded(e -> {
            statusLabel.setText("Cita actualizada.");
            setBusy(false);
            cargarCitas();
        });
        task.setOnFailed(e -> mostrarError(task, "No se pudo actualizar la cita."));
        lanzar(task, "editar-cita");
    }

    /** Duración (min) del servicio con ese id en la lista, o {@code null} si no está. */
    private static Integer duracionDeServicio(List<Servicio> servicios, Integer servicioId) {
        if (servicioId == null) {
            return null;
        }
        return servicios.stream()
                .filter(s -> servicioId.equals(s.getId()))
                .map(Servicio::getDuracionMinutos)
                .findFirst()
                .orElse(null);
    }

    /** Cambio rápido de estado (CONFIRMADA / CANCELADA) sin abrir el formulario. */
    private void cambiarEstado(Cita cita, String estado) {
        Task<Cita> task = new Task<>() {
            @Override
            protected Cita call() throws Exception {
                return citaService.cambiarEstado(cita.getId(), estado);
            }
        };
        task.setOnSucceeded(e -> {
            statusLabel.setText("Cita marcada como " + estado.toLowerCase() + ".");
            setBusy(false);
            cargarCitas();
        });
        task.setOnFailed(e -> mostrarError(task, "No se pudo cambiar el estado de la cita."));
        lanzar(task, "estado-cita");
    }

    /** Pide confirmación y elimina la cita. */
    private void eliminar(Cita cita) {
        boolean confirmado = Dialogs.confirmar(
                ventana(), "Eliminar cita",
                "¿Eliminar esta cita? Esta acción no se puede deshacer.", "Eliminar");
        if (!confirmado) {
            return;
        }
        Task<Void> task = new Task<>() {
            @Override
            protected Void call() throws Exception {
                citaService.eliminar(cita.getId());
                return null;
            }
        };
        task.setOnSucceeded(e -> {
            statusLabel.setText("Cita eliminada.");
            setBusy(false);
            cargarCitas();
        });
        task.setOnFailed(e -> mostrarError(task, "No se pudo eliminar la cita."));
        lanzar(task, "eliminar-cita");
    }

    // ------------------ Utilidades de escritura ------------------

    /** Listas necesarias para el formulario de alta. */
    private record Listas(List<Cliente> clientes, List<Empleado> empleados, List<Servicio> servicios) {
    }

    /** Lanza un Task de escritura en un hilo demonio, deshabilitando la UI. */
    private void lanzar(Task<?> task, String nombreHilo) {
        setBusy(true);
        Thread thread = new Thread(task, nombreHilo);
        thread.setDaemon(true);
        thread.start();
    }

    /** Muestra el mensaje de error de la API (o uno por defecto) en un diálogo. */
    private void mostrarError(Task<?> task, String porDefecto) {
        Throwable error = task.getException();
        String mensaje;
        if (error instanceof CitaService.CitaException
                || error instanceof ClienteService.ClienteException
                || error instanceof EmpleadoService.EmpleadoException
                || error instanceof ServicioService.ServicioException) {
            mensaje = error.getMessage();
        } else {
            mensaje = porDefecto;
        }
        setBusy(false);
        Dialogs.error(ventana(), mensaje);
    }

    /** Ventana actual, para anclar los diálogos modales. */
    private Window ventana() {
        return citasTable.getScene().getWindow();
    }

    // ------------------ Carga de datos ------------------

    /**
     * Lanza en segundo plano la carga del listado (paginado por el backend) y de
     * los recuentos agregados (KPIs, calculados en SQL sobre TODO el tenant), y
     * actualiza la tabla y los indicadores al terminar.
     */
    private void cargarCitas() {
        Task<Carga> task = new Task<>() {
            @Override
            protected Carga call() throws Exception {
                // Horario de apertura del tenant: se carga UNA sola vez por sesión
                // (no cambia mientras dura) y se cachea para que el formulario de
                // cita lo reutilice sin pedirlo a la API en cada apertura. Es un
                // dato "de ayuda" para la UI: si falla, se degrada a sin restricción.
                if (SessionManager.getHorario() == null) {
                    try {
                        SessionManager.setHorario(empresaService.obtenerHorario());
                    } catch (EmpresaService.EmpresaException ignorada) {
                        // El backend valida el horario igualmente; no bloqueamos la
                        // carga de citas por no poder pintar las restricciones.
                    }
                }
                // El resumen no depende de la paginación: da los totales reales.
                return new Carga(citaService.listar(), citaService.resumen());
            }
        };

        task.setOnSucceeded(event -> {
            Carga carga = task.getValue();
            masterData.setAll(carga.citas());      // dispara el refresco de la vista filtrada
            aplicarKpis(carga.resumen());

            // CitaService.listar() recorre todas las páginas, así que lo normal
            // es que visibles == total. La rama de "Mostrando X de Y" queda como
            // red de seguridad: si alguna vez se cargaran menos filas que el
            // total del servidor, el contador lo dice en lugar de dar a entender
            // que lo visible es todo. Importa porque las tarjetas de KPI filtran
            // sobre lo cargado y sus cifras vienen del servidor.
            int visibles = carga.citas().size();
            int total = carga.resumen().total();
            statusLabel.setText(visibles < total
                    ? "Mostrando " + visibles + " de " + total + " citas"
                    : total + " cita(s)");
            setBusy(false);
        });

        task.setOnFailed(event -> {
            Throwable error = task.getException();
            String message = (error instanceof CitaService.CitaException)
                    ? error.getMessage()
                    : "No se pudieron cargar las citas.";
            masterData.clear();
            aplicarKpis(new CitaService.Resumen(0, 0, 0, 0, 0));
            statusLabel.setText(message);
            setBusy(false);
        });

        setBusy(true);
        statusLabel.setText("");
        Thread thread = new Thread(task, "citas-task");
        thread.setDaemon(true);
        thread.start();
    }

    /** Datos de una carga: el listado (paginado) y los recuentos agregados. */
    private record Carga(List<Cita> citas, CitaService.Resumen resumen) {
    }

    // ------------------ Filtro en vivo ------------------

    /**
     * Recalcula el predicado de la {@link FilteredList} combinando el texto de
     * búsqueda (paciente / servicio / empleado) y el estado seleccionado.
     */
    private void actualizarFiltro() {
        String texto = searchField.getText() == null ? "" : searchField.getText().trim().toLowerCase();
        String estadoSel = estadoFilter.getValue();

        Predicate<Cita> porTexto = cita -> texto.isEmpty()
                || contiene(cita.getClienteNombre(), texto)
                || contiene(cita.getServicioNombre(), texto)
                || contiene(cita.getEmpleadoNombre(), texto);

        Predicate<Cita> porEstado = cita -> estadoSel == null || ESTADO_TODOS.equals(estadoSel)
                || (cita.getEstado() != null && cita.getEstado().equalsIgnoreCase(estadoSel));

        // "Citas hoy" replica la definición del servidor: las canceladas NO
        // cuentan, porque no ocupan agenda. Si divergiera, el número de la
        // tarjeta no cuadraría con las filas mostradas al pulsarla.
        Predicate<Cita> porHoy = cita -> !soloHoy
                || (esDeHoy(cita) && !"CANCELADA".equalsIgnoreCase(cita.getEstado()));

        filteredData.setPredicate(porTexto.and(porEstado).and(porHoy));
    }

    private static boolean contiene(String valor, String textoLower) {
        return valor != null && valor.toLowerCase().contains(textoLower);
    }

    // ------------------ KPIs (recuentos agregados del backend) ------------------

    /** Vuelca en los indicadores los recuentos agregados calculados en SQL. */

    // ------------------ KPIs clicables ------------------

    /**
     * Hace clicables las cuatro tarjetas de KPI: al pulsar una, la tabla muestra
     * únicamente las citas de ese tipo.
     *
     * <p>Los tres KPI de estado reutilizan el ComboBox de filtro en lugar de
     * llevar su propia variable: así el desplegable refleja lo aplicado y el
     * usuario ve por qué la tabla ha cambiado. El de "hoy" es otro eje y usa el
     * indicador {@code soloHoy}.
     *
     * <p>Cada tarjeta aplica su criterio en EXCLUSIVA y limpia el otro eje, de
     * modo que lo mostrado abajo se corresponde siempre con el número de la
     * tarjeta pulsada. Volver a pulsar la tarjeta activa deshace el filtro.
     */
    private void configurarKpisClicables() {
        tarjetaHoy.setOnMouseClicked(e -> alternarKpi(null, true));
        tarjetaPendientes.setOnMouseClicked(e -> alternarKpi("Pendiente", false));
        tarjetaConfirmadas.setOnMouseClicked(e -> alternarKpi("Confirmada", false));
        tarjetaCanceladas.setOnMouseClicked(e -> alternarKpi("Cancelada", false));

        // El resaltado debe seguir siendo correcto aunque el usuario cambie el
        // ComboBox a mano, así que se deriva del estado en lugar de recordarse.
        estadoFilter.valueProperty().addListener((obs, oldV, newV) -> refrescarKpiActivo());
    }

    /** Activa el criterio de una tarjeta, o lo desactiva si ya estaba activo. */
    private void alternarKpi(String estado, boolean esHoy) {
        boolean yaActivo = esHoy
                ? soloHoy
                : (!soloHoy && estado.equals(estadoFilter.getValue()));

        if (yaActivo) {
            soloHoy = false;
            estadoFilter.setValue(ESTADO_TODOS);   // dispara actualizarFiltro()
        } else if (esHoy) {
            soloHoy = true;
            estadoFilter.setValue(ESTADO_TODOS);   // un eje cada vez
        } else {
            soloHoy = false;
            estadoFilter.setValue(estado);
        }
        actualizarFiltro();
        refrescarKpiActivo();
    }

    /** Marca visualmente la tarjeta cuyo criterio está aplicado (si hay alguno). */
    private void refrescarKpiActivo() {
        String estadoSel = estadoFilter.getValue();
        marcarActiva(tarjetaHoy, soloHoy);
        marcarActiva(tarjetaPendientes, !soloHoy && "Pendiente".equals(estadoSel));
        marcarActiva(tarjetaConfirmadas, !soloHoy && "Confirmada".equals(estadoSel));
        marcarActiva(tarjetaCanceladas, !soloHoy && "Cancelada".equals(estadoSel));
    }

    private static void marcarActiva(VBox tarjeta, boolean activa) {
        tarjeta.getStyleClass().remove("kpi-activa");
        if (activa) {
            tarjeta.getStyleClass().add("kpi-activa");
        }
    }

    /**
     * Deshabilita las tarjetas cuyo recuento es cero: no tiene sentido filtrar
     * por un criterio sin resultados. Si la tarjeta activa se queda a cero tras
     * recargar, se limpia su filtro para no dejar la tabla vacía sin explicación.
     */
    private void actualizarDisponibilidadKpis(CitaService.Resumen resumen) {
        tarjetaHoy.setDisable(resumen.hoy() == 0);
        tarjetaPendientes.setDisable(resumen.pendientes() == 0);
        tarjetaConfirmadas.setDisable(resumen.confirmadas() == 0);
        tarjetaCanceladas.setDisable(resumen.canceladas() == 0);

        if ((soloHoy && resumen.hoy() == 0)
                || ("Pendiente".equals(estadoFilter.getValue()) && resumen.pendientes() == 0)
                || ("Confirmada".equals(estadoFilter.getValue()) && resumen.confirmadas() == 0)
                || ("Cancelada".equals(estadoFilter.getValue()) && resumen.canceladas() == 0)) {
            soloHoy = false;
            estadoFilter.setValue(ESTADO_TODOS);
            actualizarFiltro();
        }
        refrescarKpiActivo();
    }

    /** True si la cita es del día de hoy. Tolera una fecha no parseable. */
    private static boolean esDeHoy(Cita cita) {
        String iso = cita.getFechaHora();
        if (iso == null) {
            return false;
        }
        try {
            return LocalDateTime.parse(iso).toLocalDate().equals(LocalDate.now());
        } catch (DateTimeParseException e) {
            return false;
        }
    }

    private void aplicarKpis(CitaService.Resumen resumen) {
        kpiHoy.setText(Integer.toString(resumen.hoy()));
        kpiPendientes.setText(Integer.toString(resumen.pendientes()));
        kpiConfirmadas.setText(Integer.toString(resumen.confirmadas()));
        kpiCanceladas.setText(Integer.toString(resumen.canceladas()));
        actualizarDisponibilidadKpis(resumen);
    }

    // ------------------ Estado de la UI ------------------

    private void setBusy(boolean busy) {
        // Puede invocarse desde callbacks del Task, ya en el hilo de la UI.
        Runnable apply = () -> {
            refreshButton.setDisable(busy);
            nuevaButton.setDisable(busy);
            progressIndicator.setVisible(busy);
        };
        if (Platform.isFxApplicationThread()) {
            apply.run();
        } else {
            Platform.runLater(apply);
        }
    }

    /** Envuelve un valor en una propiedad de texto, mostrando "" si es nulo. */
    private static ReadOnlyStringWrapper text(Object value) {
        return new ReadOnlyStringWrapper(value == null ? "" : value.toString());
    }

    /**
     * Celda con las acciones de cada cita: Editar (formulario), Confirmar y
     * Cancelar (cambio rápido de estado) y Eliminar. Confirmar/Cancelar se
     * deshabilitan cuando la cita ya está en ese estado, para no lanzar cambios
     * sin efecto.
     */
    private class AccionesCitaCell extends TableCell<Cita, Void> {

        private final Button editar = new Button("Editar");
        private final Button confirmar = new Button("Confirmar");
        private final Button cancelar = new Button("Cancelar");
        private final Button eliminar = new Button("Eliminar");
        private final HBox caja = new HBox(6, editar, confirmar, cancelar, eliminar);

        AccionesCitaCell() {
            editar.getStyleClass().add("button-row");
            confirmar.getStyleClass().add("button-row");
            cancelar.getStyleClass().addAll("button-row", "button-row-danger");
            eliminar.getStyleClass().addAll("button-row", "button-row-danger");
            caja.setAlignment(Pos.CENTER_LEFT);
            editar.setOnAction(e -> editar(getFila()));
            confirmar.setOnAction(e -> cambiarEstado(getFila(), "CONFIRMADA"));
            cancelar.setOnAction(e -> cambiarEstado(getFila(), "CANCELADA"));
            eliminar.setOnAction(e -> eliminar(getFila()));
        }

        private Cita getFila() {
            return getTableView().getItems().get(getIndex());
        }

        @Override
        protected void updateItem(Void item, boolean empty) {
            super.updateItem(item, empty);
            if (empty || getIndex() >= getTableView().getItems().size()) {
                setGraphic(null);
                return;
            }
            String estado = getFila().getEstado();
            // No reconfirmar lo confirmado ni recancelar lo cancelado.
            confirmar.setDisable("CONFIRMADA".equalsIgnoreCase(estado));
            cancelar.setDisable("CANCELADA".equalsIgnoreCase(estado));
            setGraphic(caja);
        }
    }

    /**
     * Celda que pinta el estado de la cita como una etiqueta de color ("badge").
     * El color se aplica vía clases CSS (badge-pendiente / -confirmada / -cancelada)
     * definidas en dashboard.css, y el texto se muestra Capitalizado, no en
     * MAYÚSCULAS (PENDIENTE -> "Pendiente").
     */
    private static class EstadoBadgeCell extends TableCell<Cita, String> {

        private final Label badge = new Label();

        EstadoBadgeCell() {
            badge.getStyleClass().add("badge");
        }

        @Override
        protected void updateItem(String estado, boolean empty) {
            super.updateItem(estado, empty);
            if (empty || estado == null || estado.isBlank()) {
                setGraphic(null);
                return;
            }

            badge.setText(capitalizar(estado));
            // Reiniciamos las clases modificadoras antes de aplicar la que toca,
            // para que las celdas reutilizadas no arrastren el color anterior.
            badge.getStyleClass().removeAll(
                    "badge-pendiente", "badge-confirmada", "badge-cancelada");
            switch (estado.toUpperCase()) {
                case "PENDIENTE" -> badge.getStyleClass().add("badge-pendiente");
                case "CONFIRMADA" -> badge.getStyleClass().add("badge-confirmada");
                case "CANCELADA" -> badge.getStyleClass().add("badge-cancelada");
                default -> { /* estado desconocido: badge neutro por defecto */ }
            }
            setGraphic(badge);
        }
    }

    /** Convierte "PENDIENTE" en "Pendiente" (primera letra mayúscula, resto minúsculas). */
    private static String capitalizar(String texto) {
        if (texto == null || texto.isBlank()) {
            return "";
        }
        String limpio = texto.trim().toLowerCase();
        return Character.toUpperCase(limpio.charAt(0)) + limpio.substring(1);
    }
}
