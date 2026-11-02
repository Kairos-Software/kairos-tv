/*
 * Organizar contenido: las SEÑALES de una tarjeta (canales/organizar.html).
 *
 * window.KairosSenales.pintar(lista, datos) dibuja cada señal en el orden en
 * que la prueba la app: de qué lista o link salió, el link completo (para
 * copiar), formato, estado, calidad, error, cómo anda en los aparatos, si
 * está oculta y su salud (cómo anduvo en sus últimas pruebas: canales/salud.py),
 * con sus botones: "Probar ahora", "Quitar esta señal" o "Volver a mostrar esta
 * señal" (aunque el canal se vea con las otras) y "Borrar esta señal" (solo esa).
 * Lo usa el panel de edición (organizar_trabajo.js); los datos salen del
 * data-datos de la tarjeta (los arma views._preparar_para_editar). Esos botones
 * recargan la página y el panel se vuelve a abrir en la misma (?abrir=).
 * Quien edita, en un canal, cambia ahí mismo el número de cada señal (`numero-<id>`):
 * se guarda con el «Guardar» del panel y la señal va a ese lugar.
 * (El panel viejo de Detalles quedó dentro del de edición: si no está, no hace nada.)
 */
(function () {
    'use strict';

    var formBorrar = document.getElementById('form-borrar-senal');
    var formAccion = document.getElementById('form-accion-senal');

    function crear(etiqueta, clase, texto) {
        var elemento = document.createElement(etiqueta);
        if (clase) elemento.className = clase;
        if (texto) elemento.textContent = texto;
        return elemento;
    }

    /** Al volver de la acción, el panel de esta misma tarjeta abierto (organizar_trabajo.js lee ?abrir=). */
    function volverAbierto(formulario, datos) {
        var url = new URL(window.location.href);
        url.searchParams.delete('ir');
        url.searchParams.set('abrir', datos.tipo === 'serie' ? 's:' + datos.nombre : 'c' + datos.pk);
        formulario.elements.volver.value = url.pathname + url.search;
    }

    /** Estos botones recargan la página: si el panel tiene cambios sin guardar, se pregunta antes. */
    function seguirSinGuardar() {
        var editor = window.KairosEditor;
        return !editor || !editor.sucio() ||
            window.confirm('Hay cambios sin guardar en el panel (números, fuentes nuevas, datos…). Si seguís, se pierden.');
    }

    function borrar(senal, datos) {
        if (!seguirSinGuardar()) return;
        var unica = datos.fuentes.length === 1;
        var pregunta = '¿Borrar la señal ' + senal.orden + ' (' + senal.origen + ') de «' + datos.nombre + '»?\n\n' +
            (unica ? 'Es su ÚNICA señal: no se va a ver en la app hasta que le agregues otra.'
                   : 'Las otras ' + (datos.fuentes.length - 1) + ' quedan como están.');
        if (!window.confirm(pregunta)) return;
        formBorrar.action = formBorrar.dataset.url.replace('/0/', '/' + senal.id + '/');
        volverAbierto(formBorrar, datos);
        formBorrar.submit();
    }

    /** Quitar, volver a mostrar o probar ahora UNA señal (canales/views_revisar.fuente_accion). */
    function accion(senal, datos, cual) {
        if (!seguirSinGuardar()) return;
        if (cual === 'quitar' && !window.confirm('¿Quitar la señal ' + senal.orden + ' (' + senal.origen + ') de «' +
                datos.nombre + '»?\n\nLa app deja de usarla. No se borra: «Volver a mostrar esta señal» la devuelve.')) {
            return;
        }
        formAccion.action = formAccion.dataset.url.replace('/0/', '/' + senal.id + '/');
        formAccion.elements.accion.value = cual;
        volverAbierto(formAccion, datos);
        formAccion.submit();
    }

    function botonDeAccion(texto, icono, clase, alTocar) {
        var boton = crear('button', 'btn btn-sm btn-outline-secondary' + (clase ? ' ' + clase : ''));
        boton.type = 'button';
        boton.innerHTML = '<i class="bi ' + icono + '" aria-hidden="true"></i> ';
        boton.appendChild(document.createTextNode(texto));
        boton.addEventListener('click', alTocar);
        return boton;
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
            // Quien edita cambia el número ahí mismo: al guardar, la señal va a ese lugar (views.organizar_editar)
            if (formAccion && f.borrable && f.id && datos.tipo !== 'serie') {
                var numero = crear('input', 'form-control form-control-sm senal-orden');
                numero.type = 'number';
                numero.min = 1;
                numero.name = 'numero-' + f.id;
                numero.value = f.orden;
                numero.setAttribute('aria-label', 'Número de la señal ' + f.orden + ' (su lugar en el orden)');
                cabeza.appendChild(numero);
            } else if (f.orden) {
                cabeza.appendChild(crear('span', 'senal-numero', String(f.orden)));
            }
            var origen = crear(f.importacion ? 'a' : 'strong', 'senal-origen', f.origen);
            if (f.importacion) { origen.href = f.importacion; origen.title = 'Ver esa importación (de qué lista salió)'; }
            cabeza.appendChild(origen);
            if (f.estado) {
                cabeza.appendChild(crear('span', 'senal-estado' + (f.caida ? ' estado-mal' : ''),
                    f.estado + (f.activa ? '' : (f.retirada ? ' · retirada' : ' · apagada a mano'))));
            }
            li.appendChild(cabeza);
            var tecnico = [f.tipo, f.calidad, f.codec && !f.calidad ? 'códec ' + f.codec : ''].filter(Boolean).join(' · ');
            if (tecnico) li.appendChild(crear('div', 'senal-dato', tecnico));
            if (f.error) li.appendChild(crear('div', 'senal-dato estado-mal', 'Error: ' + f.error));
            if (f.probada) li.appendChild(crear('div', 'senal-dato', 'Probada por el servidor el ' + f.probada));
            if (f.aparatos) li.appendChild(crear('div', 'senal-dato', 'En los aparatos: ' + f.aparatos));
            if (f.oculta) li.appendChild(crear('div', 'senal-dato estado-mal', f.oculta));
            if (f.retirada) li.appendChild(crear('div', 'senal-dato estado-mal', f.retirada));
            if (f.problema) li.appendChild(crear('div', 'senal-dato senal-aviso', f.problema));
            if (f.salud) li.appendChild(crear('div', 'senal-dato' + (f.salud_mal ? ' estado-mal' : ''), 'Salud: ' + f.salud));
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
            // En una serie cada señal junta las de muchos capítulos: ahí no van (como Borrar)
            if (formAccion && f.borrable && f.id) {
                botones.appendChild(botonDeAccion('Probar ahora', 'bi-arrow-repeat', '', function () { accion(f, datos, 'probar'); }));
                if (f.se_puede_mostrar) {
                    botones.appendChild(botonDeAccion('Volver a mostrar esta señal', 'bi-eye', '', function () { accion(f, datos, 'mostrar'); }));
                }
                if (f.activa) {
                    botones.appendChild(botonDeAccion('Quitar esta señal', 'bi-eye-slash', 'text-danger', function () { accion(f, datos, 'quitar'); }));
                }
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

    // ── Los filtros quedan fijos arriba solo si entran en un renglón: partidos en dos o tres
    // (columna angosta, panel abierto) tapaban las tarjetas. Ahí se van al bajar, como el resto ──
    var filtros = document.querySelector('.organizar-filtros');
    if (filtros && window.ResizeObserver) {
        new ResizeObserver(function () {
            var visibles = Array.prototype.filter.call(filtros.children, function (hijo) { return hijo.offsetParent; });
            var partidos = visibles.some(function (hijo) { return Math.abs(hijo.offsetTop - visibles[0].offsetTop) > 8; });
            filtros.classList.toggle('no-entra', partidos);
        }).observe(filtros);
    }

    // ── El panel de al lado ──
    var panel = document.getElementById('detalle-lateral');
    if (!panel) return;
    var tarjetas = Array.prototype.slice.call(document.querySelectorAll('.espejo-tarjeta'));
    var mostrada = null;

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
            : 'La app prueba la 1 y, si no anda, pasa a la siguiente. Si una no anda, quitala (la podés volver a mostrar) o borrala: las otras quedan. Las que no andan en una semana se retiran solas.';
        pintar(panel.querySelector('[data-detalle-senales]'), datos);

        var mas = panel.querySelector('[data-detalle-mas]');
        mas.href = datos.mas;
        mas.textContent = esSerie ? 'Ver y ordenar capítulos' : 'Más opciones';
        // Kairos: sus señales una por una, en la pantalla Señales (con su acción ahí mismo)
        var enSenales = panel.querySelector('[data-detalle-senales-link]');
        if (enSenales) {
            enSenales.hidden = esSerie;
            if (!esSerie) enSenales.href = enSenales.dataset.base + '?problema=cualquiera&canal=' + datos.pk;
        }
        panel.hidden = false;
        panel.querySelector('.detalle-lateral-cuerpo').scrollTop = 0;
    }

    function cerrar() {
        panel.hidden = true;
        if (mostrada) mostrada.classList.remove('detalle-actual');
        mostrada = null;
    }

    // Elegir tarjetas (para cambiarles la categoría, borrarlas...) NO abre el panel: molestaba al
    // trabajar con varias. Lo abre el botón «Detalles»; otra vez sobre la misma, lo cierra.
    tarjetas.forEach(function (tarjeta) {
        var ver = tarjeta.querySelector('.espejo-ver');
        if (!ver) return;
        ver.addEventListener('click', function () {
            if (mostrada === tarjeta) cerrar();
            else mostrar(tarjeta);
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
