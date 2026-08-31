package com.example.appclinica

import android.animation.ObjectAnimator
import android.animation.ValueAnimator
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.view.animation.AccelerateDecelerateInterpolator
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView

/**
 * Adapter del chat. Pinta cada [ChatMessage] con una de dos plantillas de fila
 * (usuario / IA) según [ChatMessage.isUser], usando el mecanismo de view types.
 *
 * Además, cuando [typing] está activo, muestra una fila extra al final con el
 * indicador "escribiendo…" (tres puntos animados), gestionada por su propio
 * [TypingViewHolder].
 *
 * item_chat_user.xml e item_chat_ai.xml comparten `@id/textMensaje`, así que los
 * mensajes reales comparten un único [ChatViewHolder].
 */
class ChatAdapter(
    private val mensajes: MutableList<ChatMessage> = mutableListOf()
) : RecyclerView.Adapter<RecyclerView.ViewHolder>() {

    // Cuando es true, se pinta la fila del indicador tras el último mensaje real.
    private var typing = false

    /** Copia inmutable de los mensajes reales (sin el indicador "escribiendo…"). */
    fun currentMessages(): List<ChatMessage> = mensajes.toList()

    /** Añade un mensaje al final y notifica solo esa inserción. */
    fun addMessage(mensaje: ChatMessage) {
        mensajes.add(mensaje)
        notifyItemInserted(mensajes.size - 1)
    }

    /** Muestra el indicador "escribiendo…" como última fila (idempotente). */
    fun showTyping() {
        if (typing) return
        typing = true
        notifyItemInserted(mensajes.size) // se coloca tras el último mensaje real
    }

    /** Oculta el indicador si estaba visible (idempotente). */
    fun hideTyping() {
        if (!typing) return
        typing = false
        notifyItemRemoved(mensajes.size) // posición que ocupaba el indicador
    }

    /** Índice del último elemento visible (mensaje real o indicador). */
    fun lastPosition(): Int = itemCount - 1

    override fun getItemViewType(position: Int): Int = when {
        typing && position == mensajes.size -> VIEW_TYPE_TYPING
        mensajes[position].isUser -> VIEW_TYPE_USER
        else -> VIEW_TYPE_AI
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): RecyclerView.ViewHolder {
        val inflater = LayoutInflater.from(parent.context)
        return when (viewType) {
            VIEW_TYPE_TYPING ->
                TypingViewHolder(inflater.inflate(R.layout.item_chat_typing, parent, false))
            VIEW_TYPE_USER ->
                ChatViewHolder(inflater.inflate(R.layout.item_chat_user, parent, false))
            else ->
                ChatViewHolder(inflater.inflate(R.layout.item_chat_ai, parent, false))
        }
    }

    override fun onBindViewHolder(holder: RecyclerView.ViewHolder, position: Int) {
        // La fila del indicador no tiene datos que enlazar; se anima al adjuntarse.
        if (holder is ChatViewHolder) holder.bind(mensajes[position])
    }

    // El total incluye la fila del indicador cuando está activo.
    override fun getItemCount(): Int = mensajes.size + if (typing) 1 else 0

    // La animación solo debe correr mientras la fila es visible: la arrancamos al
    // adjuntarse a la ventana y la paramos al desadjuntarse (ahorra batería).
    override fun onViewAttachedToWindow(holder: RecyclerView.ViewHolder) {
        if (holder is TypingViewHolder) holder.startAnimation()
    }

    override fun onViewDetachedFromWindow(holder: RecyclerView.ViewHolder) {
        if (holder is TypingViewHolder) holder.stopAnimation()
    }

    /** Burbuja de mensaje real (usuario o IA). */
    class ChatViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val textMensaje: TextView = itemView.findViewById(R.id.textMensaje)

        fun bind(mensaje: ChatMessage) {
            textMensaje.text = mensaje.text
        }
    }

    /** Indicador "escribiendo…": tres puntos que rebotan de forma desfasada. */
    class TypingViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val dots = listOf<View>(
            itemView.findViewById(R.id.dot1),
            itemView.findViewById(R.id.dot2),
            itemView.findViewById(R.id.dot3)
        )
        private val animators = mutableListOf<ObjectAnimator>()

        fun startAnimation() {
            stopAnimation() // evita duplicar animadores si se re-adjunta la vista

            // Amplitud del rebote en píxeles reales del dispositivo.
            val amplitude = 6f * itemView.resources.displayMetrics.density

            dots.forEachIndexed { index, dot ->
                val animator = ObjectAnimator.ofFloat(
                    dot, View.TRANSLATION_Y, 0f, -amplitude, 0f
                ).apply {
                    duration = 600L
                    startDelay = index * 150L // desfase entre puntos
                    repeatCount = ValueAnimator.INFINITE
                    interpolator = AccelerateDecelerateInterpolator()
                    start()
                }
                animators.add(animator)
            }
        }

        fun stopAnimation() {
            animators.forEach { it.cancel() }
            animators.clear()
            dots.forEach { it.translationY = 0f } // deja los puntos en reposo
        }
    }

    companion object {
        private const val VIEW_TYPE_AI = 0
        private const val VIEW_TYPE_USER = 1
        private const val VIEW_TYPE_TYPING = 2
    }
}
