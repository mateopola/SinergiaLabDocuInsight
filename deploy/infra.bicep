// DocuInsight - Infraestructura Azure como codigo (Bicep).
//
// Crea: Container Registry + Container Apps Environment + Container App.
// Costo aprox: ~$5-10/mes con scale-to-zero (paga solo cuando alguien usa).
//
// Deploy:
//     az deployment group create \
//         --resource-group rg-docuinsight-demo \
//         --template-file infra.bicep \
//         --parameters appName=docuinsight imageTag=latest

@description('Nombre base de los recursos (sin espacios, lowercase)')
param appName string = 'docuinsight'

@description('Region de Azure. Default eastus2 (cerca de Colombia, soporta Container Apps)')
param location string = 'eastus2'

@description('Tag de la imagen Docker en el ACR (ej. latest, v1)')
param imageTag string = 'latest'

@description('CPU del container (vCores). 2 = suficiente para CPU-only')
param containerCpu string = '2'

@description('Memoria del container. 8 GB = suficiente para GLiNER 4.4GB + Paddle')
param containerMemory string = '8Gi'

// --- Container Registry ---
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: '${appName}acr'
  location: location
  sku: {
    name: 'Basic'  // $5/mes, suficiente para una imagen
  }
  properties: {
    adminUserEnabled: true  // habilitado para deploy simple; en prod usar managed identity
  }
}

// --- Log Analytics workspace (requerido por Container Apps Environment) ---
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${appName}-logs'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// --- Container Apps Environment ---
resource cae 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${appName}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// --- Container App ---
resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  properties: {
    managedEnvironmentId: cae.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8501
        transport: 'auto'
        allowInsecure: false
        // CORS y sticky sessions importantes para Streamlit
        stickySessions: {
          affinity: 'sticky'
        }
      }
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.name
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: acr.listCredentials().passwords[0].value
        }
      ]
    }
    template: {
      containers: [
        {
          name: appName
          image: '${acr.properties.loginServer}/${appName}:${imageTag}'
          resources: {
            cpu: json(containerCpu)
            memory: containerMemory
          }
          probes: [
            {
              type: 'Startup'
              httpGet: {
                path: '/_stcore/health'
                port: 8501
              }
              initialDelaySeconds: 60
              periodSeconds: 30
              failureThreshold: 20  // 10 min para arrancar (carga modelos GLiNER)
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/_stcore/health'
                port: 8501
              }
              periodSeconds: 30
              failureThreshold: 5
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0  // scale-to-zero: ahorra $$$ cuando nadie usa
        maxReplicas: 2  // demo no necesita mas
        rules: [
          {
            name: 'http-rule'
            http: {
              metadata: {
                concurrentRequests: '10'
              }
            }
          }
        ]
      }
    }
  }
}

// --- Outputs ---
output appUrl string = 'https://${app.properties.configuration.ingress.fqdn}'
output acrLoginServer string = acr.properties.loginServer
output acrName string = acr.name
