# Reproductores web (app 1.2.44+47)

El tipo de fuente `web` aisla el reproductor en un WebView del dispositivo.
Oculta menus y enlaces, y no muestra la web mientras no detecta un video real. No extrae
ni guarda una URL temporal de video. YouTube y las fuentes directas conservan
sus reproductores actuales.

## Activar

1. Publicar los cambios del servidor y ejecutar `python manage.py migrate`.
2. Instalar la APK 1.2.44 o posterior en la TV o el celular.
3. Editar ESPN Premium: pegar la URL completa en **Agregar una fuente** y marcar
   **Abrir la fuente nueva como reproductor web**. Guardar.
4. Elegir esa fuente en los ajustes del reproductor; o cambiar su prioridad en
   el panel para que se abra primero.

Tambien se puede crear un canal desde **Probar un link**, marcando **Abrir como
reproductor web**. El panel la guarda como **Sin verificar**: que una pagina
abra no demuestra que su video funcione. Las apps anteriores no reciben este
formato porque no lo incluyen al pedir el catalogo.

## Comprobar en el dispositivo

- Abrir la fuente y comprobar imagen, audio y controles con el control remoto.
  En Android TV, el reproductor web recibe el foco. El primer Atras devuelve
  el foco a KAIROS; luego OK abre la guia y las flechas laterales las opciones.
  La opcion **Reproductor web** vuelve a pasar el control a la pagina.
- Cambiar de fuente, cambiar de canal y salir: el WebView se desmonta y carga
  una pagina vacia para detener tambien los videos en marcos externos.
- Mandar la app al fondo y volver: se vuelve a cargar la pagina.
- La app intenta iniciar el video y muestra sus controles cuando esta listo.
  La calidad depende del sitio. El silencio se propaga a los reproductores en
  iframes mediante un comando limitado al reproductor.
- Android System WebView necesita soportar scripts al inicio del documento.
  Si no los soporta, se muestra un error en lugar de abrir la web completa.

No se marca como reproduccion exitosa ni se envia estabilidad de un video solo
porque se haya cargado la pagina. Los errores web tienen un boton Reintentar;
se puede elegir otra fuente desde los ajustes de KAIROS.

El navegador integrado deniega permisos de camara/microfono. La ventana
principal solo puede conservar la URL de la fuente (con cambios de fragmento);
no puede navegar ni a otras paginas del mismo dominio. El script bloquea enlaces,
formularios y popups en los marcos. Tras comenzar el video se bloquean nuevas
navegaciones de marcos; las solicitudes de medios no son navegaciones.

Un canal JavaScript acepta solo estados pequenos del reproductor (listo, reproduciendo,
error y rechazo HTTP), con identificador por carga. No ejecuta instrucciones
arbitrarias ni ofrece acceso a funciones del dispositivo. La carga de HTML no
cancela el plazo de espera: debe detectarse reproduccion real. Si falla, se
oculta y descarga la pagina para que no quede audio en segundo plano.

## Estado de la prueba del enlace proporcionado

La pagina original de Pelota Libre responde y carga marcos de reproductores.
El extractor existente no la reconoce. La prueba aislada de escritorio llega a un marco final que devuelve HTTP 403
Forbidden, sin video. Esto no certifica compatibilidad con el sitio ni puede
resolverse simplemente ocultando el resto de la pagina.
Queda pendiente probar esa transmision en el WebView de la TV real. La prueba
puede variar por sitio, red, publicidad, restricciones y version de Android WebView.

## Pruebas sin depender del proveedor

`python scripts/test_reproductor_web.py` ejecuta cuatro pruebas en un navegador
aislado con todas las solicitudes interceptadas y un MP4 existente como fixture:
video real en iframe de otro origen, pantalla completa sin menus, bloqueo de
enlaces y popups, propagacion del silencio y diagnostico de un marco con HTTP 403.
Una pagina sin video no genera eventos de reproduccion. Requiere Playwright y
un navegador compatible; KAIROS_TEST_BROWSER permite indicar su ejecutable.
