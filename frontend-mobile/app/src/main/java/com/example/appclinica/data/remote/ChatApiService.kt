package com.example.appclinica.data.remote

import com.example.appclinica.data.model.ChatRequest
import com.example.appclinica.data.model.ChatResponse
import retrofit2.http.Body
import retrofit2.http.POST

/**
 * Contrato del asistente virtual (FastAPI).
 *
 * El token JWT NO se pasa como parámetro aquí: lo inyecta de forma centralizada
 * el [AuthInterceptor] en cada petición, evitando repetir la cabecera en cada call.
 */
interface ChatApiService {

    @POST("chatbot/chat")
    suspend fun enviarMensaje(
        @Body request: ChatRequest
    ): ChatResponse
}
