# Reglas propias para R8 (el que achica la APK de producción; Flutter suma este
# archivo solo, si existe).

# "Ver en la tele" (PantallaTele.prestarLaTeleAYoutube): al plugin de WebView del
# motor de la tele se le cambia el contexto por dentro, buscando este campo por
# su nombre. Sin esta regla R8 le cambia el nombre y YouTube volvía a verse en
# una parte de la tele.
-keepclassmembers class io.flutter.plugins.webviewflutter.WebViewFlutterPlugin {
    io.flutter.plugins.webviewflutter.ProxyApiRegistrar proxyApiRegistrar;
}
