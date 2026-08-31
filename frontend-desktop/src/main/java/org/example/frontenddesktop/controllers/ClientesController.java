package org.example.frontenddesktop.controllers;

import org.example.frontenddesktop.models.Cliente;
import org.example.frontenddesktop.services.ClienteService;
import org.example.frontenddesktop.utils.Dialogs;
import org.example.frontenddesktop.utils.PacienteDialog;
import org.example.frontenddesktop.utils.PasswordGenerator;
import org.example.frontenddesktop.utils.UiFactory;

import javafx.application.Platform;
import javafx.beans.property.ReadOnlyStringWrapper;
import javafx.collections.FXCollections;
import javafx.concurrent.Task;
import javafx.fxml.FXML;
import javafx.geometry.Pos;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.control.TableCell;
import javafx.scene.control.TableColumn;
import javafx.scene.control.TableView;
import javafx.scene.layout.HBox;
import javafx.stage.Window;

import java.util.List;
import java.util.Optional;

/**
 * Controlador de la sección de Pacientes. Configura la tabla y carga los
 * clientes reales desde la API mediante {@link ClienteService} en un hilo de
 * fondo (Task), tanto al inicializar la vista como al pulsar "Refrescar".
 */
public class ClientesController {

    @FXML
    private TableView<Cliente> clientesTable;

    @FXML
    private TableColumn<Cliente, String> nombreColumn;

    @FXML
    private TableColumn<Cliente, String> emailColumn;

    @FXML
    private TableColumn<Cliente, String> telefonoColumn;

    @FXML
    private TableColumn<Cliente, Void> accionesColumn;

    @FXML
    private Button nuevoButton;

    @FXML
    private Button refreshButton;

    @FXML
    private Label statusLabel;

    private final ClienteService clienteService = new ClienteService();

    @FXML
    private void initialize() {
        // Value factories con lambdas: evitan reflexión y muestran "" para nulos.
        // El id no se muestra como columna (ruido de BD); sigue en el modelo.
        nombreColumn.setCellValueFactory(cell -> text(cell.getValue().getNombre()));
        emailColumn.setCellValueFactory(cell -> text(cell.getValue().getEmail()));
        telefonoColumn.setCellValueFactory(cell -> text(cell.getValue().getTelefono()));

        clientesTable.setPlaceholder(UiFactory.tablePlaceholder(
                "M22 21a7 7 0 100-14 7 7 0 000 14z M8 38c0-8 6-11 14-11s14 3 14 11",
                "No hay pacientes que mostrar",
                "Los pacientes de la clínica aparecerán aquí."));

        // Columna de acciones por fila: Editar / Eliminar.
        accionesColumn.setCellFactory(col -> new AccionesCell());

        cargarClientes();
    }

    @FXML
    private void onRefresh() {
        cargarClientes();
    }

    // ------------------ Altas, ediciones y bajas ------------------

    /** Abre el formulario de alta; si se confirma, crea el paciente en la API. */
    @FXML
    private void onNuevo() {
        Optional<PacienteDialog.Datos> datos = PacienteDialog.abrir(ventana(), null);
        if (datos.isEmpty()) {
            return;
        }
        PacienteDialog.Datos d = datos.get();
        // La contraseña la genera el cliente (el personal no la teclea) y se
        // mostrará una sola vez tras el alta correcta.
        String password = PasswordGenerator.generar();

        Task<Cliente> task = new Task<>() {
            @Override
            protected Cliente call() throws Exception {
                return clienteService.crear(d.nombre(), d.email(), d.telefono(), password);
            }
        };
        task.setOnSucceeded(e -> {
            statusLabel.setText("Paciente creado: " + d.nombre());
            Dialogs.credencialesGeneradas(ventana(), d.email(), password);
            setBusy(false);
            cargarClientes();
        });
        task.setOnFailed(e -> mostrarError(task, "No se pudo crear el paciente."));
        lanzar(task, "crear-cliente");
    }

    /** Abre el formulario de edición precargado y, si se confirma, guarda los cambios. */
    private void editar(Cliente cliente) {
        Optional<PacienteDialog.Datos> datos = PacienteDialog.abrir(ventana(), cliente);
        if (datos.isEmpty()) {
            return;
        }
        PacienteDialog.Datos d = datos.get();
        Task<Cliente> task = new Task<>() {
            @Override
            protected Cliente call() throws Exception {
                return clienteService.editar(cliente.getId(), d.nombre(), d.email(), d.telefono());
            }
        };
        task.setOnSucceeded(e -> {
            statusLabel.setText("Paciente actualizado: " + d.nombre());
            setBusy(false);
            cargarClientes();
        });
        task.setOnFailed(e -> mostrarError(task, "No se pudo actualizar el paciente."));
        lanzar(task, "editar-cliente");
    }

    /** Pide confirmación (avisando de la cascada) y elimina el paciente. */
    private void eliminar(Cliente cliente) {
        boolean confirmado = Dialogs.confirmar(
                ventana(),
                "Eliminar paciente",
                "Vas a eliminar a «" + cliente.getNombre() + "». Se eliminarán también "
                + "TODAS sus citas (el borrado es en cascada). Esta acción no se puede deshacer.",
                "Eliminar");
        if (!confirmado) {
            return;
        }
        Task<Void> task = new Task<>() {
            @Override
            protected Void call() throws Exception {
                clienteService.eliminar(cliente.getId());
                return null;
            }
        };
        task.setOnSucceeded(e -> {
            statusLabel.setText("Paciente eliminado: " + cliente.getNombre());
            setBusy(false);
            cargarClientes();
        });
        task.setOnFailed(e -> mostrarError(task, "No se pudo eliminar el paciente."));
        lanzar(task, "eliminar-cliente");
    }

    // ------------------ Utilidades de escritura ------------------

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
        String mensaje = (error instanceof ClienteService.ClienteException)
                ? error.getMessage()
                : porDefecto;
        setBusy(false);
        Dialogs.error(ventana(), mensaje);
    }

    /** Ventana actual, para anclar los diálogos modales. */
    private Window ventana() {
        return clientesTable.getScene().getWindow();
    }

    /** Lanza la carga de pacientes en segundo plano y actualiza la tabla al terminar. */
    private void cargarClientes() {
        Task<List<Cliente>> task = new Task<>() {
            @Override
            protected List<Cliente> call() throws Exception {
                return clienteService.listar();
            }
        };

        task.setOnSucceeded(event -> {
            List<Cliente> clientes = task.getValue();
            clientesTable.setItems(FXCollections.observableArrayList(clientes));
            statusLabel.setText(clientes.size() + " paciente(s)");
            setBusy(false);
        });

        task.setOnFailed(event -> {
            Throwable error = task.getException();
            String message = (error instanceof ClienteService.ClienteException)
                    ? error.getMessage()
                    : "No se pudieron cargar los pacientes.";
            statusLabel.setText(message);
            setBusy(false);
        });

        setBusy(true);
        statusLabel.setText("Cargando...");
        Thread thread = new Thread(task, "clientes-task");
        thread.setDaemon(true);
        thread.start();
    }

    private void setBusy(boolean busy) {
        // Puede invocarse desde callbacks del Task, ya en el hilo de la UI.
        Runnable apply = () -> {
            refreshButton.setDisable(busy);
            nuevoButton.setDisable(busy);
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
     * Celda con los botones de acción de cada fila (Editar / Eliminar). Los
     * botones actúan sobre el paciente de esa fila; se ocultan en filas vacías.
     */
    private class AccionesCell extends TableCell<Cliente, Void> {

        private final Button editar = new Button("Editar");
        private final Button eliminar = new Button("Eliminar");
        private final HBox caja = new HBox(6, editar, eliminar);

        AccionesCell() {
            editar.getStyleClass().add("button-row");
            eliminar.getStyleClass().addAll("button-row", "button-row-danger");
            caja.setAlignment(Pos.CENTER_LEFT);
            editar.setOnAction(e -> editar(getFila()));
            eliminar.setOnAction(e -> eliminar(getFila()));
        }

        private Cliente getFila() {
            return getTableView().getItems().get(getIndex());
        }

        @Override
        protected void updateItem(Void item, boolean empty) {
            super.updateItem(item, empty);
            setGraphic(empty || getIndex() >= getTableView().getItems().size() ? null : caja);
        }
    }
}
