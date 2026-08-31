package com.example.appclinica

import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.util.Log
import android.view.Gravity
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.lifecycle.lifecycleScope
import com.example.appclinica.databinding.ActivityLoginBinding
import com.example.appclinica.data.remote.RetrofitClient
import kotlinx.coroutines.launch
import retrofit2.HttpException
import java.io.IOException

class LoginActivity : ComponentActivity() {

    private lateinit var binding: ActivityLoginBinding
    private lateinit var sessionManager: SessionManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityLoginBinding.inflate(layoutInflater)
        setContentView(binding.root)

        sessionManager = SessionManager(this)

        binding.buttonLogin.setOnClickListener { realizarLogin() }
    }

    private fun realizarLogin() {
        val email = binding.editTextEmail.text.toString().trim()
        val password = binding.editTextPassword.text.toString()

        if (email.isEmpty() || password.isEmpty()) {
            mostrarToast("Introduce email y contraseña", exito = false)
            return
        }

        // Evitamos pulsaciones repetidas mientras la petición está en curso.
        binding.buttonLogin.isEnabled = false

        lifecycleScope.launch {
            try {
                val respuesta = RetrofitClient.apiService.login(email, password)
                Log.d("Login", "Token recibido: ${respuesta.accessToken}")

                // 1) Persistimos el token para futuras peticiones autenticadas.
                sessionManager.saveToken(respuesta.accessToken)
                mostrarToast("¡Login correcto!", exito = true)

                // 2) Saltamos al Dashboard y cerramos el Login: con finish() el
                //    botón "Atrás" no devolverá al usuario a esta pantalla.
                startActivity(Intent(this@LoginActivity, DashboardActivity::class.java))
                finish()
            } catch (e: HttpException) {
                // Respuesta del servidor con código de error (p. ej. 401 credenciales inválidas).
                mostrarToast("Credenciales incorrectas (${e.code()})", exito = false)
                binding.buttonLogin.isEnabled = true
            } catch (e: IOException) {
                // Fallo de red: servidor caído, sin conexión, timeout...
                mostrarToast("Error de red: ${e.message}", exito = false)
                binding.buttonLogin.isEnabled = true
            }
        }
    }

    /**
     * Muestra un Toast con fondo verde (éxito) o rojo (error).
     * Se personaliza la vista del Toast para reflejar visualmente el resultado.
     */
    private fun mostrarToast(mensaje: String, exito: Boolean) {
        val color = if (exito) Color.parseColor("#4CAF50") else Color.parseColor("#F44336")

        val texto = TextView(this).apply {
            text = mensaje
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
            setPadding(48, 32, 48, 32)
            setBackgroundColor(color)
        }

        Toast(this).apply {
            duration = Toast.LENGTH_LONG
            @Suppress("DEPRECATION")
            view = texto
            show()
        }
    }
}
