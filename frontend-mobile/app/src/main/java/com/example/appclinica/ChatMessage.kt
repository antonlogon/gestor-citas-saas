package com.example.appclinica

/**
 * Modelo de UI para un mensaje del chat.
 *
 * Se mantiene separado de los DTOs de red (ChatRequest/ChatResponse): aquí solo
 * interesa qué texto mostrar y de qué lado pintar la burbuja (`isUser`).
 */
data class ChatMessage(
    val text: String,
    val isUser: Boolean,
    /**
     * Marca el saludo inicial que pinta la propia aplicación.
     *
     * Importa porque el historial que se envía al modelo se construye a partir de
     * los mensajes visibles: sin esta distinción, la bienvenida viajaría como un
     * turno del asistente en cada petición, ocupando contexto sin aportar nada.
     * Es una ayuda de interfaz, no parte de la conversación.
     */
    val esBienvenida: Boolean = false
)
