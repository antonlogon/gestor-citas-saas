package org.example.frontenddesktop.controllers;

import org.example.frontenddesktop.models.Servicio;
import org.example.frontenddesktop.services.ServicioService;
import org.example.frontenddesktop.utils.UiFactory;

import javafx.application.Platform;
import javafx.beans.property.ReadOnlyStringWrapper;
import javafx.collections.FXCollections;
import javafx.concurrent.Task;
import javafx.fxml.FXML;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.control.TableColumn;
import javafx.scene.control.TableView;

import java.util.List;

/**
 * Controlador de la sección de Servicios. Configura la tabla y carga los
 * servicios reales desde la API mediante {@link ServicioService} en un hilo de
 * fondo (Task), tanto al inicializar la vista como al pulsar "Refrescar".
 */
public class ServiciosController {

    @FXML
    private TableView<Servicio> serviciosTable;

    @FXML
    private TableColumn<Servicio, String> nombreColumn;

    @FXML
    private TableColumn<Servicio, String> duracionColumn;

    @FXML
    private TableColumn<Servicio, String> precioColumn;

    @FXML
    private Button refreshButton;

    @FXML
    private Label statusLabel;

    private final ServicioService servicioService = new ServicioService();

    @FXML
    private void initialize() {
        // Value factories con lambdas: evitan reflexión y muestran "" para nulos.
        // El id no se muestra como columna (ruido de BD); sigue en el modelo.
        nombreColumn.setCellValueFactory(cell -> text(cell.getValue().getNombre()));
        duracionColumn.setCellValueFactory(cell -> text(cell.getValue().getDuracionMinutos()));
        precioColumn.setCellValueFactory(cell -> new ReadOnlyStringWrapper(formatearPrecio(cell.getValue().getPrecio())));

        serviciosTable.setPlaceholder(UiFactory.tablePlaceholder(
                "M10 10H34V40H10Z M16 6H28V12H16Z M16 22H28 M16 30H26",
                "No hay servicios que mostrar",
                "El catálogo de servicios de la clínica aparecerá aquí."));

        cargarServicios();
    }

    @FXML
    private void onRefresh() {
        cargarServicios();
    }

    /** Lanza la carga de servicios en segundo plano y actualiza la tabla al terminar. */
    private void cargarServicios() {
        Task<List<Servicio>> task = new Task<>() {
            @Override
            protected List<Servicio> call() throws Exception {
                return servicioService.listar();
            }
        };

        task.setOnSucceeded(event -> {
            List<Servicio> servicios = task.getValue();
            serviciosTable.setItems(FXCollections.observableArrayList(servicios));
            statusLabel.setText(servicios.size() + " servicio(s)");
            setBusy(false);
        });

        task.setOnFailed(event -> {
            Throwable error = task.getException();
            String message = (error instanceof ServicioService.ServicioException)
                    ? error.getMessage()
                    : "No se pudieron cargar los servicios.";
            statusLabel.setText(message);
            setBusy(false);
        });

        setBusy(true);
        statusLabel.setText("Cargando...");
        Thread thread = new Thread(task, "servicios-task");
        thread.setDaemon(true);
        thread.start();
    }

    private void setBusy(boolean busy) {
        // Puede invocarse desde callbacks del Task, ya en el hilo de la UI.
        if (Platform.isFxApplicationThread()) {
            refreshButton.setDisable(busy);
        } else {
            Platform.runLater(() -> refreshButton.setDisable(busy));
        }
    }

    /** Muestra el precio con dos decimales y símbolo de euro; si no es numérico, lo deja tal cual. */
    private static String formatearPrecio(String precio) {
        if (precio == null || precio.isBlank()) {
            return "";
        }
        try {
            return String.format("%.2f €", Double.parseDouble(precio.trim()));
        } catch (NumberFormatException e) {
            return precio;
        }
    }

    /** Envuelve un valor en una propiedad de texto, mostrando "" si es nulo. */
    private static ReadOnlyStringWrapper text(Object value) {
        return new ReadOnlyStringWrapper(value == null ? "" : value.toString());
    }
}
