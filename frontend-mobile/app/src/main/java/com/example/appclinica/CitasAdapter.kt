package com.example.appclinica

import android.content.res.ColorStateList
import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.RecyclerView
import com.example.appclinica.R
import com.example.appclinica.databinding.ItemCitaBinding
import com.example.appclinica.data.model.Cita
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * Enlaza la lista de [Cita] con el layout item_cita.xml.
 */
class CitasAdapter(
    private var citas: List<Cita> = emptyList()
) : RecyclerView.Adapter<CitasAdapter.CitaViewHolder>() {

    /** Reemplaza los datos y refresca la lista. */
    fun actualizarCitas(nuevasCitas: List<Cita>) {
        citas = nuevasCitas
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): CitaViewHolder {
        val binding = ItemCitaBinding.inflate(
            LayoutInflater.from(parent.context), parent, false
        )
        return CitaViewHolder(binding)
    }

    override fun onBindViewHolder(holder: CitaViewHolder, position: Int) {
        holder.bind(citas[position])
    }

    override fun getItemCount(): Int = citas.size

    class CitaViewHolder(
        private val binding: ItemCitaBinding
    ) : RecyclerView.ViewHolder(binding.root) {

        fun bind(cita: Cita) {
            binding.textViewFecha.text = formatearFecha(cita.fechaHora)

            // Mostramos los nombres reales; si el backend no los envía, caemos
            // de vuelta a los IDs para no dejar la fila vacía.
            val servicio = cita.servicioNombre ?: "Servicio nº ${cita.servicioId}"
            val empleado = cita.empleadoNombre ?: "Dr. nº ${cita.empleadoId}"
            binding.textViewServicio.text = "$servicio · $empleado"

            binding.textViewEstado.text = cita.estado
            aplicarBadgeEstado(cita.estado)
        }

        /** Colorea la píldora de estado con un fondo suave y texto a juego. */
        private fun aplicarBadgeEstado(estado: String) {
            val ctx = binding.root.context
            val (bgRes, textRes) = when (estado.uppercase()) {
                "CONFIRMADA" -> R.color.estado_confirmada_bg to R.color.estado_confirmada_text
                "CANCELADA" -> R.color.estado_cancelada_bg to R.color.estado_cancelada_text
                else -> R.color.estado_pendiente_bg to R.color.estado_pendiente_text
            }
            binding.textViewEstado.backgroundTintList =
                ColorStateList.valueOf(ContextCompat.getColor(ctx, bgRes))
            binding.textViewEstado.setTextColor(ContextCompat.getColor(ctx, textRes))
        }

        /** Convierte "2026-08-20T10:00:00" en "20 ago 2026 · 12:10" (igual que el
         *  escritorio). Quitamos el punto que el locale español añade tras el mes
         *  abreviado ("ago.") para que el formato coincida exactamente. */
        private fun formatearFecha(iso: String): String = try {
            LocalDateTime.parse(iso).format(FORMATO_SALIDA).replace(".", "")
        } catch (e: Exception) {
            iso // fallback: mostramos el texto crudo si el formato cambia
        }

        companion object {
            // Locale España: mes en castellano y abreviado ("20 ago 2026 · 12:10").
            private val FORMATO_SALIDA: DateTimeFormatter =
                DateTimeFormatter.ofPattern("dd MMM yyyy · HH:mm", Locale("es", "ES"))
        }
    }
}
