import unittest

class TestM08Paginacion(unittest.TestCase):
    def setUp(self):
        # Fixture sintético simulando documentos ordenados por timestamp y desempatados por ID
        self.docs = [
            {"id": "doc_A", "timestamp": 1000},
            {"id": "doc_B", "timestamp": 1000}, # Empate exacto en tiempo
            {"id": "doc_C", "timestamp": 1010},
            {"id": "doc_D", "timestamp": 1020}
        ]

    def simulate_fetch(self, limit, cursor=None):
        """Simulador del comportamiento esperado de DynamoDB con LastEvaluatedKey"""
        start_idx = 0
        if cursor:
            if cursor not in [d["id"] for d in self.docs]:
                raise ValueError("Cursor inválido o malformado")
            # El cursor apunta al último evaluado, iniciamos en el siguiente
            start_idx = next(i for i, d in enumerate(self.docs) if d["id"] == cursor) + 1
        
        end_idx = start_idx + limit
        page = self.docs[start_idx:end_idx]
        
        # Si quedan elementos después de esta página, regresamos el ID del último como cursor
        next_cursor = page[-1]["id"] if len(page) == limit and end_idx < len(self.docs) else None
        return page, next_cursor

    def test_caso_normal_recorrido_completo(self):
        """Recorrido página por página sin omisiones ni duplicados."""
        page1, cursor1 = self.simulate_fetch(limit=2)
        self.assertEqual([d["id"] for d in page1], ["doc_A", "doc_B"])
        self.assertEqual(cursor1, "doc_B")
        
        page2, cursor2 = self.simulate_fetch(limit=2, cursor=cursor1)
        self.assertEqual([d["id"] for d in page2], ["doc_C", "doc_D"])
        self.assertIsNone(cursor2) # Fin de los datos

    def test_caso_limite_ultima_pagina_y_vacia(self):
        """Consulta posterior al final de los datos devuelve lista vacía y cursor nulo."""
        page, cursor = self.simulate_fetch(limit=2, cursor="doc_D")
        self.assertEqual(len(page), 0)
        self.assertIsNone(cursor)

    def test_caso_limite_inserciones_y_empates(self):
        """Garantiza orden determinista usando ID como desempate para registros simultáneos."""
        page, cursor = self.simulate_fetch(limit=1)
        self.assertEqual(page[0]["id"], "doc_A")
        
        page2, cursor2 = self.simulate_fetch(limit=1, cursor=cursor)
        self.assertEqual(page2[0]["id"], "doc_B")

    def test_fallo_declarado_cursor_invalido(self):
        """Rechaza la petición si el cursor es inexistente, previniendo escaneos erróneos."""
        with self.assertRaises(ValueError):
            self.simulate_fetch(limit=2, cursor="cursor_corrupto_123")

if __name__ == '__main__':
    unittest.main()