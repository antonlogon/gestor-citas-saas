package org.example.frontenddesktop;

import javafx.application.Application;
import javafx.fxml.FXMLLoader;
import javafx.scene.Scene;
import javafx.stage.Stage;

import java.io.IOException;

public class NexaCitaApp extends Application {
    @Override
    public void start(Stage stage) throws IOException {
        FXMLLoader fxmlLoader = new FXMLLoader(NexaCitaApp.class.getResource("views/login-view.fxml"));
        Scene scene = new Scene(fxmlLoader.load(), 900, 560);
        // theme.css (tokens de diseño) SIEMPRE antes que la hoja específica.
        scene.getStylesheets().addAll(
                NexaCitaApp.class.getResource("styles/theme.css").toExternalForm(),
                NexaCitaApp.class.getResource("styles/login.css").toExternalForm());
        stage.setTitle("NexaCita · Iniciar Sesión");
        stage.setScene(scene);
        stage.centerOnScreen();
        stage.show();
    }
}
