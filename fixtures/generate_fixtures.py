import json
import csv
import os
import random

def generar_datos():
    # Asegurar que el directorio de salida exista
    os.makedirs('fixtures', exist_ok=True)
    num_registros = 1000

    print("Generando fixtures para los 4 paradigmas...")

    # 1. Document Store (JSON)
    docs = [
        {
            "id": f"doc_{i}",
            "tipo": "usuario",
            "perfil": {"nombre": f"User{i}", "edad": random.randint(18, 65)},
            "metadatos": {"activo": i % 2 == 0}
        } for i in range(num_registros)
    ]
    with open('fixtures/document_data.json', 'w') as f:
        json.dump(docs, f, indent=2)

    # 2. Graph Store (Nodos y Relaciones en JSON)
    nodos = [{"id": i, "label": "Usuario"} for i in range(num_registros)]
    relaciones = [{"origen": random.randint(0, num_registros-1), "destino": random.randint(0, num_registros-1), "tipo": "CONOCE_A"} for _ in range(num_registros * 2)]
    with open('fixtures/graph_data.json', 'w') as f:
        json.dump({"nodos": nodos, "relaciones": relaciones}, f, indent=2)

    # 3. Column Store (CSV)
    with open('fixtures/column_data.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["id_evento", "id_usuario", "accion", "timestamp"])
        for i in range(num_registros):
            writer.writerow([i, f"usr_{i}", "CLICK", f"2026-09-27T10:00:{i%60:02d}Z"])

    # 4. Object Store (Archivo Binario Pesado - 5MB)
    with open('fixtures/object_blob.bin', 'wb') as f:
        f.write(os.urandom(5 * 1024 * 1024))

    print("✅ Fixtures generados correctamente en la carpeta /fixtures")

if __name__ == "__main__":
    generar_datos()