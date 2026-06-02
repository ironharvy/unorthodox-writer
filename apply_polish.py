"""Apply Phase-5 line-edit polish to novel.md via exact, verified replacements."""
from pathlib import Path

p = Path(__file__).resolve().parent / "novel.md"
text = p.read_text(encoding="utf-8")

EM = "—"  # em dash, matching the file

edits = [
    # 1. Ch1: add a logbook beat (deepen routine; lift count over 800).
    (
        f"a sound like a distant bell struck underwater.\n\nThe beam reached its apex",
        "a sound like a distant bell struck underwater.\n\n"
        "I logged the hour in the book, the way I had logged every hour for fourteen years"
        f"{EM}the wind, the visibility, the temper of the sea. My hand had not changed. The "
        "entries had not changed. A stranger turning the pages would find no difference between "
        "tonight and a night ten years gone, and that was the whole of it. A keeper's life is "
        "measured in sameness. The sea respects nothing else.\n\nThe beam reached its apex",
    ),
    # 2. Ch3: break "I looked / I looked" + fix gray-on-wrists oddity.
    (
        "I looked at the ember. I looked at my hands. The gray had spread to my wrists, the backs of my fingers.",
        "I looked at the ember, then down at my own hands. The skin across the backs of them had "
        f"gone thin, the veins standing up like cord{EM}older hands than the ones I had carried "
        "through on the first night.",
    ),
    # 3. Ch3: break "I thought of / I thought of / I thought of" triplet + drop redundant wife beat.
    (
        f"I did not have an answer. Not one I could speak aloud. I thought of the lighthouse, the "
        f"clockwork, the years of solitude. I thought of the storm and the ship and the woman I had "
        f"failed. I thought of the gray in my hair, spreading like a tide, and how I did not mind it "
        f"as much as I should.",
        "I did not have an answer. Not one I could speak aloud. The truth lived somewhere in the "
        "silence of the tower, in the years I had spent winding a spring for ships that never learned "
        f"my name, in the gray spreading through my hair like a slow tide{EM}which I found, to my own "
        "unease, I did not mind nearly as much as I should.",
    ),
    # 4. Ch4: remove second "gray spread to [parts]"; make it general toll.
    (
        f"I looked at her. The cracks in her skin had deepened. The gray in my hair had spread to my "
        f"chest, my shoulders, the backs of my hands.",
        "I looked at her. The cracks in her skin had deepened. And the crossings had marked me too"
        f"{EM}the toll written in the slack of my hands, the deepening lines, the ache that had "
        "settled into the joints and would not lift.",
    ),
    # 5. Ch4: vary the second "fingers left no mark".
    (
        "She touched the glass. Her fingers left no mark.\n\n\"Come with me,\" she said.",
        f"She touched the glass, and even that seemed to cost her{EM}her hand thinner than before, "
        "as if she were being worn away from the far side.\n\n\"Come with me,\" she said.",
    ),
    # 6. Ch5: Mira's affliction is the Stilling (cracks), not Elias's crossing-cost (gray hair).
    (
        f"I looked at her. The gray streaks in her hair had spread. Her eyes were the same{EM}dark, "
        f"urgent, exact{EM}but they were fading, the color bleeding out like ink in water.",
        "I looked at her. The cracks had reached her jaw now, fine as the crazing on old glaze. Her "
        f"eyes were the same{EM}dark, urgent, exact{EM}but the color was bleeding out of them, like "
        "ink dropped into water.",
    ),
    # 7. Ch5 ending: end on resolve (no premature crossing), kill "I did not / I did not / I did not"
    #    triplet, remove the redundant second send-off and the confused descent.
    (
        f"I stood before the lens. The beam turned. The portal opened. The light shimmered, violet "
        f"and black, and I saw Umbra{EM}the ashen plain, the violet sky, the line of cold creeping "
        f"through the city.\n\n"
        f"I did not polish the glass. I did not wind the spring. I did not check the oil.\n\n"
        f"I stood there, watching the light turn, and I thought about what I would leave behind. The "
        f"tower. The sea. The boot on the table. The years I had spent trying to atone for a night I "
        f"could not change.\n\n"
        f"I turned and walked to the stairs.\n\n"
        f"She was waiting at the base, barely visible in the dim light, a crack in the air that might "
        f"have been a woman.\n\n"
        f"\"Stay here,\" I said. \"I have things to settle.\"\n\n"
        f"She did not speak. She only watched as I descended past her into the dark.",
        "I stood before the lens a while longer. The beam turned, and at the apex the portal opened, "
        f"and through the shimmer I saw Umbra waiting{EM}the ashen plain, the violet sky, the line of "
        "cold creeping through the streets. For the first time in fourteen years, I set down the "
        "polishing cloth and left the work undone.\n\n"
        "What I would leave behind I could count on one hand. The tower. The sea. The boot on the "
        "table. The years I had burned trying to undo a single night that would not be undone.\n\n"
        "But there were things to settle first. A letter to write. A light to put out cleanly, so "
        "that no keeper would be sent in my place to die relighting it.\n\n"
        "I turned from the lens and went to find paper and pen.",
    ),
    # 8. Ch6: narrate the crossing once; kill the "tore/tore/tear" pileup and doubled crossing.
    (
        f"\"Now,\" I said.\n\n"
        f"We stepped forward together, our hands touching the glass, and the light tore.\n\n"
        f"Behind us, the wrench caught. The gears screamed. The teeth sheared and scattered across "
        f"the floor. The housing buckled. The clockwork seized, and the lens stopped, and the light "
        f"died.\n\n"
        f"The crossing was different this time. The light did not bend around me{EM}it tore, and I "
        f"felt it tear, a ripping sensation in my chest that left me gasping on the ashen ground of "
        f"Umbra. Mira helped me to my feet. Her hands were shaking.",
        "\"Now,\" I said.\n\n"
        "We stepped forward together, our hands flat against the glass. The light did not part for me "
        f"the way it had before{EM}it tore, and I felt it tear, a ripping in my chest that drove the "
        "breath out of me.\n\n"
        "Behind us the wrench caught. The gears screamed, the teeth sheared and scattered across the "
        "floor, the housing buckled. The clockwork seized, the lens stopped, and the light died.\n\n"
        "Then there was only ash. I was on my knees on the cold ground of Umbra, gasping, and Mira "
        "was pulling me upright. Her hands were shaking.",
    ),
    # 9. Ch7: vary the second "no larger than a walnut".
    (
        f"the ember sat at my feet on a pedestal of fused ash. It was no larger than a walnut. A "
        f"single coal, barely glowing, with veins of black running through its core like cracks in "
        f"dry earth.",
        "the ember sat at my feet on a pedestal of fused ash. It had shrunk even since I crossed the "
        f"plain to reach it{EM}a single coal, barely glowing, its core veined with black like cracks "
        "in dry earth.",
    ),
    # 10. Ch7: keep "field of stars" for the blooms but drop the clashing "constellation of lights".
    (
        "They covered the soil like a field of stars, a constellation of lights that stretched to "
        "the horizon. And beyond them, farther still, I saw other points of light.",
        "They covered the soil like a field of cold stars, laid across the dark all the way to the "
        "horizon. And beyond them, farther still, I saw other points of light.",
    ),
    # 11. Ch7: break the final "I looked / I looked / I looked" triplet.
    (
        "I looked at the lights. I looked at the blooms. I looked at the small sun above the cage, "
        "pulsing with a steady, gentle rhythm.",
        "I looked from the distant lights to the blooms at my feet, and finally up to the small sun "
        "above the cage, pulsing with its steady, gentle rhythm.",
    ),
]

for i, (old, new) in enumerate(edits, 1):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"Edit {i}: expected exactly 1 match, found {n}.\n--- old ---\n{old[:200]}")
    text = text.replace(old, new)

p.write_text(text, encoding="utf-8")
print("All", len(edits), "edits applied cleanly.")
print("Word count:", len(text.split()))
