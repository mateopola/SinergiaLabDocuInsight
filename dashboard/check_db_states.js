const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');

const SUPABASE_URL = 'https://basvbmjybtuatwfztatk.supabase.co';
const CLEAN_SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJhc3ZibWp5YnR1YXR3Znp0YXRrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIyNDk5NzAsImV4cCI6MjA4NzgyNTk3MH0.AfvYYziUj6hBXRocpzljmfuRJQHDdjxZtXZigHYhLZI';

const supabase = createClient(SUPABASE_URL, CLEAN_SUPABASE_KEY);

async function checkStates() {
    const { data, error } = await supabase
        .from('trazabilidad_procesos')
        .select('fase');

    if (error) {
        console.error("Error retrieving data:", error);
        return;
    }

    const counts = {};
    for (const d of data) {
        counts[d.fase] = (counts[d.fase] || 0) + 1;
    }

    fs.writeFileSync('db_states.json', JSON.stringify(counts, null, 2));
    console.log("Written to db_states.json");
}

checkStates();
