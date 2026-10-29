/* Tablas del panel: avisar cuando quedan columnas por ver hacia la derecha. */
(function () {
    'use strict';

    document.querySelectorAll('.table-responsive').forEach(function (caja) {
        var pista = document.createElement('p');
        pista.className = 'tabla-pista';
        pista.textContent = 'Deslizá de costado para ver todas las columnas →';
        pista.setAttribute('aria-hidden', 'true');   // la tabla ya lo dice en su aria-label
        caja.parentNode.insertBefore(pista, caja);

        function mirar() {
            var falta = caja.scrollWidth - caja.clientWidth - caja.scrollLeft;
            pista.hidden = falta < 4;
        }
        caja.addEventListener('scroll', mirar, {passive: true});
        if (window.ResizeObserver) new ResizeObserver(mirar).observe(caja);
        else window.addEventListener('resize', mirar);
        mirar();
    });
})();
