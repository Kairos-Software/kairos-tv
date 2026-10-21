# lib/widgets/

Piezas de pantalla que se usan en varias pantallas (como
`templates/parciales/` en Django).

| Archivo | Qué tiene |
|---|---|
| `comunes.dart` | `MarcaKairos` (la marca de `marca.dart`, vertical u horizontal), `BotonDegradado` (botón principal), `IconoDegradado`, `Avatar` (foto o iniciales con aro en degradé), `VistaError` (con "Reintentar"), `VistaVacia`, `AvisoError`, `TituloSeccion`, `TarjetaDatos` (filas "etiqueta: valor"), `Etiqueta` (chip de color). |
| `lista_paginada.dart` | `ListaPaginada`: lista que pide más páginas a la API al bajar (scroll infinito) y se recarga deslizando hacia abajo. |
| `espera_larga.dart` | `EsperaLarga`: debajo de la ruedita del reproductor (celular y TV), si una película tarda en arrancar dice que el servidor tarda en contestar, que la app sigue intentando y cuántos segundos van (`ControlSenal.avisoDeEspera`). |
| `imagen_guardada.dart` | Las imágenes de internet (pósters, logos, portadas): `ImagenGuardada` baja cada una **una sola vez** y la guarda en la caché de la app (hasta 150 MB; se borran las más viejas), y `imagenAlTamanio` la arma **del tamaño de su lugar** (un póster de 600x900 en una tarjeta de 150 de ancho ya no ocupa 2 MB de memoria; llena el lugar sin quedar borroso aunque sea apaisado). La usan `Imagen` (movil/componentes.dart), los logos de la TV, `LogoLegible` y el modo reposo. Antes eran `Image.network`: no guardaba nada (cada vez que se abría la app se bajaban todas) y las armaba enteras (trababa las grillas en un TV box). |
| `formulario.dart` | `DatosFormulario` + `CamposFormulario`: arman un formulario a partir de las secciones de `campos.dart` y muestran debajo de cada campo el error que devolvió la API. `filasDeSeccion` arma las filas para ver los datos. |
