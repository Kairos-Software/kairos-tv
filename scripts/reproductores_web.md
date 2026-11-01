# Reproductores web (app 1.2.43+46)

El tipo de fuente `web` abre la pagina en un WebView del dispositivo. No extrae
ni guarda una URL temporal de video. YouTube y las fuentes directas conservan
sus reproductores actuales.

## Activar

1. Publicar los cambios del servidor y ejecutar `python manage.py migrate`.
2. Instalar la APK 1.2.43 o posterior en la TV o el celular.
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
- Si la pagina pide iniciar el video, usar sus controles. La calidad y los
  controles del video dependen del sitio; el silencio de KAIROS solo alcanza
  los videos accesibles del documento principal, no los iframes externos.

No se marca como reproduccion exitosa ni se envia estabilidad de un video solo
porque se haya cargado la pagina. Los errores web tienen un boton Reintentar;
se puede elegir otra fuente desde los ajustes de KAIROS.

El navegador integrado deniega permisos de camara/microfono y navegaciones a
otros dominios en la ventana principal. Permite marcos HTTP(S), necesarios para
reproductores incrustados. No agrega canales JavaScript hacia funciones nativas.

## Estado de la prueba del enlace proporcionado

La pagina original de Pelota Libre responde y carga marcos de reproductores.
El extractor existente no la reconoce. En una prueba aislada de escritorio no
se observo video reproduciendose; esto no certifica compatibilidad con el sitio.
Queda pendiente probar esa transmision en el WebView de la TV real. La prueba
puede variar por sitio, red, publicidad, restricciones y version de Android WebView.
