/*
 * Tablas anchas que se deslizan de costado (.tabla-ancha-con-fija, en Estadísticas): si no entran,
 * aparece arriba "Deslizá de costado para ver todas las columnas →". Sin eso, en el celular o con
 * la ventana mediana la tabla se veía cortada y no se notaba que había más. Se va al llegar al final.
 */
(function () {
    'use strict';

    document.querySelectorAll('.tabla-ancha-con-fija').forEach(function (caja) {
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
        mirar();
    });
})();
