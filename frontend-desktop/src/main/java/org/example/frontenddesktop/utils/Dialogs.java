package org.example.frontenddesktop.utils;

import org.example.frontenddesktop.NexaCitaApp;

import javafx.application.Platform;
import javafx.geometry.Insets;
import javafx.scene.control.Alert;
import javafx.scene.control.Alert.AlertType;
import javafx.scene.control.ButtonBar;
import javafx.scene.control.ButtonType;
import javafx.scene.control.Dialog;
import javafx.scene.control.DialogPane;
import javafx.scene.control.Label;
import javafx.scene.control.TextField;
import javafx.scene.input.Clipboard;
import javafx.scene.input.ClipboardContent;
import javafx.scene.layout.VBox;
import javafx.stage.Window;

import java.util.Optional;

/**
 * Diálogos modales reutilizables (errores, confirmaciones, información y el
 * aviso de credenciales generadas).
 *
 * <p><b>DECISIÓN DELIBERADA — diálogos en Java, no en FXML.</b> El resto de
 * vistas de la aplicación son FXML, pero estos diálogos se construyen por
 * código a propósito: {@code mvn compile} valida el cableado (referencias a
 * nodos, tipos y handlers) en tiempo de compilación, mientras que un FXML con
 * {@code fx:id}/{@code fx:controller}/{@code onAction} solo revela sus errores
 * al arrancar la aplicación. Para formularios pequeños y muy usados, el coste de
 * un fallo en runtime no compensa; se prefiere la verificación del compilador.
 * A cada {@link DialogPane} se le aplican theme.css + dashboard.css para heredar
 * los tokens del sistema de diseño y parecerse a las vistas.
 */
public final class Dialogs {

    private Dialogs() {
        // Clase de utilidad estática.
    }

    /** Muestra un error de negocio (mensaje ya legible, extraído de la API). */
    public static void error(Window owner, String mensaje) {
        Alert alerta = new Alert(AlertType.ERROR);
        alerta.initOwner(owner);
        alerta.setTitle("No se pudo completar la acción");
        alerta.setHeaderText(null);
        alerta.setContentText(mensaje);
        estilar(alerta.getDialogPane());
        alerta.showAndWait();
    }

    /** Muestra un aviso informativo (p. ej. una acción completada). */
    public static void info(Window owner, String titulo, String mensaje) {
        Alert alerta = new Alert(AlertType.INFORMATION);
        alerta.initOwner(owner);
        alerta.setTitle(titulo);
        alerta.setHeaderText(null);
        alerta.setContentText(mensaje);
        estilar(alerta.getDialogPane());
        alerta.showAndWait();
    }

    /**
     * Pide confirmación al usuario. Devuelve {@code true} solo si pulsa el botón
     * de confirmar (Aceptar), no al cancelar ni cerrar.
     */
    public static boolean confirmar(Window owner, String titulo, String mensaje, String textoAceptar) {
        Alert alerta = new Alert(AlertType.CONFIRMATION);
        alerta.initOwner(owner);
        alerta.setTitle(titulo);
        alerta.setHeaderText(null);
        alerta.setContentText(mensaje);

        ButtonType aceptar = new ButtonType(textoAceptar, ButtonBar.ButtonData.OK_DONE);
        ButtonType cancelar = new ButtonType("Cancelar", ButtonBar.ButtonData.CANCEL_CLOSE);
        alerta.getButtonTypes().setAll(cancelar, aceptar);
        estilar(alerta.getDialogPane());

        Optional<ButtonType> resultado = alerta.showAndWait();
        return resultado.isPresent() && resultado.get() == aceptar;
    }

    /**
     * Muestra, UNA SOLA VEZ, las credenciales provisionales de un paciente
     * recién creado, con opción de copiar la contraseña al portapapeles. Deja
     * claro que es provisional y —limitación conocida— que el paciente todavía
     * no puede cambiarla (el backend no expone aún esa operación).
     *
     * @param owner    ventana propietaria del diálogo
     * @param email    email del paciente (su usuario de acceso)
     * @param password contraseña generada
     */
    public static void credencialesGeneradas(Window owner, String email, String password) {
        Dialog<Void> dialogo = new Dialog<>();
        dialogo.initOwner(owner);
        dialogo.setTitle("Paciente creado");

        DialogPane pane = dialogo.getDialogPane();
        estilar(pane);
        pane.getButtonTypes().add(ButtonType.CLOSE);

        Label intro = new Label(
                "Entrega estas credenciales al paciente para que acceda a la app móvil. "
                + "La contraseña es PROVISIONAL y solo se muestra ahora.");
        intro.setWrapText(true);
        intro.getStyleClass().add("dialog-intro");

        TextField emailField = campoSoloLectura(email);
        TextField passwordField = campoSoloLectura(password);

        javafx.scene.control.Button copiar = new javafx.scene.control.Button("Copiar contraseña");
        copiar.getStyleClass().add("button-secondary");
        copiar.setOnAction(e -> {
            ClipboardContent contenido = new ClipboardContent();
            contenido.putString(password);
            Clipboard.getSystemClipboard().setContent(contenido);
            copiar.setText("Copiada ✓");
        });

        Label nota = new Label(
                "Nota: el paciente aún no puede cambiar su contraseña desde la app "
                + "(el backend no expone todavía esa operación).");
        nota.setWrapText(true);
        nota.getStyleClass().add("dialog-nota");

        VBox contenido = new VBox(10,
                intro,
                etiqueta("Email"), emailField,
                etiqueta("Contraseña provisional"), passwordField,
                copiar, nota);
        contenido.setPadding(new Insets(4, 4, 4, 4));
        contenido.getStyleClass().add("form-grid");
        pane.setContent(contenido);

        dialogo.showAndWait();
    }

    // ------------------ Utilidades internas ------------------

    /** Aplica los tokens del sistema de diseño (theme.css + dashboard.css) al diálogo. */
    private static void estilar(DialogPane pane) {
        pane.getStylesheets().addAll(
                NexaCitaApp.class.getResource("styles/theme.css").toExternalForm(),
                NexaCitaApp.class.getResource("styles/dashboard.css").toExternalForm());
        pane.getStyleClass().add("app-dialog");
    }

    /** Campo de texto de solo lectura, seleccionable para copiar a mano. */
    private static TextField campoSoloLectura(String valor) {
        TextField campo = new TextField(valor);
        campo.setEditable(false);
        campo.getStyleClass().add("form-field");
        // Al enfocar, selecciona todo para facilitar copiar con el teclado.
        campo.focusedProperty().addListener((obs, antes, ahora) -> {
            if (ahora) {
                Platform.runLater(campo::selectAll);
            }
        });
        return campo;
    }

    private static Label etiqueta(String texto) {
        Label label = new Label(texto);
        label.getStyleClass().add("form-label");
        return label;
    }
}
