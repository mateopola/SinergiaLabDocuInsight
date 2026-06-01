# Deploy GRATIS en Hugging Face Spaces — DocuInsight

Guia paso-a-paso para publicar la app en **Hugging Face Spaces** (gratis, 16 GB
RAM, link publico). Reusa el `Dockerfile` del repo (Docker SDK) — no hay que
cambiar codigo.

> **El paso pesado**: subir los 4 modelos GLiNER (~4.4 GB) al Space via git-lfs.
> Es una sola vez, pero en internet de casa puede tardar (segun tu subida). El
> resto es rapido.

---

## 0. Pre-requisitos (una vez)

1. Cuenta gratis en https://huggingface.co (registrate con tu email).
2. Un **Access Token** con permiso de escritura:
   - https://huggingface.co/settings/tokens -> "New token" -> tipo **Write**.
   - Copialo (lo usas como password al hacer git push).
3. `git-lfs` instalado:
   ```powershell
   git lfs version    # si falla: winget install GitHub.GitLFS  (o https://git-lfs.com)
   git lfs install
   ```

---

## 1. Crear el Space

1. https://huggingface.co/new-space
2. Completa:
   - **Owner**: tu usuario
   - **Space name**: `docuinsight`
   - **License**: la que prefieras (ej. `mit`)
   - **SDK**: elegir **Docker** -> **Blank**
   - **Hardware**: `CPU basic` (gratis, 2 vCPU / 16 GB RAM)
   - **Visibility**: Public
3. "Create Space". Te queda un repo git vacio en:
   `https://huggingface.co/spaces/TU_USUARIO/docuinsight`

---

## 2. Clonar el Space y traer el codigo

Trabajamos en una carpeta aparte (el Space es OTRO repo git, distinto al de GitHub):

```powershell
cd "C:\Users\mateo\Desktop\Archivos\Estudio\Especializacion IA\Proyectos"
git clone https://huggingface.co/spaces/TU_USUARIO/docuinsight docuinsight-space
cd docuinsight-space
```

Copiar los archivos que la app necesita en runtime (desde el repo Docuinsight):

```powershell
$src = "..\Docuinsight"
copy "$src\Dockerfile" .
copy "$src\requirements.txt" .
copy "$src\app.py" .
copy "$src\real_models.py" .
copy "$src\pipeline.py" .
copy "$src\schemas.py" .
copy "$src\export.py" .
copy "$src\mock_models.py" .
xcopy "$src\pipeline_utils" ".\pipeline_utils\" /E /I
xcopy "$src\assets" ".\assets\" /E /I
xcopy "$src\.streamlit" ".\.streamlit\" /E /I
xcopy "$src\models" ".\models\" /E /I    # los 4.4 GB de modelos GLiNER + classifier
```

---

## 3. Crear el README del Space (metadata para HF)

HF lee la config del Space de un header YAML en `README.md`. Crear `README.md`
en la raiz del Space con este contenido:

```markdown
---
title: DocuInsight
emoji: 📄
colorFrom: blue
colorTo: orange
sdk: docker
app_port: 8501
pinned: false
short_description: Extraccion inteligente de datos de documentos colombianos
---

# DocuInsight

Demo academico de procesamiento inteligente de documentos colombianos
(Cedula, RUT, Camara de Comercio, Poliza). Sube un PDF/imagen y extrae los
campos clave automaticamente.

**Aviso**: demo educativo. No subas documentos con datos sensibles reales.
```

> `app_port: 8501` es clave: le dice a HF que la app escucha en el puerto 8501
> (el que expone el Dockerfile).

---

## 4. Configurar git-lfs para los modelos

Los `.bin` de los modelos son grandes -> deben ir por git-lfs, no como blobs normales:

```powershell
git lfs install
git lfs track "*.bin"
git lfs track "*.safetensors"
git lfs track "*.joblib"
git add .gitattributes
```

> El `.gitignore` del repo Docuinsight excluye `models/`. En el Space SI los
> queremos, asi que NO copies ese `.gitignore` (o borra la linea `models/`).
> Si copiaste un `.gitignore` con `models/`, eliminala ahora.

---

## 5. Commit y push (aca va el upload de 4.4 GB)

```powershell
git add .
git commit -m "DocuInsight: app + modelos GLiNER (deploy inicial HF Spaces)"
git push
```

- Te pide usuario (tu user de HF) y password (**pega el Access Token**, no tu clave).
- El push sube ~4.4 GB via git-lfs. Tarda segun tu subida (puede ser 30 min - 2 h).
  No cierres la terminal. Si se corta, `git push` de nuevo reanuda.

---

## 6. HF construye y publica solo

Apenas termina el push, HF:
1. Detecta el Dockerfile -> hace `docker build` en sus servidores (~10-15 min).
2. Levanta el container y rutea al puerto 8501.

Segui el progreso en la pestaña **"Logs"** / **"App"** del Space en el navegador.

Cuando termine, tu app esta publica en:
`https://huggingface.co/spaces/TU_USUARIO/docuinsight`

Cualquiera con el link la puede usar.

---

## 7. Probar

- **Primer arranque (cold start)**: ~1-2 min (carga el primer modelo GLiNER lazy).
- **Primer documento de cada tipo**: ~30-60 s (carga ese modelo).
- **Documentos siguientes del mismo tipo**: pocos segundos.
- El Space **se duerme tras 48 h sin uso** y despierta solo al visitarlo
  (primer acceso post-sleep tarda un poco mas).

---

## Notas y troubleshooting

### Las variables de entorno (protobuf, RAM) ya estan resueltas

El `Dockerfile` setea `PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python` y
`SINGLE_MODEL_RAM=1` en su bloque `ENV`. No tenes que configurar nada en HF.

### El build falla por tamano / timeout

Si HF se queja del tamano de imagen o el build expira:
- Verifica que `models/` se subio por git-lfs (no como blobs): en el Space web,
  abri un `pytorch_model.bin` -> debe decir "Stored with Git LFS".
- Si persiste, alternativa: hostear los modelos en un **repo de modelos HF**
  aparte y bajarlos en runtime (requiere un cambio de codigo; avisame y lo armo).

### PaddleOCR no descarga sus modelos

HF tiene internet, deberia bajar solo en el primer request. Si falla por SSL del
CDN de Baidu, `app.py` ya tiene el workaround de SSL. Revisar logs del Space.

### Privacidad

El Space es publico y la gente sube documentos a un server de terceros (HF).
El README ya incluye el aviso de "no subir datos sensibles reales". Para un demo
de clase esta bien; para datos reales del banco, NO usar un Space publico.

---

## Resumen de costos

| Recurso | Costo |
|---|---|
| HF Space CPU basic (2 vCPU, 16 GB RAM) | **$0** |
| Almacenamiento del Space (hasta 50 GB) | **$0** |
| Trafico / uso publico | **$0** |

Gratis de verdad. El unico "costo" es el tiempo del upload inicial de 4.4 GB.
