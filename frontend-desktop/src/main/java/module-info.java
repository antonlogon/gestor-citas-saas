module org.example.frontenddesktop {
    requires javafx.controls;
    requires javafx.fxml;
    requires javafx.base;
    requires java.net.http;

    // Raíz: NexaCitaApp (Application) la instancia javafx.graphics por reflexión.
    opens org.example.frontenddesktop to javafx.fxml;
    exports org.example.frontenddesktop;

    // Controladores: FXMLLoader inyecta los campos @FXML por reflexión -> opens.
    opens org.example.frontenddesktop.controllers to javafx.fxml;
    exports org.example.frontenddesktop.controllers;

    exports org.example.frontenddesktop.models;
    exports org.example.frontenddesktop.services;
    exports org.example.frontenddesktop.utils;
}