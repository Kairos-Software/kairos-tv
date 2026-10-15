/*
 * Contenido → Mantenimiento del catálogo (canales/inicio.html).
 *
 *   - "Qué revisar": todo, una sección (En vivo, Películas, Series...) o lo
 *     que vino de una lista o link importado. Vale para "Verificar" y para
 *     "Limpiar nombres".
 *   - "Verificar": prueba las señales de a tandas (tandas.js →
 *     /canales/verificar/lote/) y, al terminar, muestra el resultado en la
 *     misma página: cuántas andan, cuántas están caídas, y los nombres de lo
 *     que SE CAYÓ y lo que VOLVIÓ (cada uno lleva a su página).
 *
 * Necesita en la página: #revisar-seccion, #revisar-origen, el botón
 * [data-accion=verificar], .avance, #resultado-verificacion y
 * #form-limpiar-nombres. Las direcciones vienen en el <script>:
 * data-url-lote y data-url-canal (con 0 en lugar del número).
 */
(function () {
    'use strict';

    var script = document.currentScript;
    var caja = document.getElementById('verificar-todas');
    if (!caja || !window.Tandas) return;
    var urlCanal = (script && script.dataset.urlCanal) || '/canales/canal/0/editar/';
    var seccion = document.getElementById('revisar-seccion');
    var origen = document.getElementById('revisar-origen');
    var boton = caja.querySelector('[data-accion=verificar]');
    var avance = caja.querySelector('.avance');
    var barra = caja.querySelector('.avance-barra');
    var relleno = caja.querySelector('.avance-relleno');
    var porcentaje = caja.querySelector('[data-texto=porcentaje]');
    var detalle = caja.querySelector('[data-texto=detalle]');
    var resultado = document.getElementById('resultado-verificacion');
    var MAXIMO_NOMBRES = 500;

    var desde, suma, listas, total;
    function empezarDeCero() {
        desde = 0;
        total = 0;
        suma = {funcionan: 0, caidas: 0, sin_verificar: 0, revividas: 0, nuevas_caidas: 0};
        listas = {se_cayeron: [], volvieron: []};
    }
    empezarDeCero();

    /** "todas las señales" / "las señales de Series que vinieron de «lista.m3u»" */
    function queSeRevisa(palabra) {
        var texto = (seccion.value || origen.value) ? 'las ' + palabra : 'todas las ' + palabra;
        if (seccion.value) texto += ' de ' + seccion.options[seccion.selectedIndex].text.replace(/^Solo /, '');
        if (origen.value) texto += ' que vinieron de «' + origen.value + '»';
        return texto;
    }

    function texto(etiqueta) {
        boton.querySelector('span').textContent = etiqueta;
    }

    function pintarResultado() {
        var resumen = resultado.querySelector('[data-resultado-resumen]');
        resumen.textContent = 'Se revisaron ' + queSeRevisa('señales') + ' (' + Tandas.numero(total) + '): andan '
            + Tandas.numero(suma.funcionan) + ', caídas ' + Tandas.numero(suma.caidas)
            + (suma.sin_verificar ? ', sin poder probar ' + Tandas.numero(suma.sin_verificar) : '')
            + '. Se cayeron ahora: ' + Tandas.numero(suma.nuevas_caidas)
            + '. Volvieron: ' + Tandas.numero(suma.revividas) + '.';
        [['se_cayeron', 'Se cayeron ahora', suma.nuevas_caidas], ['volvieron', 'Volvieron', suma.revividas]]
            .forEach(function (parte) {
                var bloque = resultado.querySelector('[data-resultado="' + parte[0] + '"]');
                var lista = bloque.querySelector('ul');
                bloque.hidden = !parte[2];
                bloque.querySelector('summary').textContent = parte[1] + ' (' + Tandas.numero(parte[2]) + ')';
                lista.textContent = '';
                listas[parte[0]].forEach(function (item) {
                    var li = document.createElement('li');
                    var enlace = document.createElement('a');
                    enlace.href = urlCanal.replace('/0/', '/' + item.pk + '/');
                    enlace.textContent = item.canal;
                    li.appendChild(enlace);
                    if (item.error) li.appendChild(document.createTextNode(' — ' + item.error));
                    lista.appendChild(li);
                });
                if (parte[2] > listas[parte[0]].length) {
                    var mas = document.createElement('li');
                    mas.className = 'texto-suave';
                    mas.textContent = 'Y ' + Tandas.numero(parte[2] - listas[parte[0]].length) + ' más.';
                    lista.appendChild(mas);
                }
            });
        // "Ver en Organizar": con la misma sección y lista elegidas
        var parametros = new URLSearchParams({mostrar: 'caidos'});
        if (seccion.value) parametros.set('contenido', seccion.value);
        if (origen.value) parametros.set('origen', origen.value);
        var organizar = resultado.querySelector('[data-resultado-organizar]');
        organizar.href = organizar.href.split('?')[0] + '?' + parametros.toString();
        resultado.hidden = false;
        resultado.scrollIntoView({behavior: 'smooth', block: 'nearest'});
    }

    var tarea = Tandas({
        url: (script && script.dataset.urlLote) || '/canales/verificar/lote/',
        datos: function () { return {desde: desde, seccion: seccion.value, origen: origen.value}; },
        termino: function (r) { return r.terminado; },
        alAvanzar: function (r) {
            if (r.ocupada) {
                detalle.textContent = 'Esperando: ' + (r.esperando || 'otra tarea pesada') + '…';
                return;
            }
            desde = r.siguiente;
            total = r.total;
            Object.keys(suma).forEach(function (clave) { suma[clave] += r[clave] || 0; });
            ['se_cayeron', 'volvieron'].forEach(function (clave) {
                (r[clave] || []).forEach(function (item) {
                    if (listas[clave].length < MAXIMO_NOMBRES) listas[clave].push(item);
                });
            });
            relleno.style.width = r.porcentaje + '%';
            barra.setAttribute('aria-valuenow', r.porcentaje);
            porcentaje.textContent = r.porcentaje + ' % completado';
            detalle.textContent = Tandas.numero(r.verificadas) + ' de ' + Tandas.numero(r.total) + ' señales · andan '
                + Tandas.numero(suma.funcionan) + ' · caídas ' + Tandas.numero(suma.caidas)
                + ' · se cayeron ' + Tandas.numero(suma.nuevas_caidas) + ' · volvieron ' + Tandas.numero(suma.revividas);
        },
        alTerminar: function () {
            pintarResultado();
            empezarDeCero();
            texto('Verificar de nuevo');
            seccion.disabled = origen.disabled = false;
        },
        alCambiar: function (corriendo) {
            avance.hidden = false;
            avance.classList.toggle('trabajando', corriendo);
            texto(corriendo ? 'Pausar' : (desde ? 'Continuar' : 'Verificar'));
            // Mientras hay una verificación a medias, no se cambia qué se revisa
            seccion.disabled = origen.disabled = corriendo || desde > 0;
        },
        alError: function (mensaje) { detalle.textContent = mensaje; },
    });
    boton.addEventListener('click', function () {
        if (tarea.corriendo()) {
            tarea.pausar();
            return;
        }
        if (!desde) {
            resultado.hidden = true;
            porcentaje.textContent = '0 %';
            detalle.textContent = 'Verificando ' + queSeRevisa('señales') + '…';
        }
        tarea.empezar();
    });

    // "Limpiar nombres" con lo elegido en "Qué revisar"
    var limpiar = document.getElementById('form-limpiar-nombres');
    if (limpiar) {
        limpiar.addEventListener('submit', function (evento) {
            var pregunta = '¿Limpiar los nombres de ' + queSeRevisa('canales').replace(/^(todas )?las /, function (m) {
                return m.indexOf('todas') === 0 ? 'todos los ' : 'los ';
            }) + '? Ej: «ES: (FHD) DAZN 1» pasa a «DAZN 1». Si dos quedan iguales, se juntan en uno (con las señales de los dos).';
            if (!window.confirm(pregunta)) {
                evento.preventDefault();
                return;
            }
            limpiar.elements.seccion.value = seccion.value;
            limpiar.elements.origen.value = origen.value;
        });
    }
})();
