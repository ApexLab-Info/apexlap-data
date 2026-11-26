# Comunidad de ApexLap con GitHub (gratis, sin servidor)

1. Crea un repositorio **público** (ej. `tuusuario/apexlap-data`) y sube el contenido de esta carpeta `online/`
   (incluida `.github/`). Crea además `index.json` con `[]`.
2. Crea la etiqueta `aprobado` en el repositorio (Issues → Labels). Solo tú la pones a los circuitos que quieras publicar.
3. GitHub → Settings → Developer settings → OAuth Apps → New. Marca **Enable Device Flow**. Copia el *Client ID*
   (no hace falta el secreto).
4. En `local.properties` de la app:
   ```
   GITHUB_REPO=tuusuario/apexlap-data
   GITHUB_CLIENT_ID=xxxxxxxx
   ```
   Recompila.
5. Settings → Actions → General → Workflow permissions: "Read and write".

Cómo funciona: la app lee los ficheros por raw.githubusercontent.com (sin login, solo en memoria).
Subir = abrir un issue con tu cuenta; la Action lo valida y lo guarda. Todo es público.
Los cambios tardan unos minutos en verse (caché de GitHub). Los perfiles y rankings se basan en la confianza
(un usuario podría mentir en su tiempo); los circuitos pasan por tu aprobación.
