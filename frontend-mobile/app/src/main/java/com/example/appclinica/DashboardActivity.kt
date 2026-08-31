package com.example.appclinica

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.example.appclinica.databinding.ActivityDashboardBinding
import com.example.appclinica.data.remote.RetrofitClient
import kotlinx.coroutines.launch
import retrofit2.HttpException
import java.io.IOException

/**
 * Pantalla principal tras el login. Muestra la lista de citas del usuario.
 */
class DashboardActivity : ComponentActivity() {

    private lateinit var binding: ActivityDashboardBinding
    private lateinit var sessionManager: SessionManager
    private val citasAdapter = CitasAdapter()

    /** Nombre de pila del paciente, para saludarlo también en el asistente. */
    private var nombrePaciente: String = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityDashboardBinding.inflate(layoutInflater)
        setContentView(binding.root)

        sessionManager = SessionManager(this)

        // Inicializamos el RecyclerView.
        binding.recyclerViewCitas.layoutManager = LinearLayoutManager(this)
        binding.recyclerViewCitas.adapter = citasAdapter

        // FAB: abre el asistente virtual.
        binding.fabChat.setOnClickListener {
            startActivity(
                Intent(this, ChatActivity::class.java)
                    .putExtra(ChatActivity.EXTRA_NOMBRE, nombrePaciente)
            )
        }

        val token = sessionManager.fetchToken()
        if (token.isNullOrEmpty()) {
            Toast.makeText(this, "Sesión no válida, vuelve a iniciar sesión", Toast.LENGTH_LONG).show()
            return
        }

        cargarPerfil()
        cargarCitas()
    }

    /** Personaliza el saludo con el nombre real del cliente (GET /clientes/me). */
    private fun cargarPerfil() {
        lifecycleScope.launch {
            try {
                val perfil = RetrofitClient.apiService.getMiPerfil()
                val nombre = perfil.nombre.trim().split(" ").firstOrNull().orEmpty()
                nombrePaciente = nombre
                if (nombre.isNotEmpty()) {
                    binding.textViewSaludo.text = getString(R.string.dashboard_saludo_formato, nombre)
                }
            } catch (e: Exception) {
                // Si falla, dejamos el saludo genérico ("Hola 👋"); no es crítico.
            }
        }
    }

    private fun cargarCitas() {
        lifecycleScope.launch {
            try {
                // La pantalla anuncia "Tus próximas citas", así que pide
                // exactamente eso: de hoy en adelante. Las canceladas futuras
                // llegan y se pintan tachadas a propósito; el histórico
                // completo queda para la aplicación de la clínica.
                val citas = RetrofitClient.apiService.getMisCitas(proximas = true)
                citasAdapter.actualizarCitas(citas)
                binding.textViewEmpty.visibility = if (citas.isEmpty()) View.VISIBLE else View.GONE
            } catch (e: HttpException) {
                Toast.makeText(this@DashboardActivity, "Error del servidor (${e.code()})", Toast.LENGTH_LONG).show()
            } catch (e: IOException) {
                Toast.makeText(this@DashboardActivity, "Error de red: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }
}
