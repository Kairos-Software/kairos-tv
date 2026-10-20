/*
 * Una lista importada sin recargar (canales/importacion.html; estilos en static/css/importacion_partes.css):
 *
 *   - Arriba («Estás trabajando con…»): Probar / Pausar / Cancelar y Cargar de lo elegido, de a tandas
 *     (tandas.js -> views.importacion_lote / importacion_cargar). Al terminar se redibuja lo que cambió.
 *   - Las categorías: el botón de cada fila hace su próximo paso (Probar -> Cargar) y la ✕ la descarta
 *     (views_importacion.partes, con «Deshacer»). Se tildan varias (Shift = un rango; con una búsqueda,
 *     «todas» son las que coinciden) y la barra de abajo las encola: «Probar y cargar», «Solo probar»,
 *     «Cargar lo que pasó» o «Descartar». Se hacen de a una; «Parar» corta la fila.
 *   - Uno por uno: «No cargar» / «Cargar igual» (de una o de las tildadas) redibujan solo esas filas.
 *
 * Todo con delegación (los pedazos con data-refrescar se reemplazan al traer la página de nuevo).
 * Usa KairosTrabajo.pedir / avisar (trabajo.js) y Tandas (tandas.js).
 */
(function () {
    'use strict';

    var raiz = document.querySelector('[data-importacion]');
    if (!raiz || !window.Tandas) return;

    var urls = {lote: raiz.dataset.urlLote, cargar: raiz.dataset.urlCargar, cancelar: raiz.dataset.urlCancelar,
                partes: raiz.dataset.urlPartes};
    var seleccion = {contenido: raiz.dataset.contenido || '', categoria: raiz.dataset.categoria || '',
                     q: raiz.dataset.q || ''};
    var trabajo = window.KairosTrabajo || {};
    var avisar = trabajo.avisar || function () {};
    var numero = window.Tandas.numero;

    function plural(n, uno, varios) { return numero(n) + ' ' + (n === 1 ? uno : varios); }

    // ── Traer la página de nuevo y cambiar solo los pedazos que cambian (data-refrescar) ──
    var refrescando = null;
    function refrescar() {
        if (refrescando) return refrescando;
        refrescando = fetch(window.location.href, {credentials: 'same-origin'})
            .then(function (respuesta) { return respuesta.text(); })
            .then(function (html) {
                var nueva = new DOMParser().parseFromString(html, 'text/html');
                document.querySelectorAll('[data-refrescar]').forEach(function (viejo) {
                    // Mientras la fila de categorías trabaja, sus filas no se tocan (son las que se van pintando)
                    if (viejo.id === 'imp-categorias-filas' && colaActiva()) return;
                    var reemplazo = viejo.id && nueva.getElementById(viejo.id);
                    if (reemplazo) viejo.replaceWith(document.importNode(reemplazo, true));
                });
                filtrarCategorias();
                document.querySelectorAll('[data-categorias], [data-entradas]').forEach(actualizarBarra);
                if (window.KairosDondeVa) window.KairosDondeVa();
            })
            .catch(function () { /* sin conexión: queda como estaba */ })
            .then(function () { refrescando = null; });
        return refrescando;
    }

    // ── Tildar filas (categorías y entradas): con delegación, porque las filas se redibujan ──
    function casillas(form) {
        return Array.prototype.filter.call(form.querySelectorAll('[data-elegir]'), function (c) {
            return !c.closest('tr[hidden], li[hidden]');
        });
    }
    function elegidas(form) { return casillas(form).filter(function (c) { return c.checked; }); }
    function actualizarBarra(form) {
        var todas = casillas(form);
        var tildadas = todas.filter(function (c) { return c.checked; }).length;
        var barra = form.querySelector('[data-barra-lote]');
        var cuantas = form.querySelector('[data-cuantas]');
        var todasCasilla = form.querySelector('[data-elegir-todas]');
        if (barra) barra.hidden = !tildadas;
        if (cuantas) cuantas.textContent = form.matches('[data-categorias]')
            ? plural(tildadas, 'categoría elegida', 'categorías elegidas')
            : plural(tildadas, 'elegida', 'elegidas');
        if (todasCasilla) {
            todasCasilla.checked = tildadas > 0 && tildadas === todas.length;
            todasCasilla.indeterminate = tildadas > 0 && tildadas < todas.length;
        }
    }
    function limpiar(form) {
        form.querySelectorAll('[data-elegir]').forEach(function (c) { c.checked = false; });
        actualizarBarra(form);
    }
    var ultimaTildada = null;
    document.addEventListener('click', function (evento) {
        var casilla = evento.target.closest('[data-elegir]');
        var form = casilla && casilla.closest('[data-categorias], [data-entradas]');
        if (!form) return;
        if (evento.shiftKey && ultimaTildada && form.contains(ultimaTildada)) {
            var lista = casillas(form);
            var desde = lista.indexOf(ultimaTildada);
            var hasta = lista.indexOf(casilla);
            if (desde >= 0 && hasta >= 0) {
                lista.slice(Math.min(desde, hasta), Math.max(desde, hasta) + 1).forEach(function (c) {
                    c.checked = casilla.checked;
                });
            }
        }
        ultimaTildada = casilla;
        actualizarBarra(form);
    });
    document.addEventListener('change', function (evento) {
        var todas = evento.target.closest('[data-elegir-todas]');
        var form = todas && todas.closest('[data-categorias], [data-entradas]');
        if (!form) return;
        casillas(form).forEach(function (c) { c.checked = todas.checked; });
        actualizarBarra(form);
    });
    document.addEventListener('click', function (evento) {
        var boton = evento.target.closest('[data-limpiar-seleccion]');
        var form = boton && boton.closest('[data-categorias], [data-entradas]');
        if (form) limpiar(form);
    });

    // ── Buscar una categoría (sin recargar) ──
    function filtrarCategorias() {
        var campo = document.querySelector('[data-filtrar-categorias]');
        var buscado = campo ? campo.value.trim().toLowerCase() : '';
        document.querySelectorAll('#imp-categorias-filas tr[data-fila]').forEach(function (fila) {
            fila.hidden = !!buscado && fila.dataset.nombre.indexOf(buscado) < 0;
        });
    }
    document.addEventListener('input', function (evento) {
        if (!evento.target.matches('[data-filtrar-categorias]')) return;
        filtrarCategorias();
        var form = evento.target.closest('[data-categorias]');
        if (form) actualizarBarra(form);
    });

    // ── Arriba: probar y cargar lo elegido («Estás trabajando con…») ──
    function caja() { return document.getElementById('trabajo'); }
    function estado(texto) {
        var lugar = caja() && caja().querySelector('[data-texto=estado]');
        if (lugar) lugar.textContent = texto;
    }
    function pintarArriba(parte) {
        var c = caja();
        if (!c) return;
        var relleno = c.querySelector('.avance-relleno');
        if (relleno) relleno.style.width = parte.porcentaje + '%';
        var barra = c.querySelector('.avance-barra');
        if (barra) barra.setAttribute('aria-valuenow', parte.porcentaje);
        var porcentaje = c.querySelector('[data-texto=porcentaje]');
        if (porcentaje) porcentaje.textContent = parte.porcentaje + ' % probado';
        var detalle = c.querySelector('[data-texto=detalle]');
        if (detalle) detalle.textContent = parte.pendientes ? 'faltan ' + numero(parte.pendientes) : 'listo';
        ['aptas', 'rechazadas', 'caidas', 'agregadas', 'descartadas', 'repetidas'].forEach(function (clave) {
            var contador = c.querySelector('[data-contador=' + clave + ']');
            if (!contador) return;
            contador.textContent = numero(parte[clave]);
            var enlace = contador.closest('[data-numero]');
            if (enlace) enlace.hidden = !parte[clave];
        });
    }
    function boton(accion) { return caja() && caja().querySelector('[data-accion=' + accion + ']'); }

    var prueba = null;
    var carga = null;
    function ocupado() {
        return (prueba && prueba.corriendo()) || (carga && carga.corriendo()) || colaActiva();
    }

    function probarArriba() {
        if (prueba && prueba.corriendo()) { prueba.pausar(); return; }
        if (colaActiva()) { avisar('Esperá a que terminen las categorías (o tocá «Parar»).', 'mal'); return; }
        prueba = prueba || window.Tandas({
            url: urls.lote,
            urlCancelar: urls.cancelar,
            datos: function () { return seleccion; },
            termino: function (r) { return r.terminada; },
            alAvanzar: function (r) {
                pintarArriba(r.en_la_seleccion);
                if (r.ocupada) estado('Otra pestaña está trabajando con esta lista: esperando…');
            },
            alTerminar: function (r) {
                prueba = null;
                var parte = r.en_la_seleccion;
                estado('');
                avisar('Terminó la prueba: ' + plural(parte.aptas, 'pasó', 'pasaron') + '.', 'bien');
                refrescar();
            },
            alCambiar: function (corriendo) {
                var probar = boton('correr');
                if (probar) {
                    probar.querySelector('span').textContent = corriendo ? 'Pausar' : 'Seguir probando';
                    probar.querySelector('i').className = corriendo ? 'bi bi-pause-fill' : 'bi bi-play-fill';
                    probar.classList.toggle('btn-primary', !corriendo);
                    probar.classList.toggle('btn-outline-secondary', corriendo);
                }
                var avance = caja() && caja().querySelector('.avance');
                if (avance) avance.classList.toggle('trabajando', corriendo);
                var cancelar = boton('cancelar-prueba');
                if (cancelar) cancelar.hidden = !corriendo;
                if (corriendo) estado('Probando… no hace falta quedarse mirando, pero no cierres esta página.');
                else if (prueba) estado('En pausa. Lo que ya se probó quedó guardado.');
            },
            alError: function (mensaje) { estado(mensaje); },
            alCancelar: function () { prueba = null; estado('Cancelado. Lo que ya se probó quedó guardado.'); refrescar(); },
        });
        prueba.empezar();
    }

    function cargarArriba() {
        if (ocupado()) { avisar('Esperá a que termine lo que está corriendo.', 'mal'); return; }
        var total = null;
        carga = window.Tandas({
            url: urls.cargar,
            urlCancelar: urls.cancelar,
            datos: function () { return seleccion; },
            termino: function (r) { return !r.en_la_seleccion.aptas || r.en_la_seleccion.pendientes > 0; },
            alAvanzar: function (r) {
                var parte = r.en_la_seleccion;
                if (total === null) total = parte.aptas + parte.agregadas;
                pintarArriba(parte);
                estado(r.ocupada ? 'Otra pestaña está trabajando con esta lista: esperando…'
                    : 'Cargando… ' + numero(parte.agregadas) + ' de ' + numero(total) + '. No cierres esta página.');
            },
            alTerminar: function (r) {
                carga = null;
                estado('');
                avisar('Listo: ' + plural(r.en_la_seleccion.agregadas, 'cargado', 'cargados') + '. Ya se ven en la app.', 'bien');
                refrescar();
            },
            alCambiar: function (corriendo) {
                var cargar = boton('cargar');
                if (cargar) cargar.disabled = corriendo;
                var cancelar = boton('cancelar-carga');
                if (cancelar) cancelar.hidden = !corriendo;
            },
            alError: function (mensaje) { estado(mensaje); },
            alCancelar: function () { carga = null; estado('Carga cancelada. Lo que ya se cargó quedó guardado.'); refrescar(); },
        });
        carga.empezar();
    }

    document.addEventListener('click', function (evento) {
        var b = evento.target.closest('[data-accion]');
        if (!b || !raiz.contains(b) || b.disabled) return;
        if (b.dataset.accion === 'correr') probarArriba();
        else if (b.dataset.accion === 'cancelar-prueba' && prueba) { prueba.cancelar(); estado('Cancelando…'); }
        else if (b.dataset.accion === 'cargar') cargarArriba();
        else if (b.dataset.accion === 'cancelar-carga' && carga) { carga.cancelar(); estado('Cancelando…'); }
    });

    // ── Las categorías: cada fila con su barrita y su próximo paso ──
    function filaDe(contenido, categoria) {
        return Array.prototype.find.call(document.querySelectorAll('#imp-categorias-filas tr[data-fila]'), function (f) {
            return f.dataset.contenido === contenido && f.dataset.categoria === categoria;
        });
    }
    function nombreDe(fila) {
        var enlace = fila.querySelector('.imp-fila-nombre a');
        return enlace ? enlace.textContent.trim() : fila.dataset.categoria;
    }
    // La misma barrita y el mismo texto que canales/_importacion_cuentas.html
    function barraDe(c) {
        return '<span class="imp-barra" aria-hidden="true">' +
            [['b-cargados', c.agregadas], ['b-pasaron', c.aptas], ['b-fallaron', c.no_pasaron],
             ['b-descartados', c.descartadas], ['b-estaban', c.repetidas], ['b-falta', c.pendientes]]
                .map(function (p) { return '<span class="' + p[0] + '" style="flex-grow: ' + (p[1] || 0) + '"></span>'; })
                .join('') + '</span>';
    }
    function textoDe(c) {
        return '<span class="imp-cuentas">' +
            [['', c.pendientes, ' sin probar'], ['c-pasaron', c.aptas, ' pasaron'], ['c-cargados', c.agregadas, ' cargados'],
             ['c-fallaron', c.no_pasaron, ' no pasaron'], ['', c.descartadas, ' descartados'], ['', c.repetidas, ' ya estaban']]
                .filter(function (p) { return p[1]; })
                .map(function (p) { return '<span' + (p[0] ? ' class="' + p[0] + '"' : '') + '>' + numero(p[1]) + p[2] + '</span>'; })
                .join('') + '</span>';
    }
    function cuentasDe(fila) {
        try { return JSON.parse(fila.dataset.cuentas || 'null'); } catch (_) { return null; }
    }
    function pintarFila(fila, c) {
        if (!fila || !c) return;
        fila.dataset.cuentas = JSON.stringify(c);
        var como = fila.querySelector('[data-como]');
        var aviso = como.querySelector('[data-fila-estado]');
        como.innerHTML = barraDe(c) + textoDe(c);
        if (aviso) como.appendChild(aviso);
        var acciones = fila.querySelector('[data-acciones]');
        if (!acciones) return;
        var nombre = nombreDe(fila).replace(/"/g, '&quot;');
        var html = '';
        if (c.pendientes) html = '<button type="button" class="btn btn-sm btn-outline-secondary" data-fila-accion="probar"><i class="bi bi-play-fill" aria-hidden="true"></i> Probar</button>';
        else if (c.aptas) html = '<button type="button" class="btn btn-sm btn-primary" data-fila-accion="cargar"><i class="bi bi-cloud-arrow-up" aria-hidden="true"></i> Cargar ' + numero(c.aptas) + '</button>';
        else if (c.agregadas) html = '<span class="imp-fila-hecho"><i class="bi bi-check-circle-fill" aria-hidden="true"></i> Cargada</span>';
        if (c.pendientes || c.aptas) html += '<button type="button" class="btn-icono btn-icono-peligro" data-fila-accion="descartar" title="Descartar: no se prueba ni se carga" aria-label="Descartar ' + nombre + '"><i class="bi bi-x-lg" aria-hidden="true"></i></button>';
        else if (c.descartadas) html += '<button type="button" class="btn-icono" data-fila-accion="recuperar" title="Volver a traer lo que se descartó" aria-label="Recuperar ' + nombre + '"><i class="bi bi-arrow-counterclockwise" aria-hidden="true"></i></button>';
        acciones.innerHTML = html;
    }
    function marcar(fila, texto, clase) {
        var como = fila.querySelector('[data-como]');
        var aviso = como.querySelector('[data-fila-estado]');
        if (!texto) {
            if (aviso) aviso.remove();
            fila.classList.remove('en-cola', 'trabajando', 'con-error');
            return;
        }
        if (!aviso) {
            aviso = document.createElement('span');
            aviso.className = 'imp-fila-estado';
            aviso.setAttribute('data-fila-estado', '');
            como.appendChild(aviso);
        }
        aviso.textContent = texto;
        fila.classList.remove('en-cola', 'trabajando', 'con-error');
        if (clase) fila.classList.add(clase);
    }

    // Descartar (o «Deshacer»: recuperar) varias categorías de una
    function partes(filas, accion) {
        var datos = new FormData();
        datos.append('accion', accion);
        filas.forEach(function (fila) {
            datos.append('contenido', fila.dataset.contenido);
            datos.append('categoria', fila.dataset.categoria);
        });
        return trabajo.pedir(urls.partes, datos).then(function (r) {
            r.filas.forEach(function (d) { pintarFila(filaDe(d.contenido, d.categoria), d.cuentas); });
            var deshacer = accion === 'descartar' && r.cantidad ? function () { partes(filas, 'recuperar'); } : null;
            avisar(r.mensaje, r.cantidad ? 'bien' : 'info', deshacer);
            if (r.cantidad) refrescar();
        }).catch(function (error) { avisar(error.message, 'mal'); });
    }

    // La fila de trabajo: una categoría por vez (el servidor procesa una lista por vez)
    var cola = [];
    var actual = null;
    var hechas = {categorias: 0, pasaron: 0, cargados: 0};
    function colaActiva() { return !!actual || cola.length > 0; }
    function textoDeLaCola() {
        var aviso = document.querySelector('[data-cola]');
        if (!aviso) return;
        aviso.hidden = !colaActiva();
        if (!actual) return;
        var quedan = cola.length;
        aviso.querySelector('[data-cola-texto]').textContent = (actual.fase === 'cargar' ? 'Cargando' : 'Probando') +
            ' «' + nombreDe(actual.fila) + '»' + (quedan ? ' · quedan ' + plural(quedan, 'categoría', 'categorías') : '') +
            '. Podés seguir mirando, pero no cierres la página.';
    }
    function encolar(filas, modo) {
        if ((prueba && prueba.corriendo()) || (carga && carga.corriendo())) {
            avisar('Esperá a que termine lo de arriba (o pausalo).', 'mal');
            return;
        }
        var nuevas = 0;
        filas.forEach(function (fila) {
            var ya = (actual && actual.fila === fila) || cola.some(function (i) { return i.fila === fila; });
            if (ya) return;
            cola.push({fila: fila, modo: modo});
            marcar(fila, 'En espera…', 'en-cola');
            nuevas++;
        });
        if (!nuevas) return;
        textoDeLaCola();
        siguiente();
    }
    function siguiente() {
        if (actual) return;
        var item = cola.shift();
        if (!item) { terminarCola(); return; }
        var c = cuentasDe(item.fila);   // sin números: se prueba y el servidor dice
        if (item.modo === 'cargar' && c && c.pendientes) {
            marcar(item.fila, 'Falta probarla: usá «Probar y cargar».', 'con-error');
            siguiente();
        } else if (item.modo !== 'cargar' && (!c || c.pendientes)) correrFila(item, 'probar');
        else if (item.modo !== 'probar' && (!c || c.aptas)) correrFila(item, 'cargar');
        else { marcar(item.fila, ''); siguiente(); }
    }
    function correrFila(item, fase) {
        actual = item;
        item.fase = fase;
        var datos = {contenido: item.fila.dataset.contenido, categoria: item.fila.dataset.categoria, q: ''};
        var anterior = null;
        var sinAvanzar = false;
        var antes = cuentasDe(item.fila) || {aptas: 0, agregadas: 0};
        marcar(item.fila, fase === 'probar' ? 'Probando…' : 'Cargando…', 'trabajando');
        textoDeLaCola();
        item.tarea = window.Tandas({
            url: fase === 'probar' ? urls.lote : urls.cargar,
            urlCancelar: urls.cancelar,
            datos: function () { return datos; },
            termino: function (r) {
                var parte = r.en_la_seleccion;
                if (fase === 'probar') return r.terminada;
                if (!parte.aptas || parte.pendientes > 0) return true;
                // Algo del servidor no deja cargar (falta probar otra parte de una serie de YouTube): no insistir
                if (!r.ocupada && anterior === parte.aptas) { sinAvanzar = true; return true; }
                anterior = parte.aptas;
                return false;
            },
            alAvanzar: function (r) {
                var parte = r.en_la_seleccion;
                pintarFila(item.fila, parte);
                if (r.ocupada) marcar(item.fila, 'Esperando: otra pestaña está trabajando con esta lista…', 'trabajando');
                else if (fase === 'probar') marcar(item.fila, 'Probando… ' + parte.porcentaje + ' %', 'trabajando');
                else marcar(item.fila, 'Cargando… faltan ' + numero(parte.aptas), 'trabajando');
            },
            alTerminar: function (r) {
                var parte = r.en_la_seleccion;
                actual = null;
                if (fase === 'probar') {
                    hechas.pasaron += Math.max(0, parte.aptas - (antes.aptas || 0));
                    if (item.modo === 'probar-cargar' && parte.aptas) { correrFila(item, 'cargar'); return; }
                } else {
                    hechas.cargados += Math.max(0, parte.agregadas - (antes.agregadas || 0));
                }
                hechas.categorias++;
                marcar(item.fila, sinAvanzar ? 'No se pudo cargar: primero terminá de probar toda la lista.' : '',
                       sinAvanzar ? 'con-error' : '');
                siguiente();
            },
            alError: function (mensaje) {
                marcar(item.fila, mensaje, 'con-error');
                actual = null;
                pararCola(true);
                avisar(mensaje, 'mal');
            },
        });
        item.tarea.empezar();
    }
    function pararCola(sinCancelar) {
        cola.forEach(function (i) { marcar(i.fila, ''); });
        cola = [];
        if (actual) {
            var item = actual;
            actual = null;
            if (!sinCancelar) item.tarea.cancelar();
            marcar(item.fila, 'Parado. Lo que ya se hizo quedó guardado.');
        }
        textoDeLaCola();
        refrescar();
    }
    function terminarCola() {
        textoDeLaCola();
        if (!hechas.categorias) return;
        var partesDelAviso = [plural(hechas.categorias, 'categoría lista', 'categorías listas')];
        if (hechas.pasaron) partesDelAviso.push(plural(hechas.pasaron, 'pasó la prueba', 'pasaron la prueba'));
        if (hechas.cargados) partesDelAviso.push(plural(hechas.cargados, 'cargado', 'cargados'));
        avisar('Listo: ' + partesDelAviso.join(' · ') + '.', 'bien');
        hechas = {categorias: 0, pasaron: 0, cargados: 0};
        refrescar();
    }

    document.addEventListener('click', function (evento) {
        var b = evento.target.closest('[data-fila-accion]');
        if (b) {
            var fila = b.closest('tr[data-fila]');
            if (!fila) return;
            var accion = b.dataset.filaAccion;
            if (accion === 'descartar' || accion === 'recuperar') partes([fila], accion);
            else encolar([fila], accion);
            return;
        }
        var lote = evento.target.closest('[data-lote-accion]');
        if (lote) {
            var form = lote.closest('[data-categorias]');
            var filas = elegidas(form).map(function (c) { return c.closest('tr[data-fila]'); });
            if (!filas.length) return;
            if (lote.dataset.loteAccion === 'descartar') partes(filas, 'descartar');
            else encolar(filas, lote.dataset.loteAccion);
            limpiar(form);
            return;
        }
        if (evento.target.closest('[data-parar-cola]')) pararCola();
    });

    // ── Uno por uno: «No cargar» / «Cargar igual» sin recargar ──
    document.addEventListener('submit', function (evento) {
        var form = evento.target;
        if (!form.matches('[data-entradas]') || evento.defaultPrevented || !trabajo.pedir) return;
        evento.preventDefault();
        var datos = new FormData(form);
        var quien = evento.submitter;
        if (quien && quien.name) datos.append(quien.name, quien.value);
        if (quien) quien.disabled = true;
        trabajo.pedir(form.action, datos).then(function (r) {
            Object.keys(r.filas).forEach(function (pk) {
                var vieja = form.querySelector('[data-entrada="' + pk + '"]');
                if (!vieja) return;
                var molde = document.createElement('template');
                molde.innerHTML = r.filas[pk].trim();
                var nueva = molde.content.firstElementChild;
                nueva.classList.add('recien-cambiada');
                vieja.replaceWith(nueva);
            });
            avisar(r.mensaje, r.cantidad ? 'bien' : 'info');
            limpiar(form);
            // Los números de arriba y de las pestañas
            if (r.cantidad) refrescarSinLista();
        }).catch(function (error) {
            avisar(error.message, 'mal');
        }).then(function () { if (quien) quien.disabled = false; });
    });
    // Después de cambiar entradas, la lista se queda como está (se ve lo que se hizo y se puede volver atrás)
    function refrescarSinLista() {
        var lista = document.getElementById('lista-entradas');
        if (lista) lista.removeAttribute('data-refrescar');
        refrescar().then(function () { if (lista) lista.setAttribute('data-refrescar', ''); });
    }

    // Recién llegada de subir una lista: arranca a probar sola
    if (raiz.hasAttribute('data-empezar') && boton('correr')) probarArriba();
})();
