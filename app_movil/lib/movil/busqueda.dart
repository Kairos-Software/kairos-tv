/// Buscar en el catálogo, igual en el celular (movil/buscar.dart) y en la TV
/// (tv/buscar.dart): sin tildes ni mayúsculas, y primero lo que EMPIEZA con
/// lo escrito (o tiene una palabra que empieza así), después lo que solo lo
/// contiene. Ej: "la" muestra antes "La casa de papel" que "Atlántida".
///
/// [QueBuscar] es el filtro de arriba de los resultados (Todo, En vivo,
/// Películas, Series). Arranca en el de la sección donde se estaba: buscar
/// desde Series busca series. Lo de las secciones nuevas (Música, Radio...)
/// aparece en "Todo", cada una con su título; ahí también se busca por la
/// categoría (en Música, el artista: "shakira" trae sus videos).
library;

import '../api/modelos.dart';
import 'datos.dart';

enum QueBuscar {
  todo('Todo'),
  enVivo('En vivo'),
  peliculas('Películas'),
  series('Series');

  const QueBuscar(this.texto);

  final String texto;
}

/// "Notícias Ñandú" -> "noticias nandu".
String sinTildes(String texto) {
  final minusculas = texto.toLowerCase();
  // Casi todos los nombres no tienen tildes: se devuelven tal cual (sin armar otro texto)
  if (!minusculas.codeUnits.any(_sinTilde.containsKey)) return minusculas;
  return String.fromCharCodes([for (final letra in minusculas.codeUnits) _sinTilde[letra] ?? letra]);
}

/// Cada letra con tilde -> la misma sin tilde.
final Map<int, int> _sinTilde = {
  for (final (i, letra) in 'áàäâãéèëêíìïîóòöôõúùüûñç'.codeUnits.indexed) letra: 'aaaaaeeeeiiiiooooouuuunc'.codeUnits[i],
};

/// El nombre de cada canal, película o serie ya pasado por [sinTildes] (con un
/// espacio adelante, para buscar "empieza con"). Se calcula la primera vez que
/// se busca y queda: antes se volvía a calcular con cada letra que se escribía,
/// para miles de películas y capítulos (en la TV se notaba al escribir).
final Expando<String> _simple = Expando('nombre simple');

String _nombreSimple(Object elemento, String nombre) => _simple[elemento] ??= ' ${sinTildes(nombre)}';

/// Lo que se encontró, por tipo (cada lista con [maximo] como mucho).
class Encontrado {
  const Encontrado({
    this.canales = const [],
    this.peliculas = const [],
    this.series = const [],
    this.nuevas = const [],
  });

  static const nada = Encontrado();

  final List<Canal> canales;
  final List<Canal> peliculas;
  final List<Serie> series;

  /// Lo de cada sección nueva (Música, Radio...), solo las que encontraron algo.
  final List<(SeccionNueva, List<Canal>)> nuevas;

  int cuantos(QueBuscar que) => switch (que) {
    QueBuscar.todo =>
      canales.length + peliculas.length + series.length + nuevas.fold(0, (total, n) => total + n.$2.length),
    QueBuscar.enVivo => canales.length,
    QueBuscar.peliculas => peliculas.length,
    QueBuscar.series => series.length,
  };

  bool vacio(QueBuscar que) => cuantos(que) == 0;
}

/// Busca [texto] en todo el catálogo. Con [conNumeros] (en la TV), "15"
/// también encuentra el canal 15.
Encontrado buscarEnCatalogo(Catalogo catalogo, String texto, {int maximo = 40, bool conNumeros = false}) {
  final buscado = sinTildes(texto.trim());
  if (buscado.isEmpty) return Encontrado.nada;

  List<T> filtrar<T>(Iterable<T> lista, String Function(T) nombre, [bool Function(T)? tambien]) {
    final empiezan = <T>[];
    final contienen = <T>[];
    for (final elemento in lista) {
      final simple = _nombreSimple(elemento as Object, nombre(elemento));
      if (simple.contains(' $buscado') || (tambien?.call(elemento) ?? false)) {
        empiezan.add(elemento);
        if (empiezan.length >= maximo) break;
      } else if (contienen.length < maximo && simple.contains(buscado)) {
        contienen.add(elemento);
      }
    }
    return [...empiezan, ...contienen].take(maximo).toList();
  }

  // Hay pocas categorías y muchos canales: cada una se pasa a "simple" una sola vez
  final categorias = <String, String>{};
  bool deLaCategoria(Canal canal) => categorias
      .putIfAbsent(canal.categoria, () => ' ${sinTildes(categoriaLegible(canal.categoria))}')
      .contains(' $buscado');

  return Encontrado(
    canales: filtrar(catalogo.canales, (c) => c.nombre, conNumeros ? (c) => catalogo.numeroDe(c) == buscado : null),
    peliculas: filtrar(catalogo.peliculas, (p) => p.nombre),
    series: filtrar(catalogo.series, (s) => s.nombre),
    nuevas: [
      for (final seccion in catalogo.seccionesNuevas)
        if (filtrar(seccion.canales, (c) => c.nombre, deLaCategoria) case final lista when lista.isNotEmpty)
          (seccion, lista),
    ],
  );
}
