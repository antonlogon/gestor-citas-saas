package org.example.frontenddesktop.utils;

import org.example.frontenddesktop.NexaCitaApp;
import org.example.frontenddesktop.models.Cita;
import org.example.frontenddesktop.models.Cliente;
import org.example.frontenddesktop.models.Empleado;
import org.example.frontenddesktop.models.HorarioApertura;
import org.example.frontenddesktop.models.Servicio;

import javafx.geometry.Insets;
import javafx.scene.control.ButtonBar;
import javafx.scene.control.ButtonType;
import javafx.scene.control.ComboBox;
import javafx.scene.control.DateCell;
import javafx.scene.control.DatePicker;
import javafx.scene.control.Dialog;
import javafx.scene.control.DialogPane;
import javafx.scene.control.Label;
import javafx.scene.control.TextArea;
import javafx.scene.control.TextField;
import javafx.scene.Node;
import javafx.scene.layout.VBox;
import javafx.stage.Window;
import javafx.util.StringConverter;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * Formularios modales para crear y editar citas. Construido en Java a propósito
 * (ver la nota de {@link Dialogs}): así el compilador valida el cableado.
 *
 * <p>Refleja las limitaciones del backend: al CREAR se eligen paciente,
 * profesional, servicio, fecha y hora; al EDITAR, el backend solo admite cambiar
 * fecha/hora, estado y notas, así que el paciente, el profesional y el servicio
 * se muestran como información NO editable en lugar de ofrecer campos inútiles.
 */
public final class CitaDialog {

    // Los SEGUNDOS (HH:mm:ss) son necesarios, no decorativos. El backend rechaza
    // MOVER una cita al pasado comparando la fecha recibida con la almacenada, y
    // solo valida si DIFIEREN. Al editar una cita antigua se reenvía su fecha tal
    // cual; si aquí recortáramos a HH:mm, una cita cuya hora tenga segundos
    // (p. ej. datos importados/heredados) llegaría distinta a la de la BD, el
    // backend creería que se está moviendo y la rechazaría con 422. Junto con que
    // comboHoras() reincorpora la hora original aunque no caiga en la rejilla de
    // 15 min, esto es lo que permite editar citas pasadas sin falsos rechazos.
    private static final DateTimeFormatter ISO = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss");
    private static final DateTimeFormatter HORA = DateTimeFormatter.ofPattern("HH:mm");

    // Paso de 15 minutos para el desplegable de hora (control acotado, sin texto libre).
    private static final int PASO_MINUTOS = 15;

    // Duración desconocida (aún no se ha elegido servicio): no se filtra por
    // duración, solo por pertenencia a un tramo de apertura.
    private static final int SIN_DURACION = 0;

    // Cuántos días como mucho se miran hacia delante para sugerir el primer día
    // abierto al crear una cita (evita un bucle infinito si algo fuera raro).
    private static final int MAX_DIAS_BUSQUEDA = 14;

    /** Datos de una cita nueva. */
    public record DatosNueva(int clienteId, int empleadoId, int servicioId, String fechaHoraIso) {
    }

    /** Datos editables de una cita existente (lo único que admite el backend). */
    public record DatosEdicion(String fechaHoraIso, String estado, String notas) {
    }

    private CitaDialog() {
        // Clase de utilidad estática.
    }

    // ======================================================================
    // ALTA
    // ======================================================================

    /**
     * Abre el formulario de alta de cita. Las listas se cargan antes en segundo
     * plano (el diálogo no hace HTTP) y se pasan ya resueltas.
     *
     * @param owner            ventana propietaria
     * @param clientes         pacientes seleccionables (lista completa)
     * @param empleados        profesionales activos seleccionables
     * @param servicios        servicios seleccionables
     * @param preselEmpleadoId id del profesional a preseleccionar (el propio
     *                         usuario si es empleado), o {@code null}
     * @param horario          horario de apertura del tenant para no ofrecer días
     *                         ni horas fuera de servicio; {@code null} = sin
     *                         restricción (el backend valida igualmente)
     * @return los datos de la cita, o vacío si se cancela
     */
    public static Optional<DatosNueva> abrirNueva(
            Window owner, List<Cliente> clientes, List<Empleado> empleados,
            List<Servicio> servicios, Integer preselEmpleadoId, HorarioApertura horario) {

        Dialog<DatosNueva> dialogo = new Dialog<>();
        dialogo.initOwner(owner);
        dialogo.setTitle("Nueva cita");
        DialogPane pane = dialogo.getDialogPane();
        estilar(pane);

        ButtonType crear = new ButtonType("Crear", ButtonBar.ButtonData.OK_DONE);
        pane.getButtonTypes().addAll(ButtonType.CANCEL, crear);

        ComboBox<Cliente> paciente = new ComboBox<>();
        paciente.getItems().setAll(clientes);
        paciente.setConverter(conversorCliente());
        paciente.getStyleClass().add("form-field");
        paciente.setMaxWidth(Double.MAX_VALUE);

        ComboBox<Empleado> profesional = new ComboBox<>();
        profesional.getItems().setAll(empleados);
        profesional.setConverter(conversorEmpleado());
        profesional.getStyleClass().add("form-field");
        profesional.setMaxWidth(Double.MAX_VALUE);
        // Preselección del propio profesional (recepción puede cambiarlo).
        if (preselEmpleadoId != null) {
            empleados.stream()
                    .filter(e -> preselEmpleadoId.equals(e.getId()))
                    .findFirst()
                    .ifPresent(profesional::setValue);
        }

        ComboBox<Servicio> servicio = new ComboBox<>();
        servicio.getItems().setAll(servicios);
        servicio.setConverter(conversorServicio());
        servicio.getStyleClass().add("form-field");
        servicio.setMaxWidth(Double.MAX_VALUE);

        // La fecha inicial sugerida es el primer día ABIERTO desde hoy, para no
        // arrancar sobre un día cerrado (p. ej. si hoy es sábado) sin horas.
        DatePicker fecha = new DatePicker(primerDiaAbierto(horario, LocalDate.now()));
        fecha.setEditable(false);  // sin texto libre: solo el selector
        configurarCalendario(fecha, LocalDate.now(), horario);
        fecha.getStyleClass().add("form-field");
        fecha.setMaxWidth(Double.MAX_VALUE);

        // El desplegable de horas se recalcula según el día y la duración del
        // servicio elegido: solo aparecen horas de inicio que caben enteras en un
        // tramo de apertura. Sin servicio aún, se muestran las del día sin filtrar
        // por duración.
        ComboBox<LocalTime> hora = crearComboHoras();
        Runnable recalcularHoras = () -> poblarHoras(
                hora, horario, fecha.getValue(), duracionDe(servicio.getValue()), null);
        recalcularHoras.run();

        VBox form = new VBox(10,
                etiqueta("Paciente"), paciente,
                etiqueta("Profesional"), profesional,
                etiqueta("Servicio"), servicio,
                etiqueta("Fecha"), fecha,
                etiqueta("Hora"), hora);
        form.setPadding(new Insets(4));
        form.getStyleClass().add("form-grid");
        pane.setContent(form);

        Node botonCrear = pane.lookupButton(crear);
        Runnable validar = () -> botonCrear.setDisable(
                paciente.getValue() == null || profesional.getValue() == null
                        || servicio.getValue() == null || fecha.getValue() == null
                        || hora.getValue() == null);
        paciente.valueProperty().addListener((o, a, b) -> validar.run());
        profesional.valueProperty().addListener((o, a, b) -> validar.run());
        // Cambiar el servicio o la fecha recalcula las horas válidas (la duración
        // y el día cambian los huecos que caben) antes de revalidar el botón.
        servicio.valueProperty().addListener((o, a, b) -> { recalcularHoras.run(); validar.run(); });
        fecha.valueProperty().addListener((o, a, b) -> { recalcularHoras.run(); validar.run(); });
        hora.valueProperty().addListener((o, a, b) -> validar.run());
        validar.run();

        dialogo.setResultConverter(boton -> {
            if (boton != crear) {
                return null;
            }
            String iso = LocalDateTime.of(fecha.getValue(), hora.getValue()).format(ISO);
            return new DatosNueva(paciente.getValue().getId(), profesional.getValue().getId(),
                    servicio.getValue().getId(), iso);
        });

        return dialogo.showAndWait();
    }

    // ======================================================================
    // EDICIÓN
    // ======================================================================

    /**
     * Abre el formulario de edición. El paciente, el profesional y el servicio
     * se muestran como texto NO editable (el backend no permite cambiarlos); solo
     * fecha/hora, estado y notas son editables.
     *
     * @param owner            ventana propietaria
     * @param cita             cita a editar (aporta los nombres aplanados y los
     *                         valores actuales)
     * @param horario          horario de apertura del tenant; {@code null} = sin
     *                         restricción
     * @param duracionMinutos  duración del servicio de la cita (resuelta por el
     *                         controlador), para filtrar las horas válidas;
     *                         {@code null} si no se conoce
     * @return los datos editados, o vacío si se cancela
     */
    public static Optional<DatosEdicion> abrirEdicion(
            Window owner, Cita cita, HorarioApertura horario, Integer duracionMinutos) {
        Dialog<DatosEdicion> dialogo = new Dialog<>();
        dialogo.initOwner(owner);
        dialogo.setTitle("Editar cita");
        DialogPane pane = dialogo.getDialogPane();
        estilar(pane);

        ButtonType guardar = new ButtonType("Guardar", ButtonBar.ButtonData.OK_DONE);
        pane.getButtonTypes().addAll(ButtonType.CANCEL, guardar);

        // Datos NO editables (informativos): paciente, profesional y servicio.
        Label avisoNoEditable = new Label(
                "El paciente, el profesional y el servicio no pueden cambiarse una vez "
                + "creada la cita. Para cambiarlos, crea una cita nueva.");
        avisoNoEditable.setWrapText(true);
        avisoNoEditable.getStyleClass().add("dialog-nota");

        // Fecha y hora actuales (parseadas de la cita).
        LocalDateTime actual = parseFecha(cita.getFechaHora());
        LocalDate fechaInicial = actual != null ? actual.toLocalDate() : LocalDate.now();
        LocalTime horaInicial = actual != null ? actual.toLocalTime() : LocalTime.of(9, 0);

        DatePicker fecha = new DatePicker(fechaInicial);
        fecha.setEditable(false);
        // Si la cita ya era pasada, su propio día sigue siendo seleccionable para
        // no impedir editarla; lo que no se permite es moverla aún más atrás. Los
        // días cerrados se deshabilitan igual que en el alta.
        configurarCalendario(fecha,
                fechaInicial.isBefore(LocalDate.now()) ? fechaInicial : LocalDate.now(),
                horario);
        fecha.getStyleClass().add("form-field");
        fecha.setMaxWidth(Double.MAX_VALUE);

        // Horas válidas para el día y la duración de la cita, recalculadas al
        // cambiar la fecha. La hora ORIGINAL se conserva siempre seleccionable
        // aunque ya no sea válida (día cerrado o cambio de horario), para no
        // impedir editar citas antiguas.
        int duracion = duracionMinutos != null ? duracionMinutos : SIN_DURACION;
        ComboBox<LocalTime> hora = crearComboHoras();
        Runnable recalcularHoras = () -> poblarHoras(
                hora, horario, fecha.getValue(), duracion, horaInicial);
        recalcularHoras.run();

        ComboBox<String> estado = new ComboBox<>();
        estado.getItems().setAll("PENDIENTE", "CONFIRMADA", "CANCELADA");
        estado.setConverter(conversorEstado());
        estado.setValue(cita.getEstado() != null ? cita.getEstado().toUpperCase() : "PENDIENTE");
        estado.getStyleClass().add("form-field");
        estado.setMaxWidth(Double.MAX_VALUE);

        TextArea notas = new TextArea(cita.getNotasIa() == null ? "" : cita.getNotasIa());
        notas.setPromptText("Notas de la cita (opcional)");
        notas.setPrefRowCount(3);
        notas.setWrapText(true);
        notas.getStyleClass().add("form-field");

        VBox form = new VBox(10,
                soloLectura("Paciente", cita.getClienteNombre()),
                soloLectura("Profesional", cita.getEmpleadoNombre()),
                soloLectura("Servicio", cita.getServicioNombre()),
                avisoNoEditable,
                etiqueta("Fecha"), fecha,
                etiqueta("Hora"), hora,
                etiqueta("Estado"), estado,
                etiqueta("Notas"), notas);
        form.setPadding(new Insets(4));
        form.getStyleClass().add("form-grid");
        pane.setContent(form);

        Node botonGuardar = pane.lookupButton(guardar);
        Runnable validar = () -> botonGuardar.setDisable(
                fecha.getValue() == null || hora.getValue() == null || estado.getValue() == null);
        // Al cambiar la fecha se recalculan las horas válidas de ese día.
        fecha.valueProperty().addListener((o, a, b) -> { recalcularHoras.run(); validar.run(); });
        hora.valueProperty().addListener((o, a, b) -> validar.run());
        estado.valueProperty().addListener((o, a, b) -> validar.run());
        validar.run();

        dialogo.setResultConverter(boton -> {
            if (boton != guardar) {
                return null;
            }
            String iso = LocalDateTime.of(fecha.getValue(), hora.getValue()).format(ISO);
            return new DatosEdicion(iso, estado.getValue(), notas.getText());
        });

        return dialogo.showAndWait();
    }

    // ======================================================================
    // Utilidades internas
    // ======================================================================

    /** Aplica los tokens del sistema de diseño al diálogo. */
    private static void estilar(DialogPane pane) {
        pane.getStylesheets().addAll(
                NexaCitaApp.class.getResource("styles/theme.css").toExternalForm(),
                NexaCitaApp.class.getResource("styles/dashboard.css").toExternalForm());
        pane.getStyleClass().add("app-dialog");
        pane.setMinWidth(380);
    }

    /** Crea el desplegable de horas (vacío); se rellena con {@link #poblarHoras}. */
    private static ComboBox<LocalTime> crearComboHoras() {
        ComboBox<LocalTime> combo = new ComboBox<>();
        combo.setConverter(new StringConverter<>() {
            @Override
            public String toString(LocalTime valor) {
                return valor == null ? "" : valor.format(HORA);
            }

            @Override
            public LocalTime fromString(String texto) {
                return null;  // no editable: la selección es por lista
            }
        });
        combo.getStyleClass().add("form-field");
        combo.setMaxWidth(Double.MAX_VALUE);
        return combo;
    }

    /**
     * Rellena el desplegable con las horas de inicio VÁLIDAS para el día y la
     * duración dados (las que caben enteras en un tramo de apertura). Si no hay
     * horario (o no se conoce el día), cae en la rejilla de 24h sin restricción,
     * como antes. Conserva la selección previa si sigue siendo válida.
     *
     * @param combo     desplegable a rellenar
     * @param horario   horario del tenant, o {@code null} para no restringir
     * @param dia       día seleccionado
     * @param duracion  duración de la cita en minutos ({@link #SIN_DURACION} si no
     *                  se conoce)
     * @param original  hora que debe permanecer siempre seleccionable aunque no
     *                  sea válida (la de una cita en edición), o {@code null}
     */
    private static void poblarHoras(ComboBox<LocalTime> combo, HorarioApertura horario,
                                    LocalDate dia, int duracion, LocalTime original) {
        LocalTime seleccionPrevia = combo.getValue();

        List<LocalTime> horas = (horario == null || dia == null)
                ? rejilla24h()
                : new ArrayList<>(horario.horasValidas(dia, duracion, PASO_MINUTOS));

        // La hora original de una cita en edición sigue seleccionable aunque ya no
        // sea válida (día cerrado o cambio de horario), para no impedir editarla.
        if (original != null && !horas.contains(original)) {
            horas.add(original);
            horas.sort(LocalTime::compareTo);
        }
        combo.getItems().setAll(horas);

        // Conserva la selección previa si sigue disponible; si no, la original; y
        // en último término la primera hora válida (o null si el día está cerrado).
        if (seleccionPrevia != null && horas.contains(seleccionPrevia)) {
            combo.setValue(seleccionPrevia);
        } else if (original != null && horas.contains(original)) {
            combo.setValue(original);
        } else {
            combo.setValue(horas.isEmpty() ? null : horas.get(0));
        }
    }

    /** Rejilla de 24h en pasos de 15 min (comportamiento sin restricción de horario). */
    private static List<LocalTime> rejilla24h() {
        List<LocalTime> horas = new ArrayList<>();
        LocalTime t = LocalTime.of(0, 0);
        // El último tramo del día evita desbordar a 00:00.
        for (int i = 0; i < (24 * 60) / PASO_MINUTOS; i++) {
            horas.add(t);
            t = t.plusMinutes(PASO_MINUTOS);
        }
        return horas;
    }

    /** Duración del servicio en minutos, o {@link #SIN_DURACION} si no hay servicio. */
    private static int duracionDe(Servicio servicio) {
        return servicio != null && servicio.getDuracionMinutos() != null
                ? servicio.getDuracionMinutos()
                : SIN_DURACION;
    }

    /**
     * Primer día ABIERTO (con algún tramo) a partir de {@code desde}, inclusive.
     * Con horario {@code null} devuelve {@code desde} sin más. Si no encuentra
     * ninguno en {@link #MAX_DIAS_BUSQUEDA} días (no debería ocurrir), devuelve
     * {@code desde} para no dejar el formulario sin fecha.
     */
    private static LocalDate primerDiaAbierto(HorarioApertura horario, LocalDate desde) {
        if (horario == null) {
            return desde;
        }
        LocalDate dia = desde;
        for (int i = 0; i < MAX_DIAS_BUSQUEDA; i++) {
            if (!horario.estaCerrado(dia)) {
                return dia;
            }
            dia = dia.plusDays(1);
        }
        return desde;
    }

    /** Etiqueta + campo de solo lectura (para los datos no editables). */
    private static VBox soloLectura(String etiqueta, String valor) {
        TextField campo = new TextField(valor == null ? "" : valor);
        campo.setEditable(false);
        campo.setDisable(true);  // aspecto claramente inerte
        campo.getStyleClass().add("form-field");
        campo.setMaxWidth(Double.MAX_VALUE);
        VBox caja = new VBox(4, etiqueta(etiqueta), campo);
        return caja;
    }

    /**
     * Configura un {@link DatePicker} para la agenda clínica:
     *
     * <ul>
     *   <li>Oculta los números de semana ISO que JavaFX muestra por defecto en
     *       las configuraciones regionales europeas: son ruido en este contexto.</li>
     *   <li>Deshabilita los días anteriores a {@code minima}, para que no se
     *       puedan agendar citas en el pasado.</li>
     *   <li>Deshabilita los días en los que la clínica está CERRADA según el
     *       horario del tenant (si se conoce), para no agendar cuando no se abre.</li>
     * </ul>
     *
     * @param picker  el selector a configurar
     * @param minima  primer día seleccionable (inclusive)
     * @param horario horario del tenant, o {@code null} para no marcar cerrados
     */
    private static void configurarCalendario(
            DatePicker picker, LocalDate minima, HorarioApertura horario) {
        picker.setShowWeekNumbers(false);
        picker.setDayCellFactory(columna -> new DateCell() {
            @Override
            public void updateItem(LocalDate dia, boolean vacio) {
                super.updateItem(dia, vacio);
                boolean pasado = dia != null && dia.isBefore(minima);
                boolean cerrado = dia != null && horario != null && horario.estaCerrado(dia);
                setDisable(vacio || pasado || cerrado);
                // Atenuamos los días bloqueados para que se vea que no son elegibles.
                if (pasado || cerrado) {
                    setStyle("-fx-background-color: -color-surface-alt;");
                }
            }
        });
    }

    private static Label etiqueta(String texto) {
        Label label = new Label(texto);
        label.getStyleClass().add("form-label");
        return label;
    }

    private static LocalDateTime parseFecha(String iso) {
        if (iso == null || iso.isBlank()) {
            return null;
        }
        try {
            return LocalDateTime.parse(iso);
        } catch (DateTimeParseException e) {
            return null;
        }
    }

    private static StringConverter<Cliente> conversorCliente() {
        return new StringConverter<>() {
            @Override
            public String toString(Cliente c) {
                if (c == null) {
                    return "";
                }
                return c.getEmail() == null || c.getEmail().isBlank()
                        ? c.getNombre()
                        : c.getNombre() + " · " + c.getEmail();
            }

            @Override
            public Cliente fromString(String texto) {
                return null;
            }
        };
    }

    private static StringConverter<Empleado> conversorEmpleado() {
        return new StringConverter<>() {
            @Override
            public String toString(Empleado e) {
                if (e == null) {
                    return "";
                }
                return e.getEspecialidad() == null || e.getEspecialidad().isBlank()
                        ? e.getNombre()
                        : e.getNombre() + " · " + e.getEspecialidad();
            }

            @Override
            public Empleado fromString(String texto) {
                return null;
            }
        };
    }

    private static StringConverter<Servicio> conversorServicio() {
        return new StringConverter<>() {
            @Override
            public String toString(Servicio s) {
                if (s == null) {
                    return "";
                }
                return s.getDuracionMinutos() == null
                        ? s.getNombre()
                        : s.getNombre() + " · " + s.getDuracionMinutos() + " min";
            }

            @Override
            public Servicio fromString(String texto) {
                return null;
            }
        };
    }

    /** Muestra el estado Capitalizado ("Pendiente") pero conserva el valor crudo. */
    private static StringConverter<String> conversorEstado() {
        return new StringConverter<>() {
            @Override
            public String toString(String raw) {
                if (raw == null || raw.isBlank()) {
                    return "";
                }
                String limpio = raw.trim().toLowerCase();
                return Character.toUpperCase(limpio.charAt(0)) + limpio.substring(1);
            }

            @Override
            public String fromString(String texto) {
                return texto == null ? null : texto.trim().toUpperCase();
            }
        };
    }
}
