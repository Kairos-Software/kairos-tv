/*
 * "¿Dónde va?" en la pantalla de una lista importada (canales/importacion.html, paso 3):
 * elegir la categoría del panel (o una nueva) y, en Series, la serie (o una nueva) y la temporada.
 *
 *   - "＋ Una categoría nueva…" / "＋ Una serie nueva…" muestran el campo para escribir el nombre.
 *   - Una serie que ya existe va en SU categoría: se pone sola y no se puede cambiar (se explica).
 *   - "Recordarlo" se ve solo cuando se eligió una categoría (y ninguna serie).
 *   - Abajo dice cómo va a quedar, y el botón se activa cuando hay algo elegido.
 * Lo manda el formulario a canales:importacion_destino (servicios.ubicar), que vuelve a revisar todo.
 */
(function () {
    'use strict';

    var NUEVA = '+nueva';
    var form = document.querySelector('[data-donde-va]');
    if (!form) return;

    var categoria = form.querySelector('[name=destino_categoria]');
    var categoriaNueva = form.querySelector('[name=categoria_nueva]');
    var serie = form.querySelector('[name=destino_serie]');
    var serieNueva = form.querySelector('[name=serie_nueva]');
    var conSerie = form.querySelector('[data-solo-con-serie]');
    var temporada = form.querySelector('[name=temporada]');
    var recordar = form.querySelector('[data-recordar]');
    var resumen = form.querySelector('[data-resumen]');
    var boton = form.querySelector('[type=submit]');

    var aviso = document.createElement('p');
    aviso.className = 'imp-paso-ayuda mt-1';
    aviso.hidden = true;
    categoria.parentNode.appendChild(aviso);

    function clave(texto) {
        return (texto || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
    }

    function categoriaElegida() {
        if (categoria.value === NUEVA) return categoriaNueva.value.trim();
        return categoria.value;
    }

    function serieElegida() {
        if (!serie) return '';
        if (serie.value === NUEVA) return serieNueva.value.trim();
        return serie.value;
    }

    // La categoría de la serie que ya existe ('' = la serie es nueva, o no tiene categoría)
    function categoriaDeLaSerie() {
        if (!serie || !serie.value || serie.value === NUEVA) return '';
        return serie.selectedOptions[0].dataset.categoria || '';
    }

    function ponerLaDeLaSerie(nombre) {
        var existe = Array.prototype.filter.call(categoria.options, function (o) {
            return o.value && o.value !== NUEVA && clave(o.value) === clave(nombre);
        })[0];
        if (existe) {
            categoria.value = existe.value;
        } else {
            categoria.value = NUEVA;
            categoriaNueva.value = nombre;
        }
    }

    function actualizar() {
        var deLaSerie = categoriaDeLaSerie();
        // Una serie que ya existe va en su categoría: elegir otra la partiría en dos
        if (deLaSerie) {
            ponerLaDeLaSerie(deLaSerie);
            aviso.textContent = '«' + serie.value + '» está en «' + deLaSerie + '»: sus capítulos van ahí.';
        }
        categoria.disabled = !!deLaSerie;
        categoriaNueva.readOnly = !!deLaSerie;
        aviso.hidden = !deLaSerie;

        categoriaNueva.hidden = categoria.value !== NUEVA;
        categoriaNueva.required = categoria.value === NUEVA;
        if (serie) {
            serieNueva.hidden = serie.value !== NUEVA;
            serieNueva.required = serie.value === NUEVA;
            conSerie.hidden = !serie.value;
        }

        var cat = categoriaElegida();
        var ser = serieElegida();
        if (recordar) recordar.hidden = !cat || !!(serie && serie.value);

        var partes = [];
        if (cat) partes.push('la categoría «' + cat + '»' + (categoria.value === NUEVA && !deLaSerie ? ' (nueva)' : ''));
        if (ser) {
            partes.push('la serie «' + ser + '»' + (serie.value === NUEVA ? ' (nueva)' : ''));
            partes.push(temporada.value ? 'temporada ' + temporada.value : 'cada capítulo en su temporada');
        }
        var algo = !!(cat || (serie && serie.value));
        resumen.textContent = algo ? 'Va a quedar en: ' + (partes.join(' › ') || '…') + '.' : '';
        boton.disabled = !algo;
    }

    categoria.addEventListener('change', function () {
        actualizar();
        if (categoria.value === NUEVA) categoriaNueva.focus();
    });
    categoriaNueva.addEventListener('input', actualizar);
    if (serie) {
        serie.addEventListener('change', function () {
            if (!categoriaDeLaSerie() && categoria.disabled) {
                // Dejó de ser una serie existente: la categoría se vuelve a elegir
                categoria.value = '';
                categoriaNueva.value = '';
            }
            actualizar();
            if (serie.value === NUEVA) serieNueva.focus();
        });
        serieNueva.addEventListener('input', actualizar);
        temporada.addEventListener('input', actualizar);
    }
    // La categoría deshabilitada no se manda: el servidor pone sola la de la serie
    actualizar();
})();
