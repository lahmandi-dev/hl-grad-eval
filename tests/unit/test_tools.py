"""Unit tests for employee evaluation tools."""

import unittest
from app.tools import tool_read, tool_write


class TestEmployeeTools(unittest.TestCase):
    def test_tool_read_valid_employee(self):
        result = tool_read(id="EMP-001")
        self.assertEqual(result["status"], "success")
        self.assertIn("employee", result)
        emp = result["employee"]
        self.assertEqual(emp["id"], "EMP-001")
        self.assertEqual(emp["nom"], "Martin")
        self.assertEqual(emp["prénom"], "Claire")
        self.assertIn("notation-prec", emp)

    def test_tool_read_by_name(self):
        result = tool_read(nom="Martin", prenom="Claire")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["employee"]["id"], "EMP-001")

    def test_tool_read_not_found(self):
        result = tool_read(id="EMP-99999")
        self.assertEqual(result["status"], "not_found")

    def test_tool_write_invalid_grade(self):
        result = tool_write(notation="Z", id="EMP-001")
        self.assertEqual(result["status"], "error")
        self.assertIn("invalide", result["message"])

    def test_tool_write_valid_grade(self):
        result = tool_write(notation="A", id="EMP-001")
        self.assertEqual(result["status"], "success")
        # Verify read reflects update
        read_res = tool_read(id="EMP-001")
        self.assertEqual(read_res["employee"]["notation-encours"], "A")


if __name__ == "__main__":
    unittest.main()
