package org.example.frontenddesktop.controllers;

import org.example.frontenddesktop.NexaCitaApp;
import org.example.frontenddesktop.services.AuthService;
import org.example.frontenddesktop.utils.SessionManager;

import javafx.concurrent.Task;
import javafx.fxml.FXML;
import javafx.fxml.FXMLLoader;
import javafx.scene.Scene;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.control.PasswordField;
import javafx.scene.control.TextField;
import javafx.scene.control.skin.TextFieldSkin;
import javafx.stage.Stage;

import java.io.IOException;

/**
 * Controlador de la pantalla de login. Valida la entrada, invoca a {@link AuthService}
 * en un hilo de fondo y actualiza la interfaz con el resultado.
 */
public class LoginController {

    @FXML
    private TextField usernameField;

    @FXML
    private PasswordField passwordField;

    @FXML
    private Button loginButton;

    @FXML
    private Label messageLabel;

    private final AuthService authService = new AuthService();

    /**
     * JavaFX enmascara la contraseña con U+25CF (●, «black circle»), un glifo
     * bastante mayor que las letras del campo de usuario, lo que rompe la
     * uniformidad visual del formulario. Sustituimos la máscara por U+2022
     * (•, «bullet»), que es el mismo carácter del promptText y cuyo tamaño
     * concuerda con el del texto normal.
     *
     * <p>Nota: JavaFX no expone {@code PasswordFieldSkin}; desde JavaFX 9 el
     * enmascarado vive en {@link TextFieldSkin#maskText(String)}, así que es esa
     * la clase de la que hay que derivar.
     */
    @FXML
    private void initialize() {
        passwordField.setSkin(new TextFieldSkin(passwordField) {
            @Override
            protected String maskText(String texto) {
                return "\u2022".repeat(texto == null ? 0 : texto.length());
            }
        });
    }


    @FXML
    protected void onLogin() {
        String username = usernameField.getText() == null ? "" : usernameField.getText().trim();
        String password = passwordField.getText() == null ? "" : passwordField.getText();

        // Validación local: campos obligatorios.
        if (username.isEmpty() || password.isEmpty()) {
            showError("Por favor, introduce usuario y contraseña.");
            return;
        }

        // La llamada HTTP es bloqueante: la ejecutamos fuera del hilo de la UI.
        Task<String> loginTask = new Task<>() {
            @Override
            protected String call() throws Exception {
                return authService.login(username, password);
            }
        };

        loginTask.setOnSucceeded(event -> {
            String token = loginTask.getValue();
            // Guardamos el token y los datos del usuario en la sesión global.
            SessionManager.start(token, username);
            showSuccess("¡Login correcto! Sesión iniciada.");
            try {
                openDashboard();
            } catch (IOException e) {
                showError("No se pudo abrir el panel principal.");
                setFormDisabled(false);
            }
        });

        loginTask.setOnFailed(event -> {
            Throwable error = loginTask.getException();
            String message = (error instanceof AuthService.AuthException)
                    ? error.getMessage()
                    : "Ocurrió un error inesperado.";
            showError(message);
            setFormDisabled(false);
        });

        // Feedback inmediato mientras se procesa la petición.
        setFormDisabled(true);
        showInfo("Conectando...");
        Thread thread = new Thread(loginTask, "login-task");
        thread.setDaemon(true);
        thread.start();
    }

    /**
     * Sustituye la escena de login por el dashboard principal reutilizando el
     * mismo Stage (la ventana de login deja de mostrarse).
     */
    private void openDashboard() throws IOException {
        FXMLLoader fxmlLoader = new FXMLLoader(NexaCitaApp.class.getResource("views/dashboard-view.fxml"));
        Scene scene = new Scene(fxmlLoader.load(), 1200, 760);
        // theme.css (tokens de diseño) SIEMPRE antes que la hoja específica.
        scene.getStylesheets().addAll(
                NexaCitaApp.class.getResource("styles/theme.css").toExternalForm(),
                NexaCitaApp.class.getResource("styles/dashboard.css").toExternalForm());

        Stage stage = (Stage) loginButton.getScene().getWindow();
        stage.setTitle("NexaCita · Panel Principal");
        stage.setScene(scene);
        // Tamaño mínimo para que KPIs, toolbar y tabla no se rompan al encoger.
        stage.setMinWidth(1024);
        stage.setMinHeight(640);
        stage.centerOnScreen();
    }

    private void setFormDisabled(boolean disabled) {
        loginButton.setDisable(disabled);
        usernameField.setDisable(disabled);
        passwordField.setDisable(disabled);
    }

    private void showError(String message) {
        messageLabel.getStyleClass().remove("success");
        messageLabel.setText(message);
    }

    private void showInfo(String message) {
        messageLabel.getStyleClass().remove("success");
        messageLabel.setText(message);
    }

    private void showSuccess(String message) {
        if (!messageLabel.getStyleClass().contains("success")) {
            messageLabel.getStyleClass().add("success");
        }
        messageLabel.setText(message);
    }
}
