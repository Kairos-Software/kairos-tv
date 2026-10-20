package io.flutter.plugins.videoplayer;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Kairos TV (pruebas): un servidor HTTP local que se porta como una lista Xtream con una
 * película. El link de la lista ({@link #link}) redirige al servidor de video con un permiso
 * nuevo cada vez (como hacen esos paneles); el servidor de video manda el archivo desde donde
 * se le pida (Range) si el permiso es el último. Cuenta cuántas veces se pidió cada uno: en
 * el de verdad, el link es lo que tarda cerca de un minuto.
 */
final class ServidorXtreamDePrueba implements AutoCloseable {
  private final byte[] video;
  private final ServerSocket servidor;
  final String base;
  final String link;

  /** Cuántas veces se pidió el link de la lista (lo lento). */
  final AtomicInteger alLink = new AtomicInteger();

  /** Cuántas veces se pidió al servidor de video. */
  final AtomicInteger alServidorDeVideo = new AtomicInteger();

  /** El permiso que da el link: la redirección lleva el número y solo sirve el último. */
  final AtomicInteger permiso = new AtomicInteger();

  ServidorXtreamDePrueba(byte[] video, String archivo) throws IOException {
    this.video = video;
    servidor = new ServerSocket(0, 50, InetAddress.getByName("127.0.0.1"));
    base = "http://127.0.0.1:" + servidor.getLocalPort();
    link = base + "/movie/usuario/clave/" + archivo;
    Thread atiende =
        new Thread(
            () -> {
              while (!servidor.isClosed()) {
                try (Socket conexion = servidor.accept()) {
                  atender(conexion);
                } catch (IOException e) {
                  // se cerró el servidor (o el cliente cortó): sigue con el próximo
                }
              }
            });
    atiende.setDaemon(true);
    atiende.start();
  }

  @Override
  public void close() throws IOException {
    servidor.close();
  }

  private void atender(Socket conexion) throws IOException {
    BufferedReader entrada =
        new BufferedReader(new InputStreamReader(conexion.getInputStream(), StandardCharsets.ISO_8859_1));
    String pedido = entrada.readLine();
    if (pedido == null) {
      return;
    }
    String rango = null;
    for (String linea = entrada.readLine(); linea != null && !linea.isEmpty(); linea = entrada.readLine()) {
      if (linea.toLowerCase(Locale.ROOT).startsWith("range:")) {
        rango = linea.substring(6).trim();
      }
    }
    String ruta = pedido.split(" ")[1];
    OutputStream salida = conexion.getOutputStream();
    if (ruta.startsWith("/movie/")) {
      alLink.incrementAndGet();
      int nuevo = permiso.incrementAndGet();
      String archivo = ruta.substring(ruta.lastIndexOf('/') + 1);
      responder(salida, "302 Found", "Location: " + base + "/video/" + archivo + "?permiso=" + nuevo, new byte[0]);
    } else if (ruta.startsWith("/video/")) {
      alServidorDeVideo.incrementAndGet();
      if (!ruta.endsWith("?permiso=" + permiso.get())) {
        responder(salida, "403 Forbidden", null, new byte[0]);
      } else {
        mandar(salida, rango);
      }
    } else {
      mandar(salida, rango); // "/directo/": sin redirección
    }
  }

  private static void responder(OutputStream salida, String estado, String cabecera, byte[] cuerpo)
      throws IOException {
    StringBuilder texto = new StringBuilder("HTTP/1.1 ").append(estado).append("\r\n");
    if (cabecera != null) {
      texto.append(cabecera).append("\r\n");
    }
    texto.append("Content-Length: ").append(cuerpo.length).append("\r\nConnection: close\r\n\r\n");
    salida.write(texto.toString().getBytes(StandardCharsets.ISO_8859_1));
    salida.write(cuerpo);
    salida.flush();
  }

  private void mandar(OutputStream salida, String rango) throws IOException {
    int desde = 0;
    if (rango != null && rango.startsWith("bytes=")) {
      desde = Integer.parseInt(rango.substring(6).split("-")[0]);
    }
    byte[] parte = Arrays.copyOfRange(video, desde, video.length);
    if (desde > 0) {
      responder(
          salida,
          "206 Partial Content",
          "Content-Range: bytes " + desde + "-" + (video.length - 1) + "/" + video.length,
          parte);
    } else {
      responder(salida, "200 OK", null, parte);
    }
  }
}
