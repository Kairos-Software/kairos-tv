/* sistema.js — comportamiento general del sistema (sin dependencias) */

(function () {
    'use strict';

    // ── Menú lateral en celulares ──────────────────────────────────
    const app = document.querySelector('.app');
    const menu = document.getElementById('menu-principal');
    const botonesAlternar = document.querySelectorAll('[data-accion="alternar-menu"]');
    const claveMenu = 'kairos.menu.colapsado';
    const vistaEscritorio = window.matchMedia('(min-width: 1200px)');
    const contenido = document.querySelector('.contenido');
    let focoAntesDelMenu = null;

    function esEscritorio() {
        return vistaEscritorio.matches;
    }

    function actualizarBotones() {
        if (!app) return;
        const colapsado = app.classList.contains('menu-colapsado');
        const abierto = app.classList.contains('menu-abierto');
        if (menu) menu.inert = !esEscritorio() && !abierto;
        if (contenido) contenido.inert = !esEscritorio() && abierto;
        botonesAlternar.forEach(function (btn) {
            const expandido = esEscritorio() ? !colapsado : abierto;
            btn.setAttribute('aria-expanded', String(expandido));
            btn.setAttribute('aria-label', esEscritorio()
                ? (colapsado ? 'Expandir menú' : 'Contraer menú')
                : (abierto ? 'Cerrar menú' : 'Abrir menú'));
            btn.title = btn.getAttribute('aria-label');
            const icono = btn.querySelector('i');
            if (icono && btn.classList.contains('menu-colapsar')) {
                icono.className = colapsado ? 'bi bi-chevron-right' : 'bi bi-chevron-left';
            }
        });
        if (menu) {
            menu.querySelectorAll('.menu-link').forEach(function (enlace) {
                const texto = enlace.querySelector('.menu-link-texto');
                if (esEscritorio() && colapsado && texto) enlace.title = texto.textContent.trim();
                else enlace.removeAttribute('title');
            });
        }
    }

    function establecerMenuColapsado(colapsado) {
        if (!app) return;
        app.classList.toggle('menu-colapsado', colapsado);
        try { localStorage.setItem(claveMenu, colapsado ? '1' : '0'); } catch (_) { /* sin persistencia */ }
        actualizarBotones();
    }

    function abrirMenu() {
        if (!app) return;
        focoAntesDelMenu = document.activeElement;
        app.classList.add('menu-abierto');
        document.body.classList.add('menu-bloqueado');
        actualizarBotones();
        const cerrar = menu && menu.querySelector('[data-accion="cerrar-menu"]');
        if (cerrar) cerrar.focus();
    }

    function cerrarMenu(devolverFoco) {
        if (!app) return;
        app.classList.remove('menu-abierto');
        document.body.classList.remove('menu-bloqueado');
        actualizarBotones();
        if (devolverFoco && focoAntesDelMenu && typeof focoAntesDelMenu.focus === 'function') {
            focoAntesDelMenu.focus();
        }
    }

    botonesAlternar.forEach(function (btn) {
        btn.addEventListener('click', function () {
            if (esEscritorio()) {
                establecerMenuColapsado(!app.classList.contains('menu-colapsado'));
            } else if (app.classList.contains('menu-abierto')) {
                cerrarMenu(true);
            } else {
                abrirMenu();
            }
        });
    });
    document.querySelectorAll('[data-accion="cerrar-menu"]').forEach(function (el) {
        el.addEventListener('click', function () { cerrarMenu(true); });
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && app && app.classList.contains('menu-abierto')) cerrarMenu(true);
        if (e.key === 'Tab' && menu && !esEscritorio() && app.classList.contains('menu-abierto')) {
            const controles = Array.from(menu.querySelectorAll('a[href], button, input, select, textarea, [tabindex="0"]'))
                .filter(function (el) { return !el.disabled && el.getClientRects().length; });
            const primero = controles[0];
            const ultimo = controles[controles.length - 1];
            if (e.shiftKey && document.activeElement === primero) { e.preventDefault(); ultimo.focus(); }
            else if (!e.shiftKey && document.activeElement === ultimo) { e.preventDefault(); primero.focus(); }
        }
    });
    if (menu) {
        menu.querySelectorAll('a').forEach(function (enlace) {
            enlace.addEventListener('click', function () {
                if (!esEscritorio()) cerrarMenu(false);
            });
        });
    }
    if (app) {
        let colapsadoGuardado = false;
        try { colapsadoGuardado = localStorage.getItem(claveMenu) === '1'; } catch (_) { /* sin persistencia */ }
        app.classList.toggle('menu-colapsado', colapsadoGuardado && esEscritorio());
        actualizarBotones();
    }
    vistaEscritorio.addEventListener('change', function () {
        if (!app) return;
        cerrarMenu(false);
        if (esEscritorio()) {
            try { app.classList.toggle('menu-colapsado', localStorage.getItem(claveMenu) === '1'); } catch (_) { /* sin persistencia */ }
        } else {
            app.classList.remove('menu-colapsado');
        }
        actualizarBotones();
    });

    // ── Paneles plegables enlazables ────────────────────────────
    function abrirDetalle(id, moverFoco) {
        const detalle = document.getElementById(id);
        if (!detalle || detalle.tagName !== 'DETAILS') return false;
        detalle.open = true;
        requestAnimationFrame(function () {
            detalle.scrollIntoView({behavior: 'smooth', block: 'start'});
            if (moverFoco) {
                const control = detalle.querySelector('input:not([type="hidden"]), select, button, textarea');
                if (control) control.focus({preventScroll: true});
            }
        });
        return true;
    }

    document.querySelectorAll('[data-abrir-detalle]').forEach(function (enlace) {
        enlace.addEventListener('click', function (evento) {
            const id = enlace.dataset.abrirDetalle;
            if (!abrirDetalle(id, true)) return;
            evento.preventDefault();
            if (window.location.hash !== '#' + id) history.pushState(null, '', '#' + id);
        });
    });
    if (window.location.hash) {
        try { abrirDetalle(decodeURIComponent(window.location.hash.slice(1)), false); } catch (_) { /* hash inválido */ }
    }

    // ── Mostrar / ocultar contraseña ──────────────────────────────
    document.querySelectorAll('[data-accion="ver-password"]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            const input = document.getElementById(btn.dataset.objetivo);
            if (!input) return;
            const visible = input.type === 'text';
            input.type = visible ? 'password' : 'text';
            btn.setAttribute('aria-label', visible ? 'Mostrar contraseña' : 'Ocultar contraseña');
            btn.querySelector('i').className = visible ? 'bi bi-eye' : 'bi bi-eye-slash';
        });
    });

    // ── Marcar / desmarcar todos los checkboxes de un grupo ────────
    // <button data-accion="marcar-grupo" data-grupo="id-del-contenedor">
    // Solo toca los que no están bloqueados. Si ya están todos marcados, los desmarca.
    document.querySelectorAll('[data-accion="marcar-grupo"]').forEach(function (btn) {
        const grupo = document.getElementById(btn.dataset.grupo);
        if (!grupo) return;
        const casillas = function () {
            return Array.from(grupo.querySelectorAll('input[type="checkbox"]:not(:disabled)'));
        };
        const actualizarTexto = function () {
            const todas = casillas();
            btn.hidden = todas.length === 0;
            btn.textContent = todas.length && todas.every(function (c) { return c.checked; })
                ? 'Desmarcar todos' : 'Marcar todos';
        };
        btn.addEventListener('click', function () {
            const todas = casillas();
            const marcar = !todas.every(function (c) { return c.checked; });
            todas.forEach(function (c) { c.checked = marcar; });
            actualizarTexto();
        });
        grupo.addEventListener('change', actualizarTexto);
        actualizarTexto();
    });

    // ── El momento: hora en vivo, saludo y línea del día ───────────
    // Usa la hora del dispositivo del usuario. El servidor ya dejó un
    // valor inicial, así que sin JS la pantalla igual se ve bien.
    const horas = document.querySelectorAll('[data-momento="hora"]');
    const saludos = document.querySelectorAll('[data-momento="saludo"]');
    const lineas = document.querySelectorAll('[data-momento="linea"]');

    function saludoPara(h) {
        if (h >= 6 && h < 13) return 'Buen día';
        if (h >= 13 && h < 20) return 'Buenas tardes';
        return 'Buenas noches';
    }

    function actualizarMomento() {
        const ahora = new Date();
        const h = ahora.getHours();
        const texto = String(h).padStart(2, '0') + ':' + String(ahora.getMinutes()).padStart(2, '0');
        horas.forEach(function (el) { el.textContent = texto; el.setAttribute('datetime', texto); });
        saludos.forEach(function (el) { el.textContent = saludoPara(h); });
        const avance = ((h * 60 + ahora.getMinutes()) / 1440) * 100;
        lineas.forEach(function (el) { el.style.setProperty('--avance-dia', avance.toFixed(2) + '%'); });
    }

    if (horas.length || saludos.length || lineas.length) {
        actualizarMomento();
        // Se sincroniza con el cambio de minuto
        setTimeout(function () {
            actualizarMomento();
            setInterval(actualizarMomento, 60000);
        }, (60 - new Date().getSeconds()) * 1000);
    }

    // Las tablas conservan toda su información en pantallas chicas y avisan
    // a lectores de pantalla que el contenido se puede desplazar.
    document.querySelectorAll('.table-responsive').forEach(function (contenedor) {
        contenedor.setAttribute('tabindex', '0');
        if (!contenedor.getAttribute('aria-label')) {
            contenedor.setAttribute('aria-label', 'Tabla desplazable horizontalmente');
        }
    });

    // Atajo de operador: "/" lleva al buscador de la pantalla actual.
    const buscadores = Array.from(document.querySelectorAll('input[type="search"]:not([data-buscador-secundario])'));
    buscadores.forEach(function (campo) {
        campo.setAttribute('aria-keyshortcuts', '/');
        if (!campo.title) campo.title = 'Atajo: /';
    });
    document.addEventListener('keydown', function (evento) {
        if (evento.key !== '/' || evento.ctrlKey || evento.metaKey || evento.altKey) return;
        const activo = document.activeElement;
        if (activo && (activo.matches('input, textarea, select') || activo.isContentEditable)) return;
        const buscador = buscadores.find(function (campo) {
            return !campo.disabled && campo.offsetParent !== null;
        });
        if (!buscador) return;
        evento.preventDefault();
        buscador.focus();
        buscador.select();
    });

    // Categoría: "elegí de la lista" u "o una nueva" — vale UNA sola. Escribir
    // una nueva vacía la lista (o la apaga, si no tiene opción vacía: lo escrito
    // es lo que vale); elegir de la lista borra lo escrito. Sirve en todos los
    // formularios del panel que tengan los dos campos.
    const NOMBRES_LISTA = ['categoria', 'categoria_destino'];
    const NOMBRES_NUEVA = ['nueva_categoria', 'categoria_nueva'];
    function camposDelFormulario(campo, nombres, etiqueta) {
        if (!campo.form) return [];
        return Array.prototype.filter.call(campo.form.elements, function (el) {
            return el.tagName === etiqueta && nombres.indexOf(el.name) >= 0;
        });
    }
    document.addEventListener('input', function (evento) {
        const nueva = evento.target;
        if (nueva.tagName !== 'INPUT' || NOMBRES_NUEVA.indexOf(nueva.name) < 0) return;
        const escrita = nueva.value.trim() !== '';
        camposDelFormulario(nueva, NOMBRES_LISTA, 'SELECT').forEach(function (lista) {
            const vacia = Array.prototype.some.call(lista.options, function (o) { return o.value === ''; });
            if (escrita && vacia) lista.value = '';
            lista.classList.toggle('categoria-anulada', escrita && !vacia);
            lista.title = escrita && !vacia ? 'Vale la categoría nueva que escribiste (borrala para elegir de la lista)' : '';
        });
    });
    document.addEventListener('change', function (evento) {
        const lista = evento.target;
        if (lista.tagName !== 'SELECT' || NOMBRES_LISTA.indexOf(lista.name) < 0 || !lista.value) return;
        camposDelFormulario(lista, NOMBRES_NUEVA, 'INPUT').forEach(function (nueva) { nueva.value = ''; });
        lista.classList.remove('categoria-anulada');
        lista.title = '';
    });

    // Logos de canales que no cargan (dirección vieja, o http dentro de https):
    // en su lugar quedan las iniciales del canal, como en la app.
    // Uso: <span data-iniciales="TN"><img src="..." alt=""></span>
    document.addEventListener('error', function (evento) {
        const imagen = evento.target;
        if (imagen.tagName !== 'IMG' || !imagen.parentElement || !imagen.parentElement.dataset.iniciales) return;
        imagen.parentElement.textContent = imagen.parentElement.dataset.iniciales;
    }, true);
})();
