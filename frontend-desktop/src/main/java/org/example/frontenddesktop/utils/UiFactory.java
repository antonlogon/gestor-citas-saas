package org.example.frontenddesktop.utils;

import javafx.geometry.Pos;
import javafx.scene.control.Label;
import javafx.scene.layout.VBox;
import javafx.scene.shape.SVGPath;

/**
 * Fábrica de nodos de interfaz reutilizables, para que las distintas vistas
 * (Citas, Pacientes, Servicios) compartan exactamente el mismo aspecto y no
 * parezcan aplicaciones diferentes. Las clases CSS las define dashboard.css.
 */
public final class UiFactory {

    private UiFactory() {
        // Clase de utilidad estática.
    }

    /**
     * Construye el placeholder de una tabla vacía: icono + título + detalle,
     * centrado. Se usa con {@code tableView.setPlaceholder(...)} en lugar de un
     * texto pelado.
     *
     * @param svgContent contenido (path) del icono SVG, a tamaño final (~44px);
     *                   sin transformaciones de escala
     * @param titulo     mensaje principal (p. ej. "No hay pacientes que mostrar")
     * @param detalle    texto secundario explicativo
     * @return un VBox listo para usar como placeholder
     */
    public static VBox tablePlaceholder(String svgContent, String titulo, String detalle) {
        SVGPath icono = new SVGPath();
        icono.setContent(svgContent);
        icono.getStyleClass().add("placeholder-icon");

        Label lblTitulo = new Label(titulo);
        lblTitulo.getStyleClass().add("placeholder-title");

        Label lblDetalle = new Label(detalle);
        lblDetalle.getStyleClass().add("placeholder-detail");

        VBox box = new VBox(12, icono, lblTitulo, lblDetalle);
        box.setAlignment(Pos.CENTER);
        box.getStyleClass().add("placeholder-box");
        return box;
    }
}
