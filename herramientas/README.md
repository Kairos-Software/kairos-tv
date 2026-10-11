# herramientas/

Código reutilizable en todo el sistema. Es el "puente" común entre proyectos:
lo que se escribe acá sirve para cualquier sistema que nazca de esta base.

## Qué va acá

Todo lo que no pertenece a una app en particular y se usa desde varias. Por ejemplo:

- **Funciones de texto**: pasar a minúsculas, quitar acentos, formatear nombres,
  dejar solo números (DNI, CUIT, teléfonos).
- **Listas fijas para desplegables**: países, provincias, tipos de documento, etc.
  Se definen una vez y se usan en cualquier modelo (cliente, usuario, empresa,
  tarjeta...), según lo que necesite cada sistema.
- **Campos de modelo listos para usar**: por ejemplo un campo "país" que ya
  trae la lista y el valor por defecto.
- **Validaciones comunes**: formatos de CUIT, teléfonos, etc.

## Qué NO va acá

- Nada que dependa de una app concreta (usuarios, ventas, clientes...).
  Eso va dentro de esa app.

## Regla

Las apps usan `herramientas`, pero `herramientas` nunca importa nada de las
apps. Así se puede copiar tal cual a cualquier proyecto.

## Cómo usar el modelo base

```python
from herramientas.modelos import ModeloBase

class Cliente(ModeloBase):
    nombre = models.CharField(max_length=150)

Cliente.objects.all()   # solo los no eliminados
Cliente.todos.all()     # todos, incluidos los eliminados
cliente.eliminar(request.user)   # baja lógica
cliente.restaurar(request.user)  # la deshace
```

## Contenido actual

| Archivo | Qué contiene |
|---|---|
| `modelos.py` | `ModeloBase`: molde para cualquier modelo nuevo. Trae fecha de creación y modificación, quién lo creó y modificó, y **baja lógica** ("eliminar" lo oculta en vez de borrarlo, y se puede restaurar). Ver el ejemplo de uso al principio del archivo. |
| `tests/` | Pruebas automáticas. `tests/app_pruebas/` es una mini-app con modelos de prueba que **solo se instala al correr los tests**. |
| `excel.py` | `planilla(hojas)`: arma un **.xlsx** sin instalar nada (texto, números, Sí/No y fechas; una o varias hojas, la primera fila en negrita y fija, con filtros y columnas de ancho cómodo). `TIPO_XLSX` para la respuesta. Para fórmulas, colores o gráficos haría falta una librería (openpyxl). |
| `formularios.py` | `EstiloBootstrapMixin`: agrega solo las clases de Bootstrap a los campos de cualquier formulario, marca en rojo los que tienen error (recién al validar, en `full_clean`: así un formulario puede armar sus desplegables después de `super().__init__()` y se valida con esas opciones) y pone "Elegir…" como opción vacía de los desplegables. `CampoFecha`: selector de fecha nativo del navegador. |
