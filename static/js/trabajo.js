/*
 * Kairos TV · lo que comparten las pantallas de TRABAJO de Contenido (estilos en static/css/trabajo.css):
 *
 *   <button class="ayuda-boton" data-ayuda="texto">?</button>  -> la explicación en una burbuja flotante (se cierra
 *                                                                  con Esc o tocando afuera): sin textos largos fijos
 *   <button data-copiar="link">                                 -> copia el texto al portapapeles
 *   <button type="submit" data-confirmar="¿Seguro?">            -> pide confirmación antes de mandar
 *   <select data-enviar-al-cambiar>                             -> filtra apenas se elige (sin tocar "Buscar")
 *   <input data-atajo="/">                                      -> la tecla / lleva a la búsqueda
 *   <form data-seleccion> con [data-elegir] (cada fila), [data-elegir-todas], [data-barra-lote] y [data-cuantas]
 *                                                               -> tildar filas (Shift = un rango) muestra la barra
 *                                                                  de abajo con cuántas hay elegidas
 *
 * Y para las pantallas que guardan sin recargar (Organizar, la página de una serie):
 *   KairosTrabajo.pedir(url, formData)          -> Promise del JSON {ok: true, ...}; si no, un Error con el motivo
 *   KairosTrabajo.avisar(texto, tipo, deshacer) -> un aviso abajo que se va solo ('bien' | 'mal' | 'info');
 *                                                  con `deshacer` (una función) suma el botón «Deshacer»
 */
(function () {
    'use strict';

    // ── Guardar sin recargar y avisar ──
    function csrfDeLaPagina() {
        var campo = document.querySelector('[name=csrfmiddlewaretoken]');
        return campo ? campo.value : '';
    }
    function pedir(url, datos) {
        return fetch(url, {
            method: 'POST', body: datos, credentials: 'same-origin',
            headers: {'Accept': 'application/json', 'X-CSRFToken': csrfDeLaPagina()}
        }).then(function (respuesta) {
            return respuesta.json().catch(function () { return null; }).then(function (r) {
                if (r && r.ok === true) return r;
                if (r && r.error) throw new Error(r.error);
                if (respuesta.status === 403) throw new Error('No tenés permiso para cambiar esto.');
                throw new Error('No se pudo guardar. Si estuviste mucho rato sin usar el panel, recargá la página.');
            });
        }, function () { throw new Error('No se pudo guardar: revisá la conexión.'); });
    }
    // Los avisos van en un contenedor popover="manual" (si el navegador lo tiene): queda en la capa de arriba de
    // todo, también sobre un cuadro abierto, y no se cierra al tocar otra cosa. Sin popover, es un fijo común.
    var avisos = null;
    var conPopoverDeAvisos = 'popover' in HTMLElement.prototype;
    function contenedorDeAvisos() {
        if (!avisos) {
            avisos = document.createElement('div');
            avisos.className = 'avisos-trabajo';
            avisos.setAttribute('role', 'status');
            avisos.setAttribute('aria-live', 'polite');
            if (conPopoverDeAvisos) avisos.setAttribute('popover', 'manual');
            document.body.appendChild(avisos);
        }
        if (conPopoverDeAvisos && !avisos.matches(':popover-open')) avisos.showPopover();
        return avisos;
    }
    function sacarAviso(aviso) {
        aviso.classList.add('saliendo');
        window.setTimeout(function () {
            aviso.remove();
            if (avisos && !avisos.children.length && conPopoverDeAvisos && avisos.matches(':popover-open')) avisos.hidePopover();
        }, 300);
    }
    function avisar(texto, tipo, deshacer) {
        if (!texto) return;
        var lista = contenedorDeAvisos();
        var aviso = document.createElement('div');
        aviso.className = 'aviso-trabajo aviso-' + (tipo || 'info');
        var mensaje = document.createElement('span');
        mensaje.textContent = texto;
        aviso.appendChild(mensaje);
        if (deshacer) {
            var boton = document.createElement('button');
            boton.type = 'button';
            boton.className = 'btn btn-sm btn-link';
            boton.textContent = 'Deshacer';
            boton.addEventListener('click', function () { sacarAviso(aviso); deshacer(); });
            aviso.appendChild(boton);
        }
        var cerrar = document.createElement('button');
        cerrar.type = 'button';
        cerrar.className = 'aviso-cerrar';
        cerrar.setAttribute('aria-label', 'Cerrar el aviso');
        cerrar.textContent = '×';
        cerrar.addEventListener('click', function () { sacarAviso(aviso); });
        aviso.appendChild(cerrar);
        lista.appendChild(aviso);
        while (lista.children.length > 3) lista.firstElementChild.remove();
        // Se va solo, pero no mientras tiene el mouse o el foco encima (para llegar a tocar «Deshacer»)
        var reloj = null;
        var irse = function () {
            window.clearTimeout(reloj);
            reloj = window.setTimeout(function () { sacarAviso(aviso); }, deshacer ? 9000 : 4500);
        };
        aviso.addEventListener('mouseenter', function () { window.clearTimeout(reloj); });
        aviso.addEventListener('focusin', function () { window.clearTimeout(reloj); });
        aviso.addEventListener('mouseleave', irse);
        aviso.addEventListener('focusout', irse);
        irse();
    }
    window.KairosTrabajo = {pedir: pedir, avisar: avisar};

    // ── Ayuda flotante: una sola burbuja (popover nativo: se cierra sola con Esc o tocando afuera) ──
    var burbuja = document.createElement('div');
    burbuja.className = 'ayuda-flotante';
    burbuja.id = 'ayuda-flotante';
    burbuja.setAttribute('role', 'tooltip');
    var conPopover = 'popover' in HTMLElement.prototype;
    if (conPopover) burbuja.setAttribute('popover', '');
    document.body.appendChild(burbuja);
    var botonAbierto = null;
    var recienCerrado = {boton: null, cuando: 0};   // el navegador la cierra al apretar, antes del clic

    function ubicar(boton) {
        var caja = boton.getBoundingClientRect();
        var ancho = burbuja.offsetWidth;
        var alto = burbuja.offsetHeight;
        var izquierda = Math.min(Math.max(8, caja.left + caja.width / 2 - ancho / 2), window.innerWidth - ancho - 8);
        var arriba = caja.bottom + 8;
        if (arriba + alto > window.innerHeight - 8) arriba = Math.max(8, caja.top - alto - 8);   // no entra abajo
        burbuja.style.left = izquierda + 'px';
        burbuja.style.top = arriba + 'px';
    }
    function cerrarAyuda() {
        if (conPopover) { if (burbuja.matches(':popover-open')) burbuja.hidePopover(); }
        else burbuja.classList.remove('abierta');
        if (botonAbierto) botonAbierto.setAttribute('aria-expanded', 'false');
        botonAbierto = null;
    }
    function abrirAyuda(boton) {
        var mismo = botonAbierto === boton || (recienCerrado.boton === boton && Date.now() - recienCerrado.cuando < 400);
        cerrarAyuda();
        if (mismo) return;   // tocar el mismo "?" la cierra
        burbuja.textContent = boton.dataset.ayuda;
        if (conPopover) burbuja.showPopover();
        else burbuja.classList.add('abierta');
        ubicar(boton);
        boton.setAttribute('aria-expanded', 'true');
        boton.setAttribute('aria-describedby', 'ayuda-flotante');
        botonAbierto = boton;
    }
    if (conPopover) {
        burbuja.addEventListener('toggle', function (evento) {
            if (evento.newState === 'closed' && botonAbierto) {
                botonAbierto.setAttribute('aria-expanded', 'false');
                recienCerrado = {boton: botonAbierto, cuando: Date.now()};
                botonAbierto = null;
            }
        });
    }
    document.querySelectorAll('[data-ayuda]').forEach(function (boton) {
        boton.setAttribute('aria-expanded', 'false');
        boton.setAttribute('aria-controls', 'ayuda-flotante');
    });
    document.addEventListener('click', function (evento) {
        var boton = evento.target.closest('[data-ayuda]');
        if (boton) {
            evento.preventDefault();
            evento.stopPropagation();
            abrirAyuda(boton);
        } else if (!conPopover && botonAbierto && !burbuja.contains(evento.target)) {
            cerrarAyuda();
        }
    }, true);
    document.addEventListener('keydown', function (evento) {
        if (evento.key === 'Escape' && !conPopover) cerrarAyuda();
    });
    window.addEventListener('scroll', function () { if (botonAbierto) cerrarAyuda(); }, {passive: true});

    // ── Copiar al portapapeles ──
    document.addEventListener('click', function (evento) {
        var boton = evento.target.closest('[data-copiar]');
        if (!boton) return;
        evento.preventDefault();
        var listo = function () {
            var titulo = boton.title;
            boton.classList.add('copiado');
            boton.title = '¡Copiado!';
            window.setTimeout(function () { boton.classList.remove('copiado'); boton.title = titulo; }, 1500);
        };
        if (navigator.clipboard) navigator.clipboard.writeText(boton.dataset.copiar).then(listo);
        else window.prompt('Copiá el link:', boton.dataset.copiar);
    });

    // ── Confirmar antes de mandar (lo que no se puede deshacer) ──
    document.addEventListener('submit', function (evento) {
        var boton = evento.submitter;
        if (boton && boton.dataset.confirmar && !window.confirm(boton.dataset.confirmar)) evento.preventDefault();
    });

    // ── Filtrar apenas se elige ──
    document.querySelectorAll('[data-enviar-al-cambiar]').forEach(function (campo) {
        campo.addEventListener('change', function () { campo.form.requestSubmit(); });
    });

    // ── Atajo de teclado a la búsqueda ──
    document.addEventListener('keydown', function (evento) {
        var enCampo = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) || document.activeElement.isContentEditable;
        if (enCampo || evento.ctrlKey || evento.metaKey || evento.altKey) return;
        var campo = document.querySelector('[data-atajo="' + evento.key + '"]');
        if (campo) { evento.preventDefault(); campo.focus(); campo.select(); }
    });

    // ── Tarjetas o lista (Organizar): queda guardado en este navegador ──
    var botonesVista = document.querySelectorAll('[data-vista]');
    function marcarVista() {
        var enLista = document.documentElement.classList.contains('vista-lista');
        botonesVista.forEach(function (b) { b.setAttribute('aria-pressed', String((b.dataset.vista === 'lista') === enLista)); });
    }
    botonesVista.forEach(function (boton) {
        boton.addEventListener('click', function () {
            document.documentElement.classList.toggle('vista-lista', boton.dataset.vista === 'lista');
            try { localStorage.setItem('kairos.vista', boton.dataset.vista); } catch (e) { /* sin guardar: igual cambia */ }
            marcarVista();
        });
    });
    marcarVista();

    // ── Cambiar un texto ahí mismo (el título de un capítulo): tocarlo, escribir, Enter guarda y Esc cancela ──
    function csrf() {
        var campo = document.querySelector('[name=csrfmiddlewaretoken]');
        return campo ? campo.value : '';
    }
    function editarAhiMismo(texto) {
        if (texto.querySelector('input')) return;
        var antes = texto.textContent;
        var campo = document.createElement('input');
        campo.type = 'text';
        campo.className = 'form-control form-control-sm titulo-editando';
        campo.maxLength = 100;
        campo.value = texto.dataset.titulo;
        campo.setAttribute('aria-label', 'Título nuevo');
        texto.textContent = '';
        texto.appendChild(campo);
        campo.focus();
        campo.select();
        var listo = false;
        function terminar(nuevo) {
            if (listo) return;
            listo = true;
            texto.textContent = nuevo;
            texto.focus();
        }
        function guardar() {
            if (listo) return;
            var titulo = campo.value.trim();
            if (titulo === texto.dataset.titulo) { terminar(antes); return; }
            campo.disabled = true;
            var datos = new FormData();
            datos.append('titulo', titulo);
            datos.append('csrfmiddlewaretoken', csrf());
            fetch(texto.dataset.tituloUrl, {method: 'POST', body: datos, credentials: 'same-origin'})
                .then(function (respuesta) { return respuesta.json(); })
                .then(function (resultado) {
                    if (resultado.error) {
                        window.alert(resultado.error);
                        terminar(antes);
                        return;
                    }
                    texto.dataset.titulo = resultado.titulo;
                    terminar(resultado.titulo || resultado.nombre);
                    texto.classList.add('recien-guardado');
                    window.setTimeout(function () { texto.classList.remove('recien-guardado'); }, 1500);
                })
                .catch(function () { window.alert('No se pudo guardar: revisá la conexión.'); terminar(antes); });
        }
        campo.addEventListener('keydown', function (evento) {
            if (evento.key === 'Enter') { evento.preventDefault(); guardar(); }   // que no mande el formulario de la página
            else if (evento.key === 'Escape') { evento.preventDefault(); terminar(antes); }
        });
        campo.addEventListener('blur', guardar);
        campo.addEventListener('click', function (evento) { evento.stopPropagation(); });
    }
    document.querySelectorAll('[data-titulo-url]').forEach(function (texto) {
        texto.addEventListener('click', function () { editarAhiMismo(texto); });
        texto.addEventListener('keydown', function (evento) {
            if ((evento.key === 'Enter' || evento.key === 'F2') && evento.target === texto) { evento.preventDefault(); editarAhiMismo(texto); }
        });
    });

    // ── Tildar filas y la barra de abajo ──
    document.querySelectorAll('form[data-seleccion]').forEach(function (form) {
        var filas = Array.prototype.slice.call(form.querySelectorAll('[data-elegir]'));
        var todas = form.querySelector('[data-elegir-todas]');
        var barra = form.querySelector('[data-barra-lote]');
        var cuantas = form.querySelector('[data-cuantas]');
        var ultima = null;
        function actualizar() {
            var elegidas = filas.filter(function (c) { return c.checked; }).length;
            if (barra) barra.hidden = !elegidas;
            if (cuantas) cuantas.textContent = elegidas + (elegidas === 1 ? ' elegida' : ' elegidas');
            if (todas) {
                todas.checked = elegidas > 0 && elegidas === filas.length;
                todas.indeterminate = elegidas > 0 && elegidas < filas.length;
            }
        }
        filas.forEach(function (casilla) {
            casilla.addEventListener('click', function (evento) {
                // Shift + clic: todas las del medio quedan igual que esta
                if (evento.shiftKey && ultima !== null) {
                    var desde = filas.indexOf(ultima);
                    var hasta = filas.indexOf(casilla);
                    filas.slice(Math.min(desde, hasta), Math.max(desde, hasta) + 1).forEach(function (c) { c.checked = casilla.checked; });
                }
                ultima = casilla;
                actualizar();
            });
        });
        if (todas) todas.addEventListener('change', function () {
            filas.forEach(function (c) { c.checked = todas.checked; });
            actualizar();
        });
        form.querySelectorAll('[data-limpiar-seleccion]').forEach(function (boton) {
            boton.addEventListener('click', function () {
                filas.forEach(function (c) { c.checked = false; });
                actualizar();
            });
        });
        actualizar();
    });
})();
