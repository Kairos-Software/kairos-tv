"""
ComprimirMiddleware: manda comprimidas (gzip) las páginas del panel y las
respuestas de la API (JSON), si quien pide lo acepta. Son texto que se
repite mucho: llegan 5 a 10 veces más livianas y el panel y la app cargan
más rápido con internet lenta.

Solo eso: una descarga (la APK que baja la app al actualizarse) no se toca.
Ya viene comprimida y, comprimida de nuevo, pierde el tamaño total, con lo
que la app no podría mostrar cuánto falta. Lo que ya viene comprimido (el
catálogo de la app, api/v1/catalogo.py) tampoco.

Es el GZipMiddleware de Django, que ya trae la protección contra BREACH
(agrega unos bytes al azar), limitado a esos tipos.
"""

from django.middleware.gzip import GZipMiddleware

TIPOS_QUE_SE_COMPRIMEN = ('text/html', 'application/json', 'text/plain', 'text/csv')


class ComprimirMiddleware(GZipMiddleware):

    def process_response(self, request, response):
        tipo = response.get('Content-Type', '')
        if response.streaming or not tipo.startswith(TIPOS_QUE_SE_COMPRIMEN):
            return response
        return super().process_response(request, response)
