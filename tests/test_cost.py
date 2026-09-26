import tempfile
import unittest
from pathlib import Path

from saylo.cost import Charge, Ledger, money


class CostTests(unittest.TestCase):
    def test_panel_adds_jev_and_translation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory) / "usage.json")
            ledger.add(7, "jev", Charge(0.00000042, input_tokens=10))
            ledger.add(7, "llm", Charge(0.00001000, input_tokens=20, output_tokens=5))

            reloaded = Ledger(Path(directory) / "usage.json")
            panel = reloaded.panel(7)

        self.assertIn(money(0.00001042), panel)
        self.assertIn("calls: 1", panel)
        self.assertIn("Kokoro speech is local and free.", panel)
        self.assertNotIn("estimates", panel)

    def test_missing_user_is_zero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory) / "usage.json")
            self.assertEqual(ledger.get(1).total_usd, 0.0)

    def test_estimated_cost_is_marked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory) / "usage.json")
            ledger.add(3, "jev", Charge(0.01, estimated=True))
            self.assertIn("estimates", ledger.panel(3))


if __name__ == "__main__":
    unittest.main()
