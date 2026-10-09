import unittest
from dotenv import load_dotenv

load_dotenv()
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agent import root_agent, hl_search_employee, hl_write_employee


class TestMultiAgentSystem(unittest.IsolatedAsyncioTestCase):
    def test_agent_structure(self):
        self.assertEqual(root_agent.name, "hl_manager")
        self.assertEqual(len(root_agent.tools), 2)
        tool_names = [getattr(t, "name", t.__name__) for t in root_agent.tools]
        self.assertIn("hl_tool_read_employee", tool_names)
        self.assertIn("hl_tool_write_employee", tool_names)

        self.assertEqual(hl_search_employee.name, "hl_search_employee")
        self.assertEqual(len(hl_search_employee.tools), 1)
        self.assertEqual(
            getattr(hl_search_employee.tools[0], "name", hl_search_employee.tools[0].__name__),
            "tool_read"
        )

        self.assertEqual(hl_write_employee.name, "hl_write_employee")
        self.assertEqual(len(hl_write_employee.tools), 1)
        self.assertEqual(
            getattr(hl_write_employee.tools[0], "name", hl_write_employee.tools[0].__name__),
            "tool_write"
        )

    async def test_end_to_end_evaluation_flow(self):
        runner = Runner(
            agent=root_agent,
            session_service=InMemorySessionService(),
            app_name="test_eval_app"
        )
        session = await runner.session_service.create_session(app_name="test_eval_app", user_id="test_user")

        # Step 1: Propose evaluation
        prompt_1 = "Peux-tu regarder le dossier de Alexandre Richard (EMP-005) ? Il a atteint tous ses objectifs et montre une belle progression."
        c1 = types.Content(role="user", parts=[types.Part.from_text(text=prompt_1)])
        resp_text_1 = []
        async for event in runner.run_async(session_id=session.id, user_id="test_user", new_message=c1):
            if event.content and event.content.parts:
                for p in event.content.parts:
                    if p.text:
                        resp_text_1.append(p.text)
        full_resp_1 = " ".join(resp_text_1)
        self.assertGreater(len(full_resp_1), 0)
        self.assertTrue(any(term in full_resp_1.lower() for term in ["propos", "note", "valid", "accord"]))

        # Step 2: Validate evaluation
        prompt_2 = "Je valide cette notation, enregistre-la s'il te plaît."
        c2 = types.Content(role="user", parts=[types.Part.from_text(text=prompt_2)])
        resp_text_2 = []
        async for event in runner.run_async(session_id=session.id, user_id="test_user", new_message=c2):
            if event.content and event.content.parts:
                for p in event.content.parts:
                    if p.text:
                        resp_text_2.append(p.text)
        full_resp_2 = " ".join(resp_text_2)
        self.assertTrue(any(term in full_resp_2.lower() for term in ["enregistr", "succès", "noté", "mise à jour", "a bien été"]))

        await runner.close()


if __name__ == "__main__":
    unittest.main()
