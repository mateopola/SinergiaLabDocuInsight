# Plan de diseño · DocuInsight como ecosistema 360 de documentos

> Documento vivo. Tildá `[x]` lo que vayas cerrando.
> Última actualización: 2026-05-24.

---

## 0. Visión

**DocuInsight no es una demo.** Es la plataforma de inteligencia documental de SinergIA Lab. Cubre las **9 capas** del ciclo de vida de un documento empresarial:

```
Ingesta → Preprocesamiento → Clasificación → Extracción →
Validación → Enriquecimiento → Almacenamiento → Distribución → Analítica
```

Hoy el MVP cubre clasificación + extracción sobre 4 tipologías (Cédula, Cámara de Comercio, RUT, Póliza). El roadmap completa el resto del ecosistema.

---

## 1. Estado actual del MVP (lo que ya funciona)

### Backend / pipeline
- [x] OCR híbrido: PyMuPDF para PDFs digitales, EasyOCR para escaneados ([pipeline_utils/ocr.py](pipeline_utils/ocr.py))
- [x] Re-OCR forzado para RUT digital (cajas DIAN rompen al NER)
- [x] Clasificador TF-IDF + LogReg (C-1) entrenado, test_accuracy 1.0 en 168 docs ([models/classifier/](models/classifier/))
- [x] NER por tipo: CRF para CC (F1 0.915), spaCy+CNN para CED (0.921) / POL (0.337) / RUT (0.696) ([pipeline_utils/ner.py](pipeline_utils/ner.py))
- [x] Schemas v2: 27 campos combinando NER + regex ([schemas.py](schemas.py))
- [x] Contrato `DocumentPipeline` Protocol que permite mock/real intercambiables ([pipeline.py](pipeline.py))
- [x] Export Excel multi-hoja ([export.py](export.py))

### UI / app
- [x] Estética alineada con la landing: paleta brand, Space Grotesk + Inter, glassmorphism, mesh gradients
- [x] Navbar sticky con logo, status de sesión y "← Volver al sitio"
- [x] Estructura de app con tabs: Dashboard / Procesar / Casos
- [x] Sin sidebar visible para el visitante (toggle mock/real oculto en `?dev=1`)
- [x] Procesamiento de un documento a la vez con feedback en tiempo real (`st.status`)
- [x] Render de resultado individual (tipo + confianza + métricas + tabla de entidades + OCR colapsable)
- [x] Historial de casos en sesión (acumula, filtrable por tipo, expandible)
- [x] Export Excel por documento y por sesión completa
- [x] Modo mock controlado por query param para testing rápido
- [x] Responsive básico (mobile stacks)

### Landing
- [x] Hero futurista con glassmorphism, gradientes mesh, animaciones float ([docs/](docs/))
- [x] Secciones: Solución, Capacidades, Casos de uso, Arquitectura, Equipo
- [x] CTA "Demo en vivo" apunta al Streamlit cloud deploy
- [x] Publicación en GitHub Pages

---

## 2. Roadmap por capa del ecosistema

### Capa 1 · Ingesta (cómo entran los documentos)

- [ ] **Upload manual mejorado**: drag&drop multi-formato con preview antes de procesar
- [ ] **Conector email**: bandeja IMAP que ingesta automáticamente adjuntos (precedente: BFCO)
- [ ] **Conector SharePoint / OneDrive**: monitorea carpeta y procesa nuevos
- [ ] **API REST de ingesta**: `POST /documents` para integraciones programáticas
- [ ] **Webhook entrante**: recibir desde sistemas terceros (CRM, ECM, Power Automate)
- [ ] **Carga batch CSV/ZIP**: lote grande con barra de progreso y resumen al final
- [ ] **Captura por cámara móvil**: en mobile, abrir cámara para fotografiar el documento

### Capa 2 · Preprocesamiento

- [ ] **Detección de calidad** del scan (resolución, rotación, blur) antes del OCR
- [ ] **Auto-rotación** de páginas torcidas (detección de orientación)
- [ ] **Deskew + denoise** para escaneos pobres
- [ ] **Split de PDFs multi-documento** (un PDF con cédula + RUT separa automáticamente)
- [ ] **Conversión de formatos** (HEIC, TIFF, DOCX) a PDF/imagen para procesamiento

### Capa 3 · Clasificación (lo que ya hay + mejoras)

- [x] Modelo TF-IDF + LogReg sobre 4 clases
- [ ] **Confianza calibrada** (isotonic regression o Platt scaling) — hoy es softmax cruda
- [ ] **Fallback a LLM** cuando confianza < 0.50 (en vez de marcar `DESCONOCIDO`)
- [ ] **Nuevas tipologías**: Contratos, Facturas, Estados financieros, Actas, etc.
- [ ] **Modo "auto-aprende"**: cuando un humano corrige una clasificación, se guarda como sample para reentrenar

### Capa 4 · Extracción de entidades

- [x] NER por tipo con dispatcher (CRF + spaCy+CNN)
- [x] 27 campos cubiertos (NER + regex)
- [ ] **Mejorar POL** (hoy F1 0.337) — investigar GLiNER o LayoutLM
- [ ] **Mejorar RUT** (hoy F1 0.696)
- [ ] **Entidades libres por LLM**: pedirle a GPT-4.1 mini que extraiga campos no entrenados (one-shot)
- [ ] **Bounding boxes**: además del valor, devolver coordenadas en el PDF para auditoría visual
- [ ] **Multi-página**: hoy procesa solo la 1ra página; soportar documentos largos
- [ ] **Tablas estructuradas**: extraer tablas (Facturas, Estados financieros) a DataFrame

### Capa 5 · Validación humana (HITL)

- [ ] **Workflow de revisión** para resultados con confianza < 0.85
- [ ] **Vista lado-a-lado**: PDF original a la izquierda, campos extraídos editables a la derecha
- [ ] **Sistema de "aprobar / rechazar / corregir"** con auditoría (quién, cuándo, por qué)
- [ ] **Queue de pendientes** con SLA por tipo documental
- [ ] **Override manual del tipo documental** cuando el clasificador se equivoca
- [ ] **Feedback loop**: las correcciones alimentan el dataset de reentrenamiento

### Capa 6 · Enriquecimiento

- [ ] **Validación de NIT** contra DIAN (existe + estado activo)
- [ ] **Verificación de cédula** contra Registraduría (estado vigente)
- [ ] **Cruce con Cámara de Comercio**: enriquecer con RUES (representante actual, estado matrícula)
- [ ] **Geolocalización** de direcciones extraídas (ciudad → departamento → país)
- [ ] **Normalización**: capitalización consistente, formato de fechas ISO, números limpios
- [ ] **Detección de duplicados**: hash del contenido + similitud para evitar reprocesos

### Capa 7 · Almacenamiento + búsqueda

- [ ] **Persistencia** (hoy solo en sesión) — Supabase ya está en deps
- [ ] **Base documental** con metadatos indexados (tipo, fecha, entidades, NIT, etc.)
- [ ] **Búsqueda full-text** sobre OCR + entidades
- [ ] **Búsqueda facetada**: filtrar por tipo + rango de fechas + cliente
- [ ] **Vista de "expediente"**: agrupar todos los documentos de una misma persona/empresa
- [ ] **Versionado** de documentos (re-uploads, correcciones)
- [ ] **Retención configurable** con auto-eliminación post-SLA

### Capa 8 · Distribución / workflows

- [ ] **Trigger downstream**: al procesar, disparar acción (notificar Slack, crear ticket Jira, etc.)
- [ ] **Reglas de ruteo**: "si tipo = Tutela y monto > X → buzón legal"
- [ ] **Export a CRM** (Salesforce, HubSpot)
- [ ] **Export a ECM** (AZ Digital, SharePoint)
- [ ] **Notificaciones por email** cuando un caso se completa o queda pendiente
- [ ] **Webhooks salientes** configurables
- [ ] **Conector n8n** (ya hay docker-compose) para low-code workflows

### Capa 9 · Analítica + auditoría

- [x] Dashboard de sesión: KPIs, distribución por tipo, histograma de confianza
- [ ] **Dashboard histórico** (no solo sesión) — requiere capa 7
- [ ] **Drift detection**: alertar si la distribución de tipos cambia abruptamente
- [ ] **Tracking de calidad**: % de revisiones humanas, tiempo promedio, accuracy real (con ground truth en producción)
- [ ] **Logs de auditoría**: quién subió qué, cuándo, qué se corrigió
- [ ] **Reporting programado** (Excel/PDF semanal por email)
- [ ] **API de métricas** para integrar a dashboards externos (Grafana, PowerBI)

---

## 3. Experiencia y marca (UX/UI)

### Coherencia con la landing
- [x] Misma paleta, tipografía, glassmorphism, gradientes
- [x] Brand strip + navbar sticky
- [ ] **Link a landing funcional**: hoy `LANDING_URL` es placeholder ([app.py:30](app.py#L30)) — ajustar a la URL real de GitHub Pages
- [ ] **Logo del navbar clickeable** abre la landing en la misma pestaña
- [ ] **Animaciones de transición** entre tabs (fade-in suave)
- [ ] **Estado de loading global** mientras se cargan los modelos reales por primera vez

### Onboarding y pedagogía
- [ ] **Tour guiado** la primera vez que un visitante entra (3-4 pasos: sube → procesa → revisa)
- [ ] **Tooltips** explicando qué es "confianza", "OCR", "NER" para no-técnicos
- [ ] **Sección "Cómo funciona"** con diagrama de la arquitectura (puede ser otra tab)
- [ ] **Galería de outputs** mostrando ejemplos pre-procesados para que el visitante "vea" sin subir nada

### Detalles de pulido
- [ ] **Favicon animado** o con badge cuando hay un procesamiento corriendo
- [ ] **Dark mode** (opcional, paleta inversa)
- [ ] **Internacionalización** (ES default, EN/PT opcional)
- [ ] **Accesibilidad**: ARIA labels, contraste AA, navegación por teclado
- [ ] **Empty states ilustrados** (SVG custom en vez de emoji)
- [ ] **Toast notifications** para acciones rápidas (Excel descargado, sesión limpiada)

---

## 4. Infraestructura y operación

### Deploy
- [x] Streamlit Cloud (URL pública conocida)
- [ ] **Domain custom** (ej. app.docuinsight.io o similar) en vez del subdominio `*.streamlit.app`
- [ ] **Backend separado** (FastAPI) para que el procesamiento no bloquee la UI
- [ ] **Workers asíncronos** (Celery / RQ) para batch pesado
- [ ] **CDN para assets** estáticos

### Seguridad
- [ ] **Autenticación** (Auth0 / Supabase Auth / SSO empresarial)
- [ ] **RBAC**: roles operador / revisor / admin
- [ ] **Audit log** inmutable
- [ ] **Encriptación at-rest** de documentos almacenados
- [ ] **DLP**: validar que ningún dato sensible salga a servicios externos sin aprobación
- [ ] **Sanitización de uploads**: scan antivirus, validación de mime real (no solo extensión)

### Performance
- [ ] **Cache de resultados** por hash del documento (no reprocesar el mismo PDF)
- [ ] **Lazy load** de modelos (no cargar spaCy hasta primera clasificación que lo necesite)
- [ ] **GPU para EasyOCR** en producción (ahora CPU)
- [ ] **Métricas de p95 latency** por tipo documental

---

## 5. Negocio y go-to-market

- [ ] **Pricing page** en la landing (planes Free / Pro / Enterprise)
- [ ] **Calculadora de ROI** (cuántos FTEs se reemplazan, ahorro estimado)
- [ ] **Casos de éxito** documentados (mínimo 2 testimonios)
- [ ] **Whitepaper técnico** sobre la arquitectura
- [ ] **Demo agendable** (Calendly) además de la "Demo en vivo" interactiva
- [ ] **Integraciones marketplace** (Zapier, Make, n8n templates)

---

## 6. Próximos sprints sugeridos (priorización)

### Sprint 1 · Cerrar el loop de la demo (1 semana)
- [ ] Ajustar `LANDING_URL` real
- [ ] Validar pipeline real end-to-end con los modelos en `models/`
- [ ] Testear los 4 tipos con un documento real de cada uno
- [ ] Deploy a Streamlit Cloud
- [ ] Verificar que el flujo landing → Streamlit funciona sin fricción

### Sprint 2 · Capa de persistencia (2 semanas)
- [ ] Schema Supabase para documentos + entidades
- [ ] Migrar `st.session_state.history` a Supabase
- [ ] Dashboard histórico (no solo sesión)
- [ ] Búsqueda básica por filename / tipo

### Sprint 3 · Validación humana (2 semanas)
- [ ] Queue de pendientes (confianza < 0.85)
- [ ] Vista PDF + campos editables lado a lado
- [ ] Auditoría de correcciones

### Sprint 4 · Onboarding visitante (1 semana)
- [ ] Tour guiado primera visita
- [ ] Galería de outputs pre-cargados
- [ ] Tooltips pedagógicos

---

## 7. Riesgos abiertos

- [ ] **POL F1 0.337** es demasiado bajo para producción — buscar alternativa (GLiNER, LayoutLM, o aceptar revisión humana obligatoria en pólizas)
- [ ] **Costo de EasyOCR en CPU** puede romper SLAs si el volumen sube
- [ ] **Sin DLP review** todavía — bloquea cualquier cliente enterprise
- [ ] **Sin pricing definido** — la pregunta "¿cuánto cuesta?" no tiene respuesta hoy
- [ ] **El repo mezcla 3 cosas** (app Streamlit, landing, dashboard viejo, docker n8n) — limpieza pendiente
