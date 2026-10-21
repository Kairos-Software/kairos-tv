# lib/widgets/

Piezas de pantalla que se usan en varias pantallas (como
`templates/parciales/` en Django).

| Archivo | Qué tiene |
|---|---|
| `comunes.dart` | `MarcaKairos` (la marca de `marca.dart`, vertical u horizontal), `BotonDegradado` (botón principal), `IconoDegradado`, `Avatar` (foto o iniciales con aro en degradé), `VistaError` (con "Reintentar"), `VistaVacia`, `AvisoError`, `TituloSeccion`, `TarjetaDatos` (filas "etiqueta: valor"), `Etiqueta` (chip de color). |
| `lista_paginada.dart` | `ListaPaginada`: lista que pide más páginas a la API al bajar (scroll infinito) y se recarga deslizando hacia abajo. |
| `espera_larga.dart` | `EsperaLarga`: debajo de la ruedita del reproductor (celular y TV), si una película tarda en arrancar dice que el servidor tarda en contestar, que la app sigue intentando y cuántos segundos van (`ControlSenal.avisoDeEspera`). |
| `formulario.dart` | `DatosFormulario` + `CamposFormulario`: arman un formulario a partir de las secciones de `campos.dart` y muestran debajo de cada campo el error que devolvió la API. `filasDeSeccion` arma las filas para ver los datos. |
