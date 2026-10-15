/*
 * Organizar contenido: el panel de DETALLES (canales/organizar.html).
 *
 * Al elegir una tarjeta (tildarla) se abre al costado con TODO lo que se sabe
 * de ella: si se ve en la app (y si no, por qué), sus datos (sección,
 * categoría, idioma, quién la cargó y cuándo...) y cada señal en el orden en
 * que la prueba la app: de qué lista o link salió, el link completo (para
 * copiar), formato, estado, calidad, error, cómo anda en los aparatos y si
 * está oculta. Cada señal tiene "Borrar esta señal" (borra solo esa).
 * Muestra la última tarjeta que se tocó; los datos salen del data-datos del
 * botón Editar de la tarjeta (los arma views._preparar_para_editar).
 *
 * window.KairosSenales.pintar(lista, datos) dibuja las señales: lo usa también
 * el cuadro de edición rápida.
 */
(function () {
    'use strict';

    var formBorrar = document.getElementById('form-borrar-senal');

    function crear(etiqueta, clase, texto) {
        var elemento = document.createElement(etiqueta);
        if (clase) elemento.className = clase;
        if (texto) elemento.textContent = texto;
        return elemento;
    }

    function borrar(senal, datos) {
        var unica = datos.fuentes.length === 1;
        var pregunta = '¿Borrar la señal ' + senal.orden + ' (' + senal.origen + ') de «' + datos.nombre + '»?\n\n' +
            (unica ? 'Es su ÚNICA señal: no se va a ver en la app hasta que le agregues otra.'
                   : 'Las otras ' + (datos.fuentes.length - 1) + ' quedan como están.');
        if (!window.confirm(pregunta)) return;
        formBorrar.action = formBorrar.dataset.url.replace('/0/', '/' + senal.id + '/');
        formBorrar.submit();
    }

    function copiar(boton, texto) {
        var listo = function () {
            boton.textContent = 'Copiado';
            window.setTimeout(function () { boton.textContent = 'Copiar link'; }, 1500);
        };
        if (navigator.clipboard) navigator.clipboard.writeText(texto).then(listo, function () {});
    }

    /** Las señales de `datos` en la lista `lista` (un <ul>), en el orden en que las prueba la app. */
    function pintar(lista, datos) {
        lista.textContent = '';
        if (!datos.fuentes.length) {
            lista.appendChild(crear('li', 'senal', 'No tiene señales cargadas: no se puede ver en la app.'));
            return;
        }
        datos.fuentes.forEach(function (f) {
            var li = crear('li', 'senal' + (f.caida || f.oculta || !f.activa ? ' senal-mal' : ''));
            var cabeza = crear('div', 'senal-cabeza');
            if (f.orden) cabeza.appendChild(crear('span', 'senal-numero', String(f.orden)));
            var origen = crear(f.importacion ? 'a' : 'strong', 'senal-origen', f.origen);
            if (f.importacion) { origen.href = f.importacion; origen.title = 'Ver esa importación (de qué lista salió)'; }
            cabeza.appendChild(origen);
            if (f.estado) {
                cabeza.appendChild(crear('span', 'senal-estado' + (f.caida ? ' estado-mal' : ''),
                    f.estado + (f.activa ? '' : ' · apagada a mano')));
            }
            li.appendChild(cabeza);
            var tecnico = [f.tipo, f.calidad, f.codec && !f.calidad ? 'códec ' + f.codec : ''].filter(Boolean).join(' · ');
            if (tecnico) li.appendChild(crear('div', 'senal-dato', tecnico));
            if (f.error) li.appendChild(crear('div', 'senal-dato estado-mal', 'Error: ' + f.error));
            if (f.probada) li.appendChild(crear('div', 'senal-dato', 'Probada por el servidor el ' + f.probada));
            if (f.aparatos) li.appendChild(crear('div', 'senal-dato', 'En los aparatos: ' + f.aparatos));
            if (f.oculta) li.appendChild(crear('div', 'senal-dato estado-mal', f.oculta));
            if (f.aviso_codec) li.appendChild(crear('div', 'senal-dato senal-aviso', f.aviso_codec));
            if (f.url) {
                var enlace = crear('a', 'direccion', f.url);
                enlace.href = f.url;
                enlace.target = '_blank';
                enlace.rel = 'noopener noreferrer';
                li.appendChild(enlace);
            }
            var botones = crear('div', 'senal-botones');
            if (f.url && navigator.clipboard) {
                var botonCopiar = crear('button', 'btn btn-sm btn-outline-secondary', 'Copiar link');
                botonCopiar.type = 'button';
                botonCopiar.addEventListener('click', function () { copiar(botonCopiar, f.url); });
                botones.appendChild(botonCopiar);
            }
            if (formBorrar && f.borrable && f.id) {
                var botonBorrar = crear('button', 'btn btn-sm btn-outline-secondary text-danger');
                botonBorrar.type = 'button';
                botonBorrar.innerHTML = '<i class="bi bi-trash" aria-hidden="true"></i> Borrar esta señal';
                botonBorrar.addEventListener('click', function () { borrar(f, datos); });
                botones.appendChild(botonBorrar);
            }
            if (botones.children.length) li.appendChild(botones);
            lista.appendChild(li);
        });
    }

    window.KairosSenales = {pintar: pintar};

    // ── El panel de al lado ──
    var panel = document.getElementById('detalle-lateral');
    if (!panel) return;
    var tarjetas = Array.prototype.slice.call(document.querySelectorAll('.espejo-tarjeta'));
    var mostrada = null;
    var tocadas = [];   // las tildadas, la última al final

    function datosDe(tarjeta) {
        var boton = tarjeta.querySelector('.espejo-editar');
        try { return JSON.parse(boton.dataset.datos); } catch (e) { return null; }
    }

    function mostrar(tarjeta) {
        var datos = datosDe(tarjeta);
        if (!datos) return;
        if (mostrada) mostrada.classList.remove('detalle-actual');
        mostrada = tarjeta;
        tarjeta.classList.add('detalle-actual');
        var esSerie = datos.tipo === 'serie';

        var imagen = panel.querySelector('[data-detalle-imagen]');
        imagen.textContent = '';
        imagen.classList.toggle('poster', panel.dataset.forma !== 'vivo' || esSerie);
        // El que ve la app: la copia pareja del logo (o nada, si está roto); el original queda para Editar
        var logo = 'logo_ver' in datos ? datos.logo_ver : datos.logo;
        if (logo) {
            var img = crear('img');
            img.alt = '';
            img.referrerPolicy = 'no-referrer';
            img.src = logo;
            imagen.appendChild(img);
        }
        panel.querySelector('[data-detalle-nombre]').textContent = (datos.destacado ? '★ ' : '') + datos.nombre;
        var estado = panel.querySelector('[data-detalle-estado]');
        estado.textContent = datos.en_app ? 'Se ve en la app.' : 'No se ve en la app: ' + (datos.motivo || '');
        estado.className = 'small mb-0 ' + (datos.en_app ? 'estado-bien' : 'estado-mal');

        var filas = panel.querySelector('[data-detalle-datos]');
        filas.textContent = '';
        (datos.datos || []).forEach(function (fila) {
            filas.appendChild(crear('dt', '', fila[0]));
            filas.appendChild(crear('dd', '', fila[1]));
        });
        if (datos.destacado) {
            filas.appendChild(crear('dt', '', 'Destacado en la TV'));
            filas.appendChild(crear('dd', '', 'Sí: sale más seguido en el modo reposo'));
        }

        panel.querySelector('[data-detalle-cuantas]').textContent = datos.fuentes.length;
        panel.querySelector('[data-detalle-ayuda]').textContent = esSerie
            ? 'Una por cada lista o canal de donde salieron sus capítulos. Para ver o borrar las de un capítulo, entrá a «Ver y ordenar capítulos».'
            : 'La app prueba la 1 y, si no anda, pasa a la siguiente. Si una no funciona, borrala: las otras quedan.';
        pintar(panel.querySelector('[data-detalle-senales]'), datos);

        var mas = panel.querySelector('[data-detalle-mas]');
        mas.href = datos.mas;
        mas.textContent = esSerie ? 'Ver y ordenar capítulos' : 'Más opciones';
        var otras = tocadas.length - 1;
        var aviso = panel.querySelector('[data-detalle-varios]');
        aviso.hidden = otras < 1;
        aviso.textContent = 'Tenés ' + tocadas.length + ' elegidos: acá ves el último que tocaste.';
        panel.hidden = false;
        panel.querySelector('.detalle-lateral-cuerpo').scrollTop = 0;
    }

    function cerrar() {
        panel.hidden = true;
        if (mostrada) mostrada.classList.remove('detalle-actual');
        mostrada = null;
    }

    tarjetas.forEach(function (tarjeta) {
        var casilla = tarjeta.querySelector('.canal-elegir');
        if (!casilla) return;
        casilla.addEventListener('change', function () {
            tocadas = tocadas.filter(function (t) { return t !== tarjeta; });
            if (casilla.checked) {
                tocadas.push(tarjeta);
                mostrar(tarjeta);
            } else if (mostrada === tarjeta) {
                // Se destildó la que se veía: la anterior que siga elegida, o se cierra
                if (tocadas.length) mostrar(tocadas[tocadas.length - 1]);
                else cerrar();
            }
        });
    });
    // "Toda la página" o "Cancelar selección": no se abre el panel con cada una
    ['elegir-todos', 'limpiar-seleccion'].forEach(function (id) {
        var control = document.getElementById(id);
        if (!control) return;
        control.addEventListener('click', function () {
            window.setTimeout(function () {
                tocadas = tarjetas.filter(function (t) {
                    var c = t.querySelector('.canal-elegir');
                    return c && c.checked;
                });
                if (!tocadas.length) cerrar();
            }, 0);
        });
    });

    panel.querySelector('[data-detalle-cerrar]').addEventListener('click', cerrar);
    document.addEventListener('keydown', function (evento) {
        if (evento.key === 'Escape' && !panel.hidden && !document.querySelector('dialog[open]')) cerrar();
    });
    panel.querySelector('[data-detalle-editar]').addEventListener('click', function () {
        if (mostrada) mostrada.querySelector('.espejo-editar').click();
    });

    // Volviendo de borrar una señal: el panel de ese canal, abierto (#ver-<id>)
    var pedido = /^#ver-(\d+)$/.exec(window.location.hash);
    if (pedido) {
        var tarjeta = tarjetas.filter(function (t) {
            var datos = datosDe(t);
            return datos && String(datos.pk) === pedido[1];
        })[0];
        if (tarjeta) {
            mostrar(tarjeta);
            tarjeta.scrollIntoView({block: 'center'});
        }
        history.replaceState(null, '', window.location.pathname + window.location.search);
    }
})();
