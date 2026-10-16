package com.kairossoftware.app_movil

import android.app.Activity
import android.app.Presentation
import android.content.Intent
import android.hardware.display.DisplayManager
import android.media.AudioManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.provider.Settings
import android.view.Display
import android.view.KeyEvent
import android.view.WindowManager
import io.flutter.FlutterInjector
import io.flutter.embedding.android.ExclusiveAppComponent
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.android.FlutterView
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.embedding.engine.dart.DartExecutor
import io.flutter.plugin.common.MethodChannel
import io.flutter.plugins.videoplayer.KairosTele

/**
 * "Ver en la tele": el celular usa la TV como segundo monitor.
 *
 * Cuando el celular se conecta a una tele como pantalla (Transmitir pantalla /
 * Smart View / Duplicar pantalla, o un cable USB-C a HDMI), Android avisa que
 * hay una pantalla más ("de presentación"). Entonces en esa pantalla se
 * muestra la app con el diseño de TV (lib/tele/, que usa lib/tv/) en vez de
 * repetir la del celular: la tele no ve nada más del teléfono (ni
 * notificaciones ni otras apps mientras la app está adelante).
 *
 * La tele es un SEGUNDO motor de Flutter (arranca en `pantallaTele()` de
 * lib/main.dart) dibujado en una `Presentation` de Android. Los dos motores no
 * comparten memoria: se hablan por acá, con el canal "kairos/tele":
 *   celular -> "orden": qué tiene que mostrar la tele (sección, detalle, qué reproduce)
 *   celular -> "tecla": un botón del control remoto del celular (OK, pausa, flechas...)
 *   celular -> "atras": como el botón Atrás de un control
 *   celular -> "conectar": abre los ajustes de Android para elegir la tele
 *   celular -> "puedeQuedarFija" / "pedirQuedarFija": el permiso para que la
 *              tele muestre solo la app, siempre (ver mostrarEn)
 *   tele    -> "cerrada": la tele cerró sola algo que reproducía (terminó, Atrás)
 *   esta clase -> celular: "conectada" / "desconectada"
 * El video lo decodifica el celular y Android se lo manda a la tele.
 */
class PantallaTele(private val actividad: FlutterActivity, principal: FlutterEngine) : DisplayManager.DisplayListener {

    private val pantallas = actividad.getSystemService(DisplayManager::class.java)
    private val canalCelular = MethodChannel(principal.dartExecutor.binaryMessenger, CANAL)
    private var canalTele: MethodChannel? = null
    private var motor: FlutterEngine? = null
    private var vista: FlutterView? = null
    private var presentacion: Presentation? = null
    private var ventanaFija = false

    /** El volumen que tenía el celular antes de conectar la tele (para devolvérselo). */
    private var volumenAntes: Int? = null

    /** ¿Hay una tele conectada? (MainActivity: "Atrás" no cierra la app mientras tanto.) */
    val conectada: Boolean get() = presentacion != null

    /** Lo último que pidió el celular: la tele lo pide al arrancar (todavía no estaba escuchando). */
    private var ultimaOrden: Any? = null

    /** El motor de la tele se "presta" la actividad (lo necesitan los WebView de YouTube). */
    private val componente = object : ExclusiveAppComponent<Activity> {
        override fun detachFromFlutterEngine() {}
        override fun getAppComponent(): Activity = actividad
    }

    init {
        canalCelular.setMethodCallHandler { llamada, resultado ->
            when (llamada.method) {
                "estado" -> resultado.success(estado())
                "orden" -> {
                    ultimaOrden = llamada.arguments
                    canalTele?.invokeMethod("orden", llamada.arguments)
                    resultado.success(null)
                }
                "tecla" -> resultado.success(teclear(llamada.argument<String>("tecla") ?: ""))
                "atras" -> {
                    motor?.navigationChannel?.popRoute()
                    resultado.success(null)
                }
                "conectar" -> resultado.success(abrirAjustesDePantalla())
                "puedeQuedarFija" -> resultado.success(puedeQuedarFija())
                "pedirQuedarFija" -> resultado.success(pedirQuedarFija())
                else -> resultado.notImplemented()
            }
        }
    }

    fun empezar() {
        pantallas.registerDisplayListener(this, Handler(Looper.getMainLooper()))
        revisar()
    }

    fun terminar() {
        pantallas.unregisterDisplayListener(this)
        cerrar()
    }

    override fun onDisplayAdded(id: Int) = revisar()
    override fun onDisplayRemoved(id: Int) = revisar()
    override fun onDisplayChanged(id: Int) {}

    private fun estado(): Map<String, Any?> = mapOf(
        "conectada" to (presentacion != null),
        "nombre" to (presentacion?.display?.name ?: ""),
    )

    /** ¿Hay una pantalla de presentación (la tele)? Si apareció, se abre; si se fue, se cierra. */
    private fun revisar() {
        val pantalla = pantallas.getDisplays(DisplayManager.DISPLAY_CATEGORY_PRESENTATION).firstOrNull()
        if (pantalla == null) {
            cerrar()
        } else if (presentacion?.display?.displayId != pantalla.displayId) {
            cerrar()
            abrir(pantalla)
        }
    }

    private fun abrir(pantalla: Display) {
        val motor = this.motor ?: crearMotor()
        if (!mostrarEn(pantalla, motor)) {
            // La tele se desconectó justo en ese momento
            soltarMotor()
            return
        }
        ponerAjustesDeTele(pantalla)
        canalCelular.invokeMethod("conectada", estado())
    }

    /**
     * La ventana de la app en la tele. Con el permiso "Mostrar sobre otras
     * apps" es una ventana FIJA: sigue en la tele aunque se salga de la app o
     * se esté en los ajustes eligiendo la tele, así la tele nunca muestra el
     * celular. Sin el permiso es la de la actividad: Android la esconde (y la
     * tele vuelve a mostrar el celular) mientras la app no está adelante.
     * false = la tele ya no está.
     */
    private fun mostrarEn(pantalla: Display, motor: FlutterEngine): Boolean {
        val fija = puedeQuedarFija()
        val ventana = object : Presentation(if (fija) actividad.applicationContext else actividad, pantalla) {
            override fun onCreate(estado: Bundle?) {
                super.onCreate(estado)
                window?.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                val nueva = FlutterView(context)
                setContentView(nueva)
                nueva.attachToFlutterEngine(motor)
                vista = nueva
            }
        }
        if (fija && Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            ventana.window?.setType(WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY)
        }
        try {
            ventana.show()
        } catch (e: WindowManager.InvalidDisplayException) {
            return false
        } catch (e: WindowManager.BadTokenException) {
            return false
        }
        presentacion = ventana
        ventanaFija = fija
        motor.lifecycleChannel.appIsResumed()
        return true
    }

    /** Volvió a la app: si recién dio el permiso, la ventana pasa a ser fija (la app de la tele sigue igual). */
    fun alVolver() {
        val actual = presentacion ?: return
        val motor = motor ?: return
        if (ventanaFija || !puedeQuedarFija()) return
        val pantalla = actual.display
        quitarVentana()
        if (!mostrarEn(pantalla, motor)) cerrar()
    }

    private fun puedeQuedarFija(): Boolean =
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && Settings.canDrawOverlays(actividad)

    /** La pantalla de Android para dar el permiso "Mostrar sobre otras apps" (de esta app). */
    private fun pedirQuedarFija(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return false
        return try {
            actividad.startActivity(
                Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:${actividad.packageName}")),
            )
            true
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Mientras hay tele: el video hasta 720p y más espera tras un corte
     * (KairosTele, en paquetes/video_player_android), y el volumen del celular
     * al máximo. Con la tele, el sonido sale solo por la tele, y con el
     * volumen del celular bajo se oía bajo. Al desconectarse se devuelve como estaba.
     */
    private fun ponerAjustesDeTele(pantalla: Display) {
        val alto = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) pantalla.mode.physicalHeight else 720
        KairosTele.altoMaximo = alto.coerceIn(480, 720)
        KairosTele.esperaTrasCorte = 8000
        try {
            val audio = actividad.getSystemService(AudioManager::class.java)
            val maximo = audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
            val ahora = audio.getStreamVolume(AudioManager.STREAM_MUSIC)
            if (ahora < maximo) {
                volumenAntes = ahora
                audio.setStreamVolume(AudioManager.STREAM_MUSIC, maximo, 0)
            }
        } catch (e: Exception) {
            // Este celular no deja cambiar el volumen (modo No molestar): queda como estaba
        }
    }

    private fun sacarAjustesDeTele() {
        KairosTele.altoMaximo = 0
        KairosTele.esperaTrasCorte = 5000
        val antes = volumenAntes ?: return
        volumenAntes = null
        try {
            actividad.getSystemService(AudioManager::class.java).setStreamVolume(AudioManager.STREAM_MUSIC, antes, 0)
        } catch (e: Exception) {
            // Idem
        }
    }

    private fun crearMotor(): FlutterEngine {
        val nuevo = FlutterEngine(actividad.applicationContext)
        // Los mismos datos del aparato que el motor del celular (nombre, códecs...)
        MainActivity.prepararCanalDelAparato(actividad, nuevo)
        nuevo.activityControlSurface.attachToActivity(componente, actividad.lifecycle)
        canalTele = MethodChannel(nuevo.dartExecutor.binaryMessenger, CANAL).apply {
            setMethodCallHandler { llamada, resultado ->
                when (llamada.method) {
                    "pedirOrden" -> resultado.success(ultimaOrden)
                    "cerrada" -> {
                        canalCelular.invokeMethod("cerrada", llamada.arguments)
                        resultado.success(null)
                    }
                    else -> resultado.notImplemented()
                }
            }
        }
        val cargador = FlutterInjector.instance().flutterLoader()
        nuevo.dartExecutor.executeDartEntrypoint(
            DartExecutor.DartEntrypoint(cargador.findAppBundlePath(), "pantallaTele"),
        )
        motor = nuevo
        return nuevo
    }

    private fun cerrar() {
        val estaba = presentacion != null
        quitarVentana()
        soltarMotor()
        if (estaba) {
            sacarAjustesDeTele()
            canalCelular.invokeMethod("desconectada", null)
        }
    }

    private fun quitarVentana() {
        presentacion?.let {
            try {
                it.dismiss()
            } catch (e: Exception) {
                // La ventana ya no existía (la tele se fue)
            }
        }
        presentacion = null
        ventanaFija = false
        vista?.detachFromFlutterEngine()
        vista = null
    }

    private fun soltarMotor() {
        motor?.let {
            it.activityControlSurface.detachFromActivity()
            it.destroy()
        }
        motor = null
        canalTele = null
    }

    /** Un botón del control del celular, como si fuera el control remoto de la tele. */
    private fun teclear(nombre: String): Boolean {
        val codigo = TECLAS[nombre] ?: return false
        val destino = vista ?: return false
        val ahora = SystemClock.uptimeMillis()
        destino.dispatchKeyEvent(KeyEvent(ahora, ahora, KeyEvent.ACTION_DOWN, codigo, 0))
        destino.dispatchKeyEvent(KeyEvent(ahora, SystemClock.uptimeMillis(), KeyEvent.ACTION_UP, codigo, 0))
        return true
    }

    /**
     * La lista de teles de Android ("Transmitir" / "Pantalla inalámbrica").
     * Cada marca la tiene en otro lado: si este celular no deja abrirla desde
     * una app (false), la app explica que se abre desde los accesos rápidos.
     */
    private fun abrirAjustesDePantalla(): Boolean {
        for (accion in listOf(Settings.ACTION_CAST_SETTINGS, "android.settings.WIFI_DISPLAY_SETTINGS")) {
            try {
                actividad.startActivity(Intent(accion))
                return true
            } catch (e: Exception) {
                // Este aparato no tiene esa pantalla de ajustes: la siguiente
            }
        }
        return false
    }

    companion object {
        const val CANAL = "kairos/tele"

        private val TECLAS = mapOf(
            "ok" to KeyEvent.KEYCODE_DPAD_CENTER,
            "arriba" to KeyEvent.KEYCODE_DPAD_UP,
            "abajo" to KeyEvent.KEYCODE_DPAD_DOWN,
            "izquierda" to KeyEvent.KEYCODE_DPAD_LEFT,
            "derecha" to KeyEvent.KEYCODE_DPAD_RIGHT,
            "pausa" to KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE,
            "adelantar" to KeyEvent.KEYCODE_MEDIA_FAST_FORWARD,
            "atrasar" to KeyEvent.KEYCODE_MEDIA_REWIND,
            "canalMas" to KeyEvent.KEYCODE_CHANNEL_UP,
            "canalMenos" to KeyEvent.KEYCODE_CHANNEL_DOWN,
            "guia" to KeyEvent.KEYCODE_GUIDE,
        )
    }
}
