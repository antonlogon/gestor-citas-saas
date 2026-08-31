package org.example.frontenddesktop.utils;

import org.example.frontenddesktop.NexaCitaApp;
import org.example.frontenddesktop.models.Cliente;

import javafx.application.Platform;
import javafx.geometry.Insets;
import javafx.scene.control.ButtonBar;
import javafx.scene.control.ButtonType;
import javafx.scene.control.Dialog;
import javafx.scene.control.DialogPane;
import javafx.scene.control.Label;
import javafx.scene.control.TextField;
import javafx.scene.layout.VBox;
import javafx.scene.Node;
import javafx.stage.Window;

import java.util.Optional;

/**
 * Formulario modal para dar de alta o editar un paciente. Recoge nombre, email
 * y teléfono (lo único que admite {@code ClienteUpdate} del backend). NO incluye
 * campo de contraseña: en el alta se genera una provisional en el cliente y se
 * muestra después con {@link Dialogs#credencialesGeneradas}.
 *
 * <p>Construido en Java a propósito (ver la nota de {@link Dialogs}): así el
 * compilador valida el cableado del formulario.
 */
public final class PacienteDialog {

    /** Datos introducidos en el formulario (sin id: el id lo aporta el llamante). */
    public record Datos(String nombre, String email, String telefono) {
    }

    private PacienteDialog() {
        // Clase de utilidad estática.
    }

    /**
     * Abre el formulario y devuelve los datos introducidos, o vacío si el
     * usuario cancela.
     *
     * @param owner     ventana propietaria
     * @param existente cliente a editar, o {@code null} para un alta nueva
     * @return los datos validados, o {@link Optional#empty()} si se cancela
     */
    public static Optional<Datos> abrir(Window owner, Cliente existente) {
        boolean edicion = existente != null;

        Dialog<Datos> dialogo = new Dialog<>();
        dialogo.initOwner(owner);
        dialogo.setTitle(edicion ? "Editar paciente" : "Nuevo paciente");

        DialogPane pane = dialogo.getDialogPane();
        pane.getStylesheets().addAll(
                NexaCitaApp.class.getResource("styles/theme.css").toExternalForm(),
                NexaCitaApp.class.getResource("styles/dashboard.css").toExternalForm());
        pane.getStyleClass().add("app-dialog");

        ButtonType guardar = new ButtonType(
                edicion ? "Guardar" : "Crear", ButtonBar.ButtonData.OK_DONE);
        pane.getButtonTypes().addAll(ButtonType.CANCEL, guardar);

        TextField nombre = campo("Nombre y apellidos");
        TextField email = campo("email@ejemplo.com");
        TextField telefono = campo("Teléfono");
        if (edicion) {
            nombre.setText(existente.getNombre());
            email.setText(existente.getEmail());
            telefono.setText(existente.getTelefono());
        }

        VBox form = new VBox(10,
                etiqueta("Nombre"), nombre,
                etiqueta("Email"), email,
                etiqueta("Teléfono"), telefono);
        form.setPadding(new Insets(4));
        form.getStyleClass().add("form-grid");
        pane.setContent(form);

        // Validación local mínima: los tres campos son obligatorios. El formato
        // del email lo valida el backend (422), que se mostrará tal cual.
        Node botonGuardar = pane.lookupButton(guardar);
        Runnable validar = () -> botonGuardar.setDisable(
                enBlanco(nombre) || enBlanco(email) || enBlanco(telefono));
        nombre.textProperty().addListener((o, a, b) -> validar.run());
        email.textProperty().addListener((o, a, b) -> validar.run());
        telefono.textProperty().addListener((o, a, b) -> validar.run());
        validar.run();

        dialogo.setResultConverter(boton -> boton == guardar
                ? new Datos(nombre.getText().trim(), email.getText().trim(), telefono.getText().trim())
                : null);

        Platform.runLater(nombre::requestFocus);
        return dialogo.showAndWait();
    }

    private static TextField campo(String prompt) {
        TextField campo = new TextField();
        campo.setPromptText(prompt);
        campo.getStyleClass().add("form-field");
        return campo;
    }

    private static Label etiqueta(String texto) {
        Label label = new Label(texto);
        label.getStyleClass().add("form-label");
        return label;
    }

    private static boolean enBlanco(TextField campo) {
        return campo.getText() == null || campo.getText().trim().isEmpty();
    }
}
