-- =============================================
-- DocuInsight: Migración de esquema FINAL
-- Ejecutar en Supabase SQL Editor (https://supabase.com/dashboard)
-- =============================================

-- 1. Eliminar columnas sin uso
ALTER TABLE trazabilidad_procesos DROP COLUMN IF EXISTS observaciones;
ALTER TABLE trazabilidad_procesos DROP COLUMN IF EXISTS hora_inicio;
ALTER TABLE trazabilidad_procesos DROP COLUMN IF EXISTS hora_fin;

-- 2. Agregar columna de confianza IA
ALTER TABLE trazabilidad_procesos ADD COLUMN IF NOT EXISTS confianza_general NUMERIC;

-- 3. Índice para búsquedas rápidas por categoría
CREATE INDEX IF NOT EXISTS idx_trazabilidad_categoria
ON trazabilidad_procesos (categoria_detectada);

-- 4. Verificar estructura final (columnas esperadas):
-- id_registro, id_caso, fase, fecha, nombre_archivo, resultado_ia, categoria_detectada, confianza_general
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'trazabilidad_procesos'
ORDER BY ordinal_position;
