/*
 * "Dónde va" una serie: 1 Categoría → 2 Serie → 3 Temporada, mostrando lo que YA hay.
 *
 * Lo usan Traer de YouTube (canales/youtube.html) y, en Organizar contenido, "Unir en una sola serie" y
 * "Pasar a Series" (canales/organizar.html). El árbol lo arma consultas.arbol_de_series().
 *
 * Marcado:
 *   <div data-destino-serie data-arbol="<id del json_script>"   (o data-arbol-url="<canales:series_arbol>": se pide
 *                                                                 recién cuando la caja aparece en pantalla)
 *        data-ds-categoria="<name del select>" data-ds-nueva="<name de la categoría nueva>"
 *        data-ds-serie="<name del texto con el nombre>" data-ds-temporada="<name del número>">
 *     ...esos campos (son los que se mandan)...
 *     <p data-ds-resumen></p>
 *   </div>
 *
 * Al lado del nombre agrega la lista de las series de esa categoría (o "+ Una serie nueva", que muestra el
 * texto) y al lado del número, la de las temporadas de la serie elegida con cuántos capítulos tiene cada una
 * (o "+ Temporada nueva"). Elegir una serie que ya existe pone su categoría (una serie va en UNA categoría).
 * Cada cambio escribe "Va a quedar: Series › Disney › Buena suerte Charlie › Temporada 2" y avisa con el
 * evento "destino-serie" (la página puede usar caja.dataset.resumen).
 */
(function () {
    'use strict';

    var NUEVA = '+nueva';

    function clave(texto) {
        return (texto || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
    }

    function opcion(valor, texto) {
        var elemento = document.createElement('option');
        elemento.value = valor;
        elemento.textContent = texto;
        return elemento;
    }

    function preparar(caja, arbol) {
        var campo = function (cual) {
            return caja.dataset[cual] ? caja.querySelector('[name="' + caja.dataset[cual] + '"]') : null;
        };
        var categoria = campo('dsCategoria');
        var nueva = campo('dsNueva');
        var nombre = campo('dsSerie');
        var temporada = campo('dsTemporada');
        var resumen = caja.querySelector('[data-ds-resumen]');
        if (!nombre || !temporada) return;
        var form = nombre.form;

        var listaSeries = document.createElement('select');
        listaSeries.className = nombre.className.replace('form-control', 'form-select') + ' ds-lista';
        listaSeries.setAttribute('aria-label', 'Serie');
        nombre.parentNode.insertBefore(listaSeries, nombre);
        nombre.placeholder = nombre.placeholder || 'Nombre de la serie nueva';

        var listaTemporadas = document.createElement('select');
        listaTemporadas.className = temporada.className.replace('form-control', 'form-select') + ' ds-lista';
        listaTemporadas.removeAttribute('style');
        listaTemporadas.setAttribute('aria-label', 'Temporada');
        temporada.parentNode.insertBefore(listaTemporadas, temporada);

        var aviso = document.createElement('p');
        aviso.className = 'ds-aviso';
        aviso.hidden = true;
        aviso.setAttribute('role', 'status');
        nombre.parentNode.insertBefore(aviso, nombre.nextSibling);

        function categoriaElegida() {
            if (nueva && nueva.value.trim()) return {nombre: nueva.value.trim(), nueva: true};
            if (categoria && categoria.value) return {nombre: categoria.selectedOptions[0].textContent.trim(), nueva: false};
            return null;
        }

        function grupoDe(nombreCategoria) {
            return arbol.categorias.filter(function (g) { return clave(g.nombre) === clave(nombreCategoria); })[0];
        }

        function buscarSerie(texto) {
            for (var i = 0; i < arbol.categorias.length; i++) {
                var grupo = arbol.categorias[i];
                for (var j = 0; j < grupo.series.length; j++) {
                    if (clave(grupo.series[j].nombre) === clave(texto)) return {serie: grupo.series[j], categoria: grupo};
                }
            }
            return null;
        }

        // Pone la categoría de una serie que ya existe (la de la lista, o escrita como nueva si no está)
        function ponerCategoria(nombreCategoria) {
            if (!categoria || !nombreCategoria) return;
            var elegida = categoriaElegida();
            if (elegida && clave(elegida.nombre) === clave(nombreCategoria)) return;
            var existe = Array.prototype.filter.call(categoria.options, function (o) {
                return o.value && !o.disabled && !(o.parentNode.disabled) && clave(o.textContent) === clave(nombreCategoria);
            })[0];
            if (existe) {
                categoria.value = existe.value;
                if (nueva) nueva.value = '';
                categoria.dispatchEvent(new Event('change', {bubbles: true}));
            } else if (nueva) {
                nueva.value = nombreCategoria;
                nueva.dispatchEvent(new Event('input', {bubbles: true}));
            }
        }

        function pintarSeries() {
            var elegida = categoriaElegida();
            var antes = listaSeries.value;
            var grupos = elegida ? (elegida.nueva ? [] : [grupoDe(elegida.nombre)].filter(Boolean)) : arbol.categorias;
            var hay = grupos.some(function (g) { return g.series.length; });
            listaSeries.textContent = '';
            listaSeries.appendChild(opcion('', !elegida ? 'Elegí la serie (o primero la categoría)…'
                : (hay ? 'Elegí la serie…' : 'No tiene series todavía')));
            grupos.forEach(function (grupo) {
                var destino = listaSeries;
                if (!elegida) {
                    destino = document.createElement('optgroup');
                    destino.label = grupo.nombre || 'Sin categoría';
                    listaSeries.appendChild(destino);
                }
                grupo.series.forEach(function (serie) {
                    var total = serie.temporadas.reduce(function (suma, t) { return suma + t[1]; }, 0);
                    var cuantas = serie.temporadas.length;
                    destino.appendChild(opcion(serie.nombre, serie.nombre + ' (' +
                        (cuantas > 1 ? cuantas + ' temp., ' : '') + total + ' cap.)'));
                });
            });
            listaSeries.appendChild(opcion(NUEVA, '＋ Una serie nueva…'));
            var sigue = Array.prototype.some.call(listaSeries.options, function (o) { return o.value === antes; });
            listaSeries.value = sigue ? antes : (elegida && !hay ? NUEVA : '');
            mostrar();
        }

        function pintarTemporadas(serie) {
            var antes = temporada.value;
            listaTemporadas.textContent = '';
            if (!serie) {
                // Serie nueva: el número (arranca en la 1). Sin elegir serie: nada para elegir todavía.
                var esNueva = listaSeries.value === NUEVA;
                listaTemporadas.appendChild(opcion('', 'Primero elegí la serie'));
                listaTemporadas.disabled = true;
                listaTemporadas.hidden = esNueva;
                temporada.hidden = !esNueva;
                if (esNueva && !temporada.value) temporada.value = 1;
                return;
            }
            listaTemporadas.disabled = temporada.disabled;
            listaTemporadas.hidden = false;
            temporada.hidden = true;
            listaTemporadas.appendChild(opcion('', 'Elegí la temporada…'));
            serie.temporadas.forEach(function (t) {
                listaTemporadas.appendChild(opcion(String(t[0]), 'Temporada ' + t[0] + ' (tiene ' + t[1] +
                    '; siguen del ' + (t[2] + 1) + ')'));
            });
            var proxima = Math.max.apply(null, serie.temporadas.map(function (t) { return t[0]; })) + 1;
            listaTemporadas.appendChild(opcion(String(proxima), '＋ Nueva: temporada ' + proxima));
            var sigue = Array.prototype.some.call(listaTemporadas.options, function (o) { return o.value && o.value === String(antes); });
            listaTemporadas.value = sigue ? String(antes) : '';
            temporada.value = listaTemporadas.value;
        }

        function mostrar() {
            var valor = listaSeries.value;
            var existente = valor && valor !== NUEVA ? buscarSerie(valor) : null;
            nombre.hidden = valor !== NUEVA;
            if (existente) nombre.value = existente.serie.nombre;
            else if (!valor || buscarSerie(nombre.value)) nombre.value = '';
            pintarTemporadas(existente && existente.serie);
            // Lo que falta elegir lo marca el navegador al mandar (las listas no se mandan: llenan los campos)
            listaSeries.required = true;
            nombre.required = valor === NUEVA;
            listaTemporadas.required = !!existente;
            if (categoria) categoria.required = !existente && !(nueva && nueva.value.trim());
            contar();
        }

        function contar() {
            var elegida = categoriaElegida();
            var valor = listaSeries.value;
            var partes = ['Series', elegida ? elegida.nombre + (elegida.nueva ? ' (categoría nueva)' : '') : '¿categoría?'];
            if (valor === NUEVA) partes.push((nombre.value.trim() || '¿nombre?') + ' (serie nueva)');
            else partes.push(valor || '¿serie?');
            var opcionTemporada = listaTemporadas.selectedOptions[0];
            if (valor === NUEVA) partes.push('Temporada ' + (temporada.value || 1));
            else if (valor && listaTemporadas.value) {
                partes.push('Temporada ' + listaTemporadas.value +
                    (opcionTemporada && opcionTemporada.textContent.indexOf('＋') === 0 ? ' (nueva)' : ''));
            } else partes.push('¿temporada?');
            var texto = 'Va a quedar: ' + partes.join(' › ');
            caja.dataset.resumen = texto;
            if (resumen) resumen.textContent = texto;
            caja.dispatchEvent(new CustomEvent('destino-serie', {bubbles: true}));
        }

        // Lo que ya trae el formulario (volver con un error, o "Agregar capítulos" desde la serie)
        function sincronizar() {
            var existente = nombre.value.trim() ? buscarSerie(nombre.value) : null;
            if (existente) ponerCategoria(existente.categoria.nombre);
            pintarSeries();
            if (existente) listaSeries.value = existente.serie.nombre;
            else if (nombre.value.trim()) listaSeries.value = NUEVA;
            mostrar();
        }

        listaSeries.addEventListener('change', function () {
            aviso.hidden = true;
            var existente = listaSeries.value !== NUEVA ? buscarSerie(listaSeries.value) : null;
            temporada.value = '';   // al cambiar de serie, la temporada se elige de nuevo
            if (existente) {
                var serieElegida = existente.serie.nombre;
                ponerCategoria(existente.categoria.nombre);
                listaSeries.value = serieElegida;
            }
            mostrar();
            if (listaSeries.value === NUEVA) nombre.focus();
        });
        listaTemporadas.addEventListener('change', function () {
            temporada.value = listaTemporadas.value;
            contar();
        });
        if (categoria) categoria.addEventListener('change', pintarSeries);
        if (nueva) nueva.addEventListener('input', pintarSeries);
        nombre.addEventListener('input', contar);
        temporada.addEventListener('input', contar);
        // Escribió como nueva una serie que ya existe: se elige esa (si no, quedarían dos)
        nombre.addEventListener('change', function () {
            var existente = buscarSerie(nombre.value);
            if (!existente) return;
            ponerCategoria(existente.categoria.nombre);
            listaSeries.value = existente.serie.nombre;
            temporada.value = '';
            mostrar();
            aviso.textContent = '«' + existente.serie.nombre + '» ya existe' +
                (existente.categoria.nombre ? ' (en ' + existente.categoria.nombre + ')' : '') +
                ': se eligió esa serie. Elegí a qué temporada van.';
            aviso.hidden = false;
        });
        // La página cambió los campos por su cuenta (un canal sugerido en Traer de YouTube)
        caja.addEventListener('destino-serie:refrescar', sincronizar);
        // En un formulario sin validación del navegador (Traer de YouTube), se revisa acá
        if (form && form.noValidate) {
            form.addEventListener('submit', function (evento) {
                // Solo lo que se ve (en Películas, la parte de la serie está escondida)
                var falta = [listaSeries, nombre, listaTemporadas].filter(function (c) {
                    return c.offsetParent && !c.disabled && c.required && !c.value.trim();
                })[0];
                if (falta) {
                    evento.preventDefault();
                    evento.stopImmediatePropagation();
                    falta.reportValidity();
                    falta.focus();
                }
            }, true);
        }
        sincronizar();
    }

    // El árbol: en la página (json_script) o pedido una sola vez cuando hace falta (Organizar: al abrir
    // "Unir" o "Pasar a Series"; cargarlo en cada página sería pedirle al servidor todas las series por nada)
    var pedidos = {};
    function pedirArbol(url) {
        pedidos[url] = pedidos[url] || fetch(url, {credentials: 'same-origin', headers: {'Accept': 'application/json'}})
            .then(function (respuesta) { return respuesta.ok ? respuesta.json() : {categorias: []}; })
            .catch(function () { return {categorias: []}; });
        return pedidos[url];
    }

    function cuandoSeVea(caja, hacer) {
        if (!('IntersectionObserver' in window)) return hacer();
        var mirar = new IntersectionObserver(function (entradas) {
            if (!entradas.some(function (e) { return e.isIntersecting; })) return;
            mirar.disconnect();
            hacer();
        });
        mirar.observe(caja);
    }

    document.querySelectorAll('[data-destino-serie]').forEach(function (caja) {
        if (caja.dataset.arbol) {
            var datos = document.getElementById(caja.dataset.arbol);
            preparar(caja, datos ? JSON.parse(datos.textContent) : {categorias: []});
        } else if (caja.dataset.arbolUrl) {
            cuandoSeVea(caja, function () {
                pedirArbol(caja.dataset.arbolUrl).then(function (arbol) { preparar(caja, arbol); });
            });
        }
    });
})();
