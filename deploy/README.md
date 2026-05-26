# Deploy en Azure — DocuInsight

Guia paso-a-paso para deployar la app en **Azure Container Apps** (scale-to-zero, ~$5-10/mes en idle).

Asumimos: tenes acceso a una subscription Azure con rol Contributor sobre algun Resource Group, y `az cli` instalado.

---

## 0. Pre-requisitos (one-time)

```bash
# Instalar Azure CLI si no lo tenes
# Windows: winget install Microsoft.AzureCLI
# Mac:     brew install azure-cli

# Login al tenant
az login --tenant <TENANT_ID>

# Setear la subscription a usar
az account set --subscription <SUBSCRIPTION_ID>

# Verificar
az account show --query "{name:name, id:id, tenantId:tenantId}" -o table
```

---

## 1. Preparar el contexto de build

Los modelos GLiNER (4.4 GB) y PaddleOCR (16 MB) no estan en git. Tenes que copiarlos al repo antes del docker build:

```bash
# 1a. GLiNER models (deberian estar ya en models/ner/gliner/ — son los que bajaste de Drive)
ls models/ner/gliner/cc/pytorch_model.bin   # debe existir (~1.1 GB)

# 1b. PaddleOCR models (copiar de tu cache local al folder del repo)
mkdir -p paddle_cache/whl
cp -r ~/.paddleocr/whl/det paddle_cache/whl/
cp -r ~/.paddleocr/whl/rec paddle_cache/whl/
cp -r ~/.paddleocr/whl/cls paddle_cache/whl/
ls paddle_cache/whl/  # debe haber: cls/ det/ rec/
```

Si todavia no tenes los Paddle models, bajalos con:
```bash
curl -k -o /tmp/det.tar https://paddleocr.bj.bcebos.com/PP-OCRv3/english/en_PP-OCRv3_det_infer.tar
curl -k -o /tmp/rec.tar https://paddleocr.bj.bcebos.com/PP-OCRv3/multilingual/latin_PP-OCRv3_rec_infer.tar
curl -k -o /tmp/cls.tar https://paddleocr.bj.bcebos.com/dygraph_v2.0/ch/ch_ppocr_mobile_v2.0_cls_infer.tar
mkdir -p paddle_cache/whl/det/en paddle_cache/whl/rec/latin paddle_cache/whl/cls
tar -xf /tmp/det.tar -C paddle_cache/whl/det/en
tar -xf /tmp/rec.tar -C paddle_cache/whl/rec/latin
tar -xf /tmp/cls.tar -C paddle_cache/whl/cls
```

---

## 2. Build local de la imagen

```bash
docker build -t docuinsight:latest .
```

Build inicial: ~10-15 min (instala torch, paddle, transformers; bakea 4.4 GB de modelos). Image final ~5.5 GB.

Verificar local antes de pushear:
```bash
docker run --rm -p 8501:8501 docuinsight:latest
# Abrir http://localhost:8501 y probar
```

---

## 3. Crear el Resource Group

```bash
RG=rg-docuinsight-demo
LOCATION=eastus2

az group create --name $RG --location $LOCATION
```

---

## 4. Deploy de la infraestructura (Bicep)

```bash
az deployment group create \
    --resource-group $RG \
    --template-file deploy/infra.bicep \
    --parameters appName=docuinsight imageTag=latest
```

Esto crea:
- **Azure Container Registry** (Basic, ~$5/mes)
- **Log Analytics workspace** (~$2/mes por ingestion baja de demo)
- **Container Apps Environment** (sin costo fijo)
- **Container App** con scale-to-zero (paga $0 cuando nadie usa)

Toma ~5 min.

Al finalizar te muestra los outputs:
```
appUrl: https://docuinsight.xxxxxx.eastus2.azurecontainerapps.io
acrLoginServer: docuinsightacr.azurecr.io
acrName: docuinsightacr
```

Guarda esos valores en variables:
```bash
ACR=$(az deployment group show -g $RG -n infra --query "properties.outputs.acrName.value" -o tsv)
APP_URL=$(az deployment group show -g $RG -n infra --query "properties.outputs.appUrl.value" -o tsv)
echo "ACR: $ACR"
echo "URL: $APP_URL"
```

---

## 5. Push de la imagen al ACR

```bash
# Login al ACR
az acr login --name $ACR

# Tag de la imagen local
docker tag docuinsight:latest $ACR.azurecr.io/docuinsight:latest

# Push (15-25 min la primera vez, son ~5 GB; siguientes pushes son rapidos)
docker push $ACR.azurecr.io/docuinsight:latest
```

---

## 6. Forzar restart del Container App con la nueva imagen

```bash
az containerapp update \
    --name docuinsight \
    --resource-group $RG \
    --image $ACR.azurecr.io/docuinsight:latest
```

Toma ~3 min en crear el revision nueva y rutear trafico.

---

## 7. Probar

Abrir `$APP_URL` en el browser. La primera vez:
- Cold start: ~2-3 min (Container Apps levanta replica desde cero + carga modelos GLiNER 4.4 GB)
- Procesar primer documento: ~5-10 segundos
- Documentos siguientes en la misma sesion: 1-3 segundos

**Tip para la presentacion**: 15 min antes de empezar, abrí la URL desde tu PC para que la replica este warm. Durante la demo todo va a ser rapido.

---

## 8. (Opcional) Dominio custom

Si queres `docuinsight.tudominio.com` en vez de `docuinsight.xxx.azurecontainerapps.io`:

```bash
az containerapp hostname add \
    --hostname docuinsight.tudominio.com \
    --resource-group $RG \
    --name docuinsight

# Despues configurar el CNAME en tu DNS apuntando al fqdn del Container App
# y bindear el cert managed (free):
az containerapp hostname bind \
    --hostname docuinsight.tudominio.com \
    --resource-group $RG \
    --name docuinsight \
    --environment docuinsight-env \
    --validation-method CNAME
```

---

## 9. Limpieza despues de la demo

Si solo era para la presentacion y ya termino:

```bash
az group delete --name $RG --yes --no-wait
```

Borra todo. Costo total de una demo de 1 noche: ~$2-5 USD.

---

## Costos esperados

| Escenario | Costo aprox/mes |
|---|---|
| Idle (scale-to-zero, 0 visitas) | $5-7 |
| Demo de 4 horas en un dia | $5-8 |
| Uso ligero (10 sesiones/dia, 30 dias) | $15-25 |
| Demo de 1 noche + delete RG | $2-5 |

---

## Troubleshooting

### El container no arranca / health check falla

Ver los logs:
```bash
az containerapp logs show --name docuinsight --resource-group $RG --follow
```

### "ImagePullBackOff" en el deploy

ACR no esta accesible. Verificar que el username/password del ACR esten en los secrets del Container App:
```bash
az containerapp show --name docuinsight --resource-group $RG \
    --query "properties.configuration.registries"
```

### Cold start tarda mas de 5 min

Es normal con 4.4 GB de modelos en CPU. Si es bloqueante:
- Subir el `minReplicas` a 1 (siempre 1 replica arriba, ~$25/mes en vez de $5)
- O usar Storage + descarga lazy en el primer request (mas complejo, fuera de scope)

### Out of memory

Container Apps mata el proceso si excede los 8 GB. Aumentar `containerMemory` a `16Gi`:
```bash
az containerapp update --name docuinsight -g $RG --memory 16Gi --cpu 4
```
