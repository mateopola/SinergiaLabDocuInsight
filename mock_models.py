"""
Pipeline mock para desarrollo de la interfaz.

Genera resultados falsos pero realistas (con datos típicos colombianos)
para que la UI se pueda desarrollar y demostrar sin depender de los
modelos reales. Cuando RealPipeline esté listo, este archivo se mantiene
para tests y demos sin internet/GPU.
"""

from __future__ import annotations

import random
import time

from schemas import DocType, DocumentResult, Entity


# Plantillas de datos realistas para cada tipo documental.
# Mantener solo los campos que el UI espera (ver EXPECTED_ENTITIES en schemas.py).
_FAKE_DATA = {
    DocType.CEDULA: [
        {
            "nombres": "JUAN CARLOS",
            "apellidos": "PÉREZ GÓMEZ",
            "numero_cedula": "1.020.345.678",
            "lugar_expedicion": "BOGOTÁ D.C.",
            "fecha_expedicion": "20-04-2003",
        },
        {
            "nombres": "MARÍA FERNANDA",
            "apellidos": "RODRÍGUEZ LÓPEZ",
            "numero_cedula": "52.789.123",
            "lugar_expedicion": "MEDELLÍN, ANTIOQUIA",
            "fecha_expedicion": "12-12-2008",
        },
        {
            "nombres": "ANDRÉS FELIPE",
            "apellidos": "MARTÍNEZ TORRES",
            "numero_cedula": "1.098.456.321",
            "lugar_expedicion": "CALI, VALLE",
            "fecha_expedicion": "30-07-2010",
        },
    ],
    DocType.RUT: [
        {
            "nit": "900.123.456-7",
            "razon_social": "SINERGIA LAB S.A.S.",
            "direccion": "CALLE 100 # 15-50 OF 502, BOGOTÁ D.C.",
            "actividad_economica_ciiu": "6201 - Actividades de desarrollo de sistemas informáticos",
        },
        {
            "nit": "830.456.789-2",
            "razon_social": "INVERSIONES DEL ANDES S.A.",
            "direccion": "CARRERA 7 # 99-53, BOGOTÁ D.C.",
            "actividad_economica_ciiu": "6810 - Actividades inmobiliarias",
        },
    ],
    DocType.CAMARA_COMERCIO: [
        {
            "razon_social": "TECNOLOGÍAS INNOVADORAS S.A.S.",
            "nit": "901.456.789-3",
            "numero_matricula": "01234567",
            "fecha_constitucion": "12-01-2020",
            "representante_legal": "ANA MARÍA RODRÍGUEZ CASTRO",
        },
        {
            "razon_social": "DISTRIBUIDORA CENTRAL LTDA.",
            "nit": "860.789.012-5",
            "numero_matricula": "00876543",
            "fecha_constitucion": "05-08-2015",
            "representante_legal": "CARLOS ALBERTO MUÑOZ",
        },
    ],
    DocType.POLIZA: [
        {
            "asegurado": "EMPRESA EJEMPLO S.A.S.",
            "tomador": "EMPRESA EJEMPLO S.A.S.",
            "prima": "$ 4.500.000",
            "numero_poliza": "P-2025-001234",
        },
        {
            "asegurado": "JUAN CARLOS PÉREZ",
            "tomador": "JUAN CARLOS PÉREZ",
            "prima": "$ 1.200.000",
            "numero_poliza": "VID-789456",
        },
    ],
}


class MockPipeline:
    """Simula el comportamiento del pipeline real para desarrollo de UI."""

    def process(self, file_bytes: bytes, filename: str) -> DocumentResult:
        start = time.time()

        # Simular tiempo de procesamiento
        time.sleep(random.uniform(0.3, 1.2))

        # Simular error en ~5% de los casos
        if random.random() < 0.05:
            return DocumentResult(
                filename=filename,
                doc_type=DocType.DESCONOCIDO,
                doc_type_confidence=0.0,
                extracted_text="",
                error="OCR fallido: imagen ilegible o documento dañado",
                processing_time_ms=int((time.time() - start) * 1000),
            )

        # Inferir tipo desde el nombre del archivo si hay pistas; si no, aleatorio
        doc_type = self._guess_type_from_filename(filename)
        confidence = random.uniform(0.78, 0.99)

        # Tomar una plantilla y generar entidades
        templates = _FAKE_DATA.get(doc_type, [])
        if not templates:
            entities = []
        else:
            template = random.choice(templates)
            entities = []
            for label, value in template.items():
                # Simular 90% de extracción exitosa por entidad
                if random.random() > 0.10:
                    entities.append(
                        Entity(
                            label=label,
                            value=value,
                            confidence=random.uniform(0.70, 0.99),
                        )
                    )

        return DocumentResult(
            filename=filename,
            doc_type=doc_type,
            doc_type_confidence=confidence,
            extracted_text=f"[Texto OCR simulado de {filename}]\n\n"
                           f"Documento de tipo {doc_type.value} con "
                           f"{len(entities)} entidades extraídas.",
            entities=entities,
            processing_time_ms=int((time.time() - start) * 1000),
        )

    @staticmethod
    def _guess_type_from_filename(filename: str) -> DocType:
        lower = filename.lower()
        if "cedula" in lower or "_cc" in lower or "cc_" in lower:
            return DocType.CEDULA
        if "rut" in lower:
            return DocType.RUT
        if "camara" in lower or "ccc" in lower or "comercio" in lower:
            return DocType.CAMARA_COMERCIO
        if "poliza" in lower or "seguro" in lower:
            return DocType.POLIZA
        # Sin pistas, escoger uno al azar entre los 4 válidos
        return random.choice([
            DocType.CEDULA,
            DocType.RUT,
            DocType.CAMARA_COMERCIO,
            DocType.POLIZA,
        ])
