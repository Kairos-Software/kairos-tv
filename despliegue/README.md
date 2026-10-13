# despliegue/

Archivos y pasos para poner Kairos TV en el servidor de producción.
No son parte del sistema: se copian a mano en el servidor.

| Archivo | Va en el servidor en | Para qué |
|---|---|---|
| `kairostv.service` | `/opt/paginas-services/kairostv.service` | Arranca Django con gunicorn en el puerto 8017 |
| `nginx/kairostv-paso1.conf` | `/opt/nginx/conf/conf.d/kairostv.conf` (temporal) | Solo puerto 80, para sacar el certificado |
| `nginx/kairostv.conf` | `/opt/nginx/conf/conf.d/kairostv.conf` (definitivo) | https + static + media + proxy a gunicorn |

Datos: dominio `kairostv.grupokairosarg.com`, puerto `8017`, proyecto en
`/proyectos-ks/kairosTV/kairos-tv`, entorno virtual en `/proyectos-ks/kairosTV/venv`.

## Primera instalación

### 0. DNS
El subdominio tiene que apuntar al servidor (registro A con la IP del VPS).
Verificar: `ping kairostv.grupokairosarg.com` responde con la IP del servidor.
Sin esto el certificado del paso 6 falla.

### 1. Bajar el proyecto
```
mkdir -p /proyectos-ks/kairosTV
cd /proyectos-ks/kairosTV
git clone https://github.com/Kairos-Software/kairos-tv.git
```

### 2. Entorno virtual
Django 6.1 necesita Python 3.12 o más nuevo: verificar con `python3 --version`.
```
cd /proyectos-ks/kairosTV
python3 -m venv venv
venv/bin/pip install -r kairos-tv/requirements.txt gunicorn
```

### 3. Elegir el entorno
`.env.production` ya viene en el repo. Falta `.env`, que solo dice qué entorno usar
(lo necesitan `manage.py` y el cron; el servicio ya lo trae puesto):
```
cd /proyectos-ks/kairosTV/kairos-tv
echo "DJANGO_ENV=production" > .env
```

### 4. Base de datos y Django
```
sudo -u postgres createdb kairosTV
../venv/bin/python manage.py migrate
../venv/bin/python manage.py crear_roles_iniciales
../venv/bin/python manage.py createsuperuser
../venv/bin/python manage.py collectstatic --noinput
../venv/bin/python manage.py check --deploy
```
`migrate` crea las tablas (la base la crea `createdb`, Django no la crea).
El nombre tiene mayúsculas: `createdb` lo respeta tal cual, pero dentro de `psql`
hay que escribirlo entre comillas dobles (`\c "kairosTV"`, `DROP DATABASE "kairosTV";`).

### 5. Servicio (gunicorn)
```
cp despliegue/kairostv.service /opt/paginas-services/
systemctl link /opt/paginas-services/kairostv.service
systemctl enable --now kairostv
systemctl status kairostv
```
`systemctl link` crea en `/etc/systemd/system/` un acceso directo a tu archivo de
`/opt/paginas-services/`. Así hay UN solo archivo: si lo editás, después corré
`systemctl daemon-reload` y `systemctl restart kairostv`. No hace falta copiarlo.

Verificar que Django responde (antes de tocar nginx):
```
curl -I -H "Host: kairostv.grupokairosarg.com" http://127.0.0.1:8017/
```
Tiene que dar `HTTP/1.1 302` (manda al login) o `200`.

### 6. Certificado (sin el error de "no existe el archivo ssl")
El error de siempre pasa porque el `.conf` con `listen 443 ssl` nombra archivos de
`/etc/letsencrypt/live/...` que todavía no existen: `nginx -t` falla, nginx no
recarga y certbot no puede validar el dominio. Por eso va en dos pasos:

```
mkdir -p /var/www/certbot
cp despliegue/nginx/kairostv-paso1.conf /opt/nginx/conf/conf.d/kairostv.conf
/opt/nginx/sbin/nginx -t && /opt/nginx/sbin/nginx -s reload
curl http://kairostv.grupokairosarg.com/        # -> "Kairos TV: sacando el certificado"

certbot certonly --webroot -w /var/www/certbot -d kairostv.grupokairosarg.com \
    --deploy-hook "/opt/nginx/sbin/nginx -s reload"

cp despliegue/nginx/kairostv.conf /opt/nginx/conf/conf.d/kairostv.conf
/opt/nginx/sbin/nginx -t && /opt/nginx/sbin/nginx -s reload
```
Si `/opt/nginx/sbin/nginx` no existe, buscar el ejecutable con `which nginx`.
El `--deploy-hook` hace que nginx recargue solo cada vez que el certificado se renueva.

Verificar: abrir https://kairostv.grupokairosarg.com en el navegador → login del panel.

### 7. Tareas programadas
`crontab -e` y agregar:
```
0 */6 * * * cd /proyectos-ks/kairosTV/kairos-tv && ../venv/bin/python manage.py verificar_fuentes >> /var/log/kairostv-cron.log 2>&1
30 3 * * * cd /proyectos-ks/kairosTV/kairos-tv && ../venv/bin/python manage.py limpiar_registros >> /var/log/kairostv-cron.log 2>&1
```
- `verificar_fuentes` (cada 6 h): prueba las fuentes de los canales y marca las caídas. En la
  corrida de madrugada (la de las 0 y la de las 6) además mide una tanda de fuentes de los canales
  que tienen varias, para que la app arranque por la mejor (no hay que agregar nada). Mientras corre,
  el panel lo muestra arriba y las cargas de listas esperan a que termine (`core/trabajos.py`).
- `limpiar_registros` (todos los días 3:30): borra actividad y avisos viejos.

## Actualizar (cada vez que hay cambios)
```
cd /proyectos-ks/kairosTV/kairos-tv
git pull
../venv/bin/pip install -r requirements.txt
../venv/bin/python manage.py migrate
../venv/bin/python manage.py crear_roles_iniciales
../venv/bin/python manage.py collectstatic --noinput
systemctl restart kairostv
```
`crear_roles_iniciales` se repite porque suma a los roles los permisos nuevos.

**yt-dlp** (lee YouTube, Twitch y otras páginas de video, ver `canales/README.md`)
se rompe cada vez que esos sitios cambian algo. Si los canales de YouTube
empiezan a aparecer caídos todos juntos, actualizarlo y reiniciar:
```
../venv/bin/pip install -U yt-dlp
systemctl restart kairostv
```

**Si cambió `despliegue/nginx/kairostv.conf`** (git pull no lo aplica solo:
nginx lee su propia copia), copiarlo y recargar nginx:
```
cp despliegue/nginx/kairostv.conf /opt/nginx/conf/conf.d/kairostv.conf
/opt/nginx/sbin/nginx -t && /opt/nginx/sbin/nginx -s reload
```
Ejemplo: en octubre 2026 se agregó `client_max_body_size 25m;` para poder subir
listas M3U grandes desde el panel (sin eso nginx corta en 1 MB con error 413).

## Si algo falla
- Errores de Django: `journalctl -u kairostv -f`
- Errores de nginx: `tail -f /opt/nginx/logs/error.log`
- Error 400 "Bad Request": el dominio no está en `ALLOWED_HOSTS` de `.env.production`.
- Error 502: gunicorn no está corriendo (`systemctl status kairostv`).
