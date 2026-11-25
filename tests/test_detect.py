"""Tests for detect.py's level-discount note extraction (stdlib only)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import detect  # noqa: E402

# A minimal discount post: a current-week block with a level note, followed by an
# older block and the "Level N:" cost table (which must NOT be picked up).
CONTENT = """<h2>Featured Items (November 24\u2013December 1)</h2>
<p>This week, the Tortuga engineers invite Pilots to take a closer look at the following builds:</p>
<ul>
  <li><strong>War Robot Modules</strong>:&nbsp;Harpy, Tyr, Purifier</li>
  <li><strong>Weapons</strong>: Relic Orkan, Nucleon</li>
  <li><strong>Gear</strong>: Repulsor, Ghost Turret</li>
</ul>
<p><em><strong>\u2757 This week&#39;s upgrade discounts are available only for items at level 9 or higher.</strong></em></p>
<h2>Featured Items (November 17\u201324)</h2>
<ul>
  <li><strong>War Robot Modules</strong>:&nbsp;Hitcher, Relic Tyr, Scorpion</li>
  <li><strong>Weapons</strong>: Tusk, Nucleon</li>
  <li><strong>Gear</strong>: Repulsor, Emergency Shield</li>
</ul>
<h2>Upgrade Costs by Rarity</h2>
<ul>
  <li>Level 2: 3,200 Salvage (Previously 6,400 Salvage)</li>
  <li>Level 3: 6 Intel (Previously 20 Intel)</li>
</ul>
"""


class TestLevelDiscountNote(unittest.TestCase):
    def test_extracts_the_current_weeks_note(self):
        note = detect.level_discount_note(CONTENT)
        self.assertEqual(
            note,
            "This week's upgrade discounts are available only for items at level 9 or higher.",
        )

    def test_strips_leading_emoji_and_decodes_entities(self):
        # The "❗" and "&#39;" are gone; the sentence survives verbatim.
        note = detect.level_discount_note(CONTENT)
        self.assertNotIn("\u2757", note)
        self.assertNotIn("&#39;", note)
        self.assertIn("This week's", note)

    def test_never_reads_the_bottom_cost_table(self):
        # The "Level 2:" / "Level 3:" cost rows sit outside the top block, so a
        # post with no note (only the cost table) yields None.
        no_note = CONTENT.replace(
            "<p><em><strong>\u2757 This week&#39;s upgrade discounts are available only for items at level 9 or higher.</strong></em></p>",
            "",
        )
        self.assertIsNone(detect.level_discount_note(no_note))

    def test_none_for_a_week_without_any_level_mention(self):
        self.assertIsNone(detect.level_discount_note("<h2>Featured Items (November 17\u201324)</h2><ul><li><strong>Weapons</strong>: Tusk</li></ul>"))

    def test_none_for_non_discount_content(self):
        self.assertIsNone(detect.level_discount_note("<p>Patch notes for version 0.15.0</p>"))


if __name__ == "__main__":
    unittest.main()
