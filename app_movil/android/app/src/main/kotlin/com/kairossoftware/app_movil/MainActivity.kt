package com.kairossoftware.app_movil

import android.app.Activity
import android.app.UiModeManager
import android.content.Context
import android.content.Intent
import android.content.res.Configuration
import android.media.MediaCodecInfo.CodecProfileLevel
import android.media.MediaCodecList
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.LocaleList
import android.view.View
import android.view.KeyEvent
import android.view.ViewGroup
import android.webkit.WebView
import androidx.core.content.FileProvider
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import io.flutter.plugins.webviewflutter.WebViewFlutterAndroidExternalApi
import java.io.File

/**
 * Le pasa a Flutter datos del aparato que solo Android conoce:
 *   - nombre: fabricante y modelo (ej: "Philips 55PUD7406"). El servidor lo
 *     muestra en "Dispositivos conectados", para saber cuál liberar.
 *   - esTv: si corre en un televisor (Android TV / Google TV).
 *   - version: la versión de esta app instalada (la de pubspec.yaml).
 *   - carpetaTemporal: dónde dejar la APK nueva que se baja.
 *   - codecs: los códecs de video que este aparato sabe decodificar (h264,
 *     h265, mpeg2...), y si también los de 10 bits (h264_10, h265_10). La app
 *     no muestra lo que el aparato no puede ver (lo que da "imagen verde o
 *     negra con sonido", o franjas verdes y la imagen rota).
 * Y "instalar": abre el instalador de Android con esa APK (lib/actualizacion.dart);
 * "abrir": abre un enlace en otra app (ej: el WhatsApp del vendedor).
 * En el celular, además, vigila si se conecta una tele como pantalla (PantallaTele.kt):
 * ahí muestra la app con el diseño de TV.
 *
 * Además, para el reproductor de YouTube (un WebView, lib/movil/reproductor_youtube.dart):
 *   - El idioma preferido de la app es el español: el WebView se lo dice a
 *     YouTube, que en los videos con varios audios elige el castellano (y
 *     sus menús, en castellano), aunque la TV esté configurada en inglés.
 *   - "dentroDeYoutube": mete un script en el reproductor de YouTube (el marco
 *     de youtube.com, al que la página de la app no tiene acceso) antes de
 *     que cargue. Con eso la app elige el audio en castellano y cambia de
 *     idioma (la API oficial de YouTube no lo permite).
 *   - En la TV el WebView nunca se queda con el foco del control remoto: si
 *     Android le pasaba el foco (una flecha que la app no usaba), las flechas
 *     siguientes le llegaban a YouTube y no a la app (no se podía adelantar).
 */
class MainActivity : FlutterActivity() {
    private var devolviendoFocoWeb = false

    // Primer Atras: vuelve del reproductor web a los controles de KAIROS.
    // El siguiente Atras sigue el comportamiento habitual de Flutter.
    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (event.keyCode == KeyEvent.KEYCODE_BACK && esTv() &&
            (devolviendoFocoWeb || window.currentFocus?.let { esReproductorWeb(it) } == true)) {
            devolviendoFocoWeb = true
            if (event.action == KeyEvent.ACTION_UP) {
                devolviendoFocoWeb = false
                vistaDeFlutter(window.decorView)?.requestFocus()
            }
            return true
        }
        return super.dispatchKeyEvent(event)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        preferirEspanol()
        super.onCreate(savedInstanceState)
        if (esTv()) {
            window.decorView.viewTreeObserver.addOnGlobalFocusChangeListener { anterior, nuevo ->
                if (nuevo != null && dentroDeUnWebView(nuevo) && !esReproductorWeb(nuevo)) {
                    nuevo.isFocusable = false
                    nuevo.isFocusableInTouchMode = false
                    (anterior?.takeIf { !dentroDeUnWebView(it) } ?: vistaDeFlutter(window.decorView))?.requestFocus()
                }
            }
        }
    }

    override fun onResume() {
        preferirEspanol()   // Android lo vuelve al del sistema si cambió la configuración
        super.onResume()
        pantallaTele?.alVolver()
    }

    /** Sale de la app: que la tele siga mostrando solo la app (PantallaTele.alSalir). */
    override fun onPause() {
        super.onPause()
        pantallaTele?.alSalir()
    }

    /**
     * "Atrás" en el Inicio del celular cierra la app. Con una tele conectada,
     * en cambio, la manda al fondo: si se cerrara, la tele dejaría de mostrar
     * la app y volvería a mostrar el celular.
     */
    override fun popSystemNavigator(): Boolean {
        if (pantallaTele?.conectada == true) {
            moveTaskToBack(true)
            return true
        }
        return super.popSystemNavigator()
    }

    private fun esTv(): Boolean =
        (getSystemService(Context.UI_MODE_SERVICE) as UiModeManager).currentModeType ==
            Configuration.UI_MODE_TYPE_TELEVISION

    /** Castellano primero (latinoamericano y después cualquiera), y detrás los idiomas del aparato. */
    private fun preferirEspanol() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) return
        val delSistema = LocaleList.getDefault().toLanguageTags()
        if (delSistema.startsWith("es-419")) return
        LocaleList.setDefault(LocaleList.forLanguageTags("es-419,es,$delSistema"))
    }

    private fun dentroDeUnWebView(vista: View): Boolean {
        var actual: View? = vista
        while (actual != null) {
            if (actual is WebView) return true
            actual = actual.parent as? View
        }
        return false
    }

    private fun vistaDeFlutter(vista: View): View? {
        if (vista.javaClass.name.contains("FlutterView")) return vista
        if (vista is ViewGroup) {
            for (i in 0 until vista.childCount) {
                vistaDeFlutter(vista.getChildAt(i))?.let { return it }
            }
        }
        return null
    }

    /** La tele como segundo monitor (PantallaTele.kt). Solo en celulares: en la TV no hace falta. */
    private var pantallaTele: PantallaTele? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        prepararCanalDelAparato(this, flutterEngine)
        if (!esTv()) pantallaTele = PantallaTele(this, flutterEngine).also { it.empezar() }
    }

    override fun cleanUpFlutterEngine(flutterEngine: FlutterEngine) {
        pantallaTele?.terminar()
        pantallaTele = null
        super.cleanUpFlutterEngine(flutterEngine)
    }

    companion object {
        private fun esReproductorWeb(vista: View): Boolean {
            var actual: View? = vista
            while (actual != null) {
                if (actual is WebView) return actual.getTag(R.id.kairos_web_interactivo) == true
                actual = actual.parent as? View
            }
            return false
        }

        /**
         * El canal "kairos/dispositivo" de [motor]: el del celular y también el
         * de la tele (PantallaTele.kt), que es otro motor de Flutter en el mismo aparato.
         */
        fun prepararCanalDelAparato(
            actividad: Activity,
            motor: FlutterEngine,
            densidadDeVistas: () -> Double = { actividad.resources.displayMetrics.density.toDouble() },
        ) {
            MethodChannel(motor.dartExecutor.binaryMessenger, "kairos/dispositivo").setMethodCallHandler { llamada, resultado ->
                when (llamada.method) {
                    "datos" -> {
                        val modos = actividad.getSystemService(Context.UI_MODE_SERVICE) as UiModeManager
                        val fabricante = Build.MANUFACTURER.replaceFirstChar { it.uppercase() }
                        val modelo = Build.MODEL
                        val nombre = if (modelo.startsWith(fabricante, ignoreCase = true)) modelo else "$fabricante $modelo"
                        resultado.success(mapOf(
                            "nombre" to nombre,
                            "esTv" to (modos.currentModeType == Configuration.UI_MODE_TYPE_TELEVISION),
                            "version" to actividad.packageManager.getPackageInfo(actividad.packageName, 0).versionName,
                            // Para el diagnóstico de las fallas (ej. "Android 10")
                            "android" to Build.VERSION.RELEASE,
                            "carpetaTemporal" to File(actividad.cacheDir, "actualizaciones").apply { mkdirs() }.absolutePath,
                            "codecs" to codecsDeVideo(),
                            // Con la que dibujan las vistas de Android dentro de la app (YouTube): la de
                            // la pantalla de la actividad; en la tele del celular, la de la tele si se
                            // pudo (PantallaTele.prestarLaTeleAYoutube)
                            "densidadDeVistas" to densidadDeVistas(),
                        ))
                    }
                    "instalar" -> {
                        val archivo = File(llamada.argument<String>("ruta")!!)
                        // FileProvider: el instalador no puede leer la carpeta privada de la app,
                        // así que se le presta ese archivo con una dirección content://
                        val direccion = FileProvider.getUriForFile(actividad, "${actividad.packageName}.archivos", archivo)
                        val instalar = Intent(Intent.ACTION_VIEW).apply {
                            setDataAndType(direccion, "application/vnd.android.package-archive")
                            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
                        }
                        try {
                            actividad.startActivity(instalar)
                            resultado.success(true)
                        } catch (e: Exception) {
                            resultado.error("sin_instalador", e.message, null)
                        }
                    }
                    "prepararReproductorWeb" -> {
                        @Suppress("DEPRECATION")
                        val vista = WebViewFlutterAndroidExternalApi.getWebView(
                            motor, llamada.argument<Number>("webview")!!.toLong())
                        if (vista != null) {
                            vista.setTag(R.id.kairos_web_interactivo, true)
                            vista.isFocusable = true
                            vista.isFocusableInTouchMode = true
                            if (llamada.argument<Boolean>("enfocar") == true) vista.requestFocus()
                        }
                        resultado.success(vista != null)
                    }
                    "dentroDeYoutube" -> {
                        @Suppress("DEPRECATION")
                        val vista = WebViewFlutterAndroidExternalApi.getWebView(
                            motor, llamada.argument<Number>("webview")!!.toLong())
                        if (vista != null && WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) {
                            WebViewCompat.addDocumentStartJavaScript(
                                vista, llamada.argument<String>("script")!!, setOf("https://www.youtube.com"))
                            resultado.success(true)
                        } else {
                            resultado.success(false)   // WebView viejo: sigue andando, sin elegir el audio
                        }
                    }
                    "abrir" -> {
                        try {
                            actividad.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(llamada.argument<String>("url")!!)))
                            resultado.success(true)
                        } catch (e: Exception) {
                            // Ninguna app lo sabe abrir (ej: una TV sin navegador ni WhatsApp)
                            resultado.success(false)
                        }
                    }
                    else -> resultado.notImplemented()
                }
            }
        }

        /**
         * Los códecs de video que tiene algún decodificador del aparato, con los
         * nombres del servidor. Para H.264 y H.265 se fija además si alguno sabe
         * el perfil de 10 bits ("High 10" / "Main 10"): muchos TV box no.
         */
        private fun codecsDeVideo(): List<String> {
            val nombres = mapOf(
                "video/avc" to "h264",
                "video/hevc" to "h265",
                "video/mpeg2" to "mpeg2",
                "video/mp4v-es" to "mpeg4",
                "video/av01" to "av1",
                "video/x-vnd.on2.vp9" to "vp9",
                "video/wvc1" to "vc1",
                "video/vc1" to "vc1",
            )
            val perfiles10Bits = mapOf(
                "video/avc" to setOf(CodecProfileLevel.AVCProfileHigh10, CodecProfileLevel.AVCProfileHigh422,
                    CodecProfileLevel.AVCProfileHigh444),
                "video/hevc" to setOf(CodecProfileLevel.HEVCProfileMain10, CodecProfileLevel.HEVCProfileMain10HDR10),
            )
            return try {
                val codecs = mutableSetOf<String>()
                for (info in MediaCodecList(MediaCodecList.REGULAR_CODECS).codecInfos) {
                    if (info.isEncoder) continue
                    for (tipo in info.supportedTypes) {
                        val nombre = nombres[tipo.lowercase()] ?: continue
                        codecs.add(nombre)
                        val de10 = perfiles10Bits[tipo.lowercase()] ?: continue
                        val perfiles = try {
                            info.getCapabilitiesForType(tipo).profileLevels.map { it.profile }
                        } catch (e: Exception) {
                            emptyList()
                        }
                        if (perfiles.any { it in de10 }) codecs.add("${nombre}_10")
                    }
                }
                codecs.toList()
            } catch (e: Exception) {
                emptyList()   // no se sabe: la app prueba todas
            }
        }
    }
}
