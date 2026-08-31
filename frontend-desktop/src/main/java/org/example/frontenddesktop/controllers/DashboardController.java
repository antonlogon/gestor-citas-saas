package org.example.frontenddesktop.controllers;

import org.example.frontenddesktop.NexaCitaApp;
import org.example.frontenddesktop.utils.SessionManager;

import javafx.fxml.FXML;
import javafx.fxml.FXMLLoader;
import javafx.scene.Parent;
import javafx.scene.Scene;
import javafx.scene.control.Label;
import javafx.scene.control.ToggleButton;
import javafx.scene.control.ToggleGroup;
import javafx.scene.layout.StackPane;
import javafx.stage.Stage;

import java.io.IOException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

/**
 * Controlador del dashboard principal. Muestra los datos del usuario en sesión
 * (avatar con iniciales, email y rol), gestiona la navegación entre secciones
 * (Citas, Pacientes, Servicios) mediante un {@link ToggleGroup} con estado
 * activo visible, y el cierre de sesión (que devuelve a la pantalla de login).
 */
public class DashboardController {

    private static final Locale LOCALE_ES = Locale.forLanguageTag("es-ES");

    // Subtítulo de cabecera: fecha de hoy legible, p. ej. "lunes, 24 de agosto de 2026".
    private static final DateTimeFormatter FECHA_HOY =
            DateTimeFormatter.ofPattern("EEEE, d 'de' MMMM 'de' yyyy", LOCALE_ES);

    @FXML
    private Label avatarLabel;

    @FXML
    private Label userLabel;

    @FXML
    private Label roleLabel;

    @FXML
    private Label sectionTitle;

    @FXML
    private Label sectionSubtitle;

    @FXML
    private ToggleGroup navGroup;

    @FXML
    private ToggleButton navCitas;

    @FXML
    private StackPane contentArea;

    @FXML
    private void initialize() {
        // Datos del usuario en sesión.
        String email = SessionManager.getEmail() != null ? SessionManager.getEmail() : "usuario";
        userLabel.setText(email);
        avatarLabel.setText(iniciales(email));
        roleLabel.setText(rolLegible(SessionManager.getTipo()));

        // El ToggleGroup no debe quedarse sin selección: si el usuario pulsa el
        // botón ya activo (que lo deseleccionaría), lo volvemos a seleccionar.
        navGroup.selectedToggleProperty().addListener((obs, anterior, actual) -> {
            if (actual == null && anterior != null) {
                anterior.setSelected(true);
            }
        });

        // Sección inicial por defecto: Citas (marca el botón como activo).
        navCitas.setSelected(true);
        showCitas();
    }

    @FXML
    private void showCitas() {
        mostrarSeccion("Citas", "Agenda de hoy · " + fechaDeHoy(), "views/citas-view.fxml",
                "No se pudo cargar la vista de Citas.");
    }

    @FXML
    private void showPacientes() {
        mostrarSeccion("Pacientes", "Directorio de pacientes de la clínica",
                "views/clientes-view.fxml", "No se pudo cargar la vista de Pacientes.");
    }

    @FXML
    private void showServicios() {
        mostrarSeccion("Servicios", "Catálogo de servicios ofertados",
                "views/servicios-view.fxml", "No se pudo cargar la vista de Servicios.");
    }

    /**
     * Actualiza la cabecera (título + subtítulo) y carga la vista indicada en la
     * zona de contenido. Cada vista tiene su propio controlador, que carga sus
     * datos reales.
     */
    private void mostrarSeccion(String titulo, String subtitulo, String fxml, String errorMsg) {
        sectionTitle.setText(titulo);
        sectionSubtitle.setText(subtitulo);
        try {
            Parent view = FXMLLoader.load(NexaCitaApp.class.getResource(fxml));
            contentArea.getChildren().setAll(view);
        } catch (IOException e) {
            contentArea.getChildren().setAll(new Label(errorMsg));
        }
    }

    @FXML
    private void onLogout() throws IOException {
        // Cerramos la sesión y volvemos a la pantalla de login.
        SessionManager.clear();

        FXMLLoader fxmlLoader = new FXMLLoader(NexaCitaApp.class.getResource("views/login-view.fxml"));
        Scene scene = new Scene(fxmlLoader.load(), 900, 560);
        // theme.css (tokens de diseño) SIEMPRE antes que la hoja específica.
        scene.getStylesheets().addAll(
                NexaCitaApp.class.getResource("styles/theme.css").toExternalForm(),
                NexaCitaApp.class.getResource("styles/login.css").toExternalForm());

        Stage stage = (Stage) userLabel.getScene().getWindow();
        stage.setTitle("NexaCita · Iniciar Sesión");
        stage.setScene(scene);
        // El dashboard fijó un tamaño mínimo mayor; lo liberamos para que el
        // login recupere su tamaño compacto (900x560) en lugar de quedar estirado.
        stage.setMinWidth(0);
        stage.setMinHeight(0);
        stage.sizeToScene();
        stage.centerOnScreen();
    }

    // ------------------ Utilidades de presentación ------------------

    /** Fecha de hoy formateada en español para el subtítulo de cabecera. */
    private static String fechaDeHoy() {
        return LocalDate.now().format(FECHA_HOY);
    }

    /**
     * Deriva las iniciales para el avatar a partir del email/usuario. Toma la
     * parte anterior a la "@" y usa la primera letra de sus dos primeros
     * segmentos (separados por ".", "_" o "-"); si no hay separador, las dos
     * primeras letras. Devuelve mayúsculas.
     */
    private static String iniciales(String email) {
        if (email == null || email.isBlank()) {
            return "?";
        }
        String local = email.split("@", 2)[0];
        String[] partes = local.split("[._-]+");
        StringBuilder sb = new StringBuilder();
        if (partes.length >= 2 && !partes[0].isEmpty() && !partes[1].isEmpty()) {
            sb.append(partes[0].charAt(0)).append(partes[1].charAt(0));
        } else {
            String limpio = local.replaceAll("[^A-Za-z0-9]", "");
            sb.append(limpio.isEmpty() ? "?" : limpio.substring(0, Math.min(2, limpio.length())));
        }
        return sb.toString().toUpperCase(LOCALE_ES);
    }

    /** Traduce el tipo de usuario del token a una etiqueta legible para el rol. */
    private static String rolLegible(String tipo) {
        if (tipo == null) {
            return "—";
        }
        return switch (tipo.toLowerCase()) {
            case "empleado" -> "Personal clínico";
            case "cliente" -> "Paciente";
            default -> tipo;
        };
    }
}
