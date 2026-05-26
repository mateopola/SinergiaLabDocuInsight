const { createClient } = require('@supabase/supabase-js');

const SUPABASE_URL = 'https://basvbmjybtuatwfztatk.supabase.co';
const CLEAN_SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJhc3ZibWp5YnR1YXR3Znp0YXRrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIyNDk5NzAsImV4cCI6MjA4NzgyNTk3MH0.AfvYYziUj6hBXRocpzljmfuRJQHDdjxZtXZigHYhLZI';

const supabase = createClient(SUPABASE_URL, CLEAN_SUPABASE_KEY);

async function seedData() {
    console.log("Seeding base configuration...");
    const records = [
        {
            tipo_documento: 'RUT',
            descripcion: 'Registro Único Tributario (Colombia)',
            prompt_sistema: 'Eres un experto contable. Documento RUT. Extrae estrictamente NIT, Razón Social y Actividad Económica',
            esquema_metadatos: {
                "nit": { "type": "string" },
                "razon_social": { "type": "string" },
                "actividad_economica_principal": { "type": "string" }
            },
            activo: true
        },
        {
            tipo_documento: 'Cámara_Comercio',
            descripcion: 'Certificado de Existencia y Representación Legal',
            prompt_sistema: 'Eres un experto legal. Documento Cámara Comercio. Extrae Nombre Empresa, Matrícula Mercantil, Fecha Constitución y Representante Legal',
            esquema_metadatos: {
                "nombre_empresa": { "type": "string" },
                "matricula_mercantil": { "type": "string" },
                "fecha_constitucion": { "type": "string" },
                "representante_legal": { "type": "string" }
            },
            activo: true
        }
    ];

    for (const record of records) {
        const { data, error } = await supabase
            .from('configuracion_documentos')
            .upsert(record, { onConflict: 'tipo_documento' });

        if (error) {
            console.error(`Error inserting ${record.tipo_documento}:`, error);
        } else {
            console.log(`Success inserting ${record.tipo_documento}`);
        }
    }
}

seedData();
