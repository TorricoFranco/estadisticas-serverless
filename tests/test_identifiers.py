from estadisticas.identifiers import data_hash_for, match_id_for


def test_match_id_is_16_lowercase_hex_characters():
    match_id = match_id_for("liga-profesional", 2026, 5, "boca-juniors", "river-plate")
    assert len(match_id) == 16
    assert all(char in "0123456789abcdef" for char in match_id)


def test_match_id_is_stable_for_the_same_match():
    first = match_id_for("liga-profesional", 2026, 5, "boca-juniors", "river-plate")
    second = match_id_for("liga-profesional", 2026, 5, "boca-juniors", "river-plate")
    assert first == second


def test_match_id_depends_on_the_order_of_home_and_away():
    direct = match_id_for("liga-profesional", 2026, 5, "boca-juniors", "river-plate")
    reversed_ = match_id_for("liga-profesional", 2026, 5, "river-plate", "boca-juniors")
    assert direct != reversed_


def test_data_hash_is_a_full_sha256_and_stable():
    first = data_hash_for("2026-03-14", "Boca Juniors", "River Plate", 2, 1)
    second = data_hash_for("2026-03-14", "Boca Juniors", "River Plate", 2, 1)
    assert first == second
    assert len(first) == 64


def test_data_hash_changes_when_a_goal_changes():
    before = data_hash_for("2026-03-14", "Boca Juniors", "River Plate", 2, 1)
    after = data_hash_for("2026-03-14", "Boca Juniors", "River Plate", 3, 1)
    assert before != after
