# Cómo hacer deploy en Vercel

## Paso 1 — Base de datos (Neon, gratis)

1. Ve a **https://neon.tech** y crea una cuenta (gratis, sin tarjeta)
2. Crea un nuevo proyecto
3. En el dashboard copia el **Connection string** (empieza con `postgresql://...`)

## Paso 2 — Subir a GitHub

1. Crea una cuenta en **https://github.com** si no tienes
2. Crea un repositorio nuevo (botón verde "New")
3. En tu PC abre la carpeta del proyecto y ejecuta:

```bash
git init
git add .
git commit -m "primer commit"
git remote add origin https://github.com/TU_USUARIO/entradas-monitor.git
git push -u origin main
```

## Paso 3 — Deploy en Vercel

1. Ve a **https://vercel.com** y crea una cuenta con GitHub
2. Clic en "Add New → Project"
3. Selecciona tu repositorio `entradas-monitor`
4. En **Environment Variables** añade:

| Variable | Valor |
|----------|-------|
| `DATABASE_URL` | La connection string de Neon |
| `TELEGRAM_TOKEN` | Token de tu bot de Telegram |
| `TELEGRAM_CHAT_ID` | Tu ID de Telegram |
| `CRON_SECRET` | Cualquier palabra secreta (ej: `mi-clave-2026`) |

5. Clic en **Deploy**

## Paso 4 — Inicializar la base de datos

La primera vez que abras la app, la base de datos se crea automáticamente.
Solo abre la URL de Vercel y ya está.

## Usar la app

- Abre tu URL de Vercel (ej: `entradas-monitor.vercel.app`)
- Clic en **+ Añadir evento**
- Pega la URL del teatro y guarda
- Los datos se actualizan solos cada 30 minutos
- Recibirás notificaciones en Telegram cuando haya nuevas ventas

## Notas

- El plan gratuito de Vercel soporta perfectamente esta app
- Neon tiene 512MB gratuitos (más que suficiente)
- El cron se ejecuta cada 30 min en la zona horaria UTC
