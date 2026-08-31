package com.example.appclinica

import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.example.appclinica.data.model.ChatRequest
import com.example.appclinica.data.model.MensajeHistorial
import com.example.appclinica.data.remote.RetrofitClient
import com.example.appclinica.databinding.ActivityChatBinding
import kotlinx.coroutines.launch
import retrofit2.HttpException
import java.io.IOException

/**
 * Pantalla del asistente virtual. Envía el texto del usuario a `POST /chatbot/chat`
 * y muestra la respuesta del LLM local en forma de burbujas.
 *
 * El token JWT lo inyecta automáticamente el AuthInterceptor configurado en
 * [RetrofitClient] (ver AppClinicaApp), así que aquí no se gestiona.
 */
class ChatActivity : ComponentActivity() {

    private lateinit var binding: ActivityChatBinding
    private val chatAdapter = ChatAdapter()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityChatBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.recyclerChat.layoutManager = LinearLayoutManager(this)
        binding.recyclerChat.adapter = chatAdapter

        binding.buttonEnviar.setOnClickListener { enviarMensaje() }
        configurarSugerencias()

        mostrarBienvenida(savedInstanceState)
    }

    /**
     * Pinta el saludo inicial, sin llamar al modelo.
     *
     * Se hace en local a propósito: el modelo tarda segundos en responder y un
     * saludo que aparece tarde es peor que no tenerlo, además de gastar tokens en
     * cada apertura y de poder equivocarse. El nombre llega del panel, que ya lo
     * ha consultado, de modo que no hace falta ninguna petición de red.
     *
     * Solo se muestra al crear la pantalla por primera vez: al girar el
     * dispositivo el adaptador conserva la conversación y repetir el saludo la
     * ensuciaría.
     */
    private fun mostrarBienvenida(savedInstanceState: Bundle?) {
        if (savedInstanceState != null || chatAdapter.currentMessages().isNotEmpty()) {
            // Conversación ya empezada: ni saludo ni sugerencias.
            binding.scrollSugerencias.visibility = View.GONE
            return
        }
        val nombre = intent.getStringExtra(EXTRA_NOMBRE).orEmpty()
        val texto = if (nombre.isBlank()) getString(R.string.chat_bienvenida_sin_nombre)
                    else getString(R.string.chat_bienvenida, nombre)
        agregarMensaje(ChatMessage(text = texto, isUser = false, esBienvenida = true))
    }

    /**
     * Deja las sugerencias listas para enviarse de un toque.
     *
     * El texto del chip ES el mensaje que se envía: así el paciente no tiene que
     * adivinar cómo formular la petición, que es la principal fuente de peticiones
     * mal entendidas. Se ocultan en cuanto escribe el primer mensaje, porque a
     * partir de ahí ocupan espacio de conversación sin aportar nada.
     */
    private fun configurarSugerencias() {
        listOf(binding.chipCitas, binding.chipPedir, binding.chipCancelar)
            .forEach { chip -> chip.setOnClickListener { enviarTexto(chip.text.toString()) } }
    }

    /** Pinta el mensaje del usuario, limpia el campo y pide la respuesta a la IA. */
    private fun enviarMensaje() {
        enviarTexto(binding.editMensaje.text.toString())
    }

    /** Envía [texto] como mensaje del paciente, venga del campo o de un chip. */
    private fun enviarTexto(bruto: String) {
        val texto = bruto.trim()
        if (texto.isEmpty()) return

        // Las sugerencias solo tienen sentido con la conversación en blanco.
        binding.scrollSugerencias.visibility = View.GONE

        // 1. Eco inmediato del mensaje del usuario y limpieza del EditText.
        agregarMensaje(ChatMessage(text = texto, isUser = true))
        binding.editMensaje.text?.clear()

        // 2. Mapeamos el estado de UI (ChatMessage) al DTO de red que exige el
        //    backend. La lista ya incluye el mensaje recién añadido, por lo que
        //    el historial viaja completo (con memoria de contexto para la IA).
        val historial = chatAdapter.currentMessages()
            .filterNot { it.esBienvenida }
            .map { mensaje ->
                MensajeHistorial(
                    role = if (mensaje.isUser) "user" else "assistant",
                    content = mensaje.text
                )
            }

        // 3. Indicador "escribiendo…" y llamada asíncrona al backend.
        binding.buttonEnviar.isEnabled = false
        chatAdapter.showTyping()
        binding.recyclerChat.scrollToPosition(chatAdapter.lastPosition())

        lifecycleScope.launch {
            try {
                val respuesta = RetrofitClient.chatApiService.enviarMensaje(
                    ChatRequest(historial = historial)
                )
                chatAdapter.hideTyping()
                agregarMensaje(ChatMessage(text = respuesta.respuesta, isUser = false))
            } catch (e: HttpException) {
                // 401 (token inválido) o 503 (LLM local caído), entre otros.
                chatAdapter.hideTyping()
                Toast.makeText(
                    this@ChatActivity,
                    "El asistente no está disponible (${e.code()})",
                    Toast.LENGTH_LONG
                ).show()
            } catch (e: IOException) {
                chatAdapter.hideTyping()
                Toast.makeText(
                    this@ChatActivity,
                    "Error de red: revisa tu conexión",
                    Toast.LENGTH_LONG
                ).show()
            } finally {
                binding.buttonEnviar.isEnabled = true
            }
        }
    }

    companion object {
        /** Nombre de pila del paciente, para personalizar el saludo. */
        const val EXTRA_NOMBRE = "nombre_paciente"
    }

    /** Añade el mensaje a la lista y desplaza el RecyclerView hasta el final. */
    private fun agregarMensaje(mensaje: ChatMessage) {
        chatAdapter.addMessage(mensaje)
        binding.recyclerChat.scrollToPosition(chatAdapter.lastPosition())
    }
}
