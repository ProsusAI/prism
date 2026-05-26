"""Tests for phase-2 validation parse fallback and rotation gating."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


def _setup_project(tmpdir: Path, project_id: str = "proj1"):
    import lib.config as config

    home = Path(tmpdir)
    config.PRISM_HOME = home
    engrams = home / "projects" / project_id / "engrams"
    candidates = home / "projects" / project_id / "candidates"
    engrams.mkdir(parents=True)
    candidates.mkdir(parents=True)
    return home, engrams, candidates


def test_parse_failure_does_not_count_stale_engrams():
    from lib.extract import _infer_results_from_snapshot, _parse_validation_output, _take_validation_snapshot

    with tempfile.TemporaryDirectory() as tmpdir:
        home, engrams, candidates = _setup_project(Path(tmpdir))
        (engrams / "old-engram.md").write_text("---\nid: old\n---\n")
        (candidates / "new-cand.md").write_text("---\nid: new-cand\n---\n")

        snapshot = _take_validation_snapshot("proj1")
        (engrams / "new-cand.md").write_text("---\nid: new-cand\n---\n")
        candidates.joinpath("new-cand.md").unlink(missing_ok=True)

        inferred = _infer_results_from_snapshot("proj1", snapshot, n_candidates=1)
        assert inferred["parse_failed"] is True
        assert inferred["approved"] == 1
        assert inferred["rejected"] == 0

        with patch("lib.extract.PRISM_HOME", home):
            results = _parse_validation_output("not json at all", "proj1", snapshot, 1)
        assert results["parse_failed"] is True
        assert results["approved"] == 1
        assert results["approved"] != len(list(engrams.glob("*.md")))


def test_parse_failure_keeps_observations_when_candidates_remain():
    from lib.extract import _infer_results_from_snapshot, _should_rotate_observations

    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_project(Path(tmpdir))
        snapshot = {
            "engrams_before": set(),
            "candidates_before": {"a.md", "b.md"},
        }
        # Sonnet approved one but left b.md in candidates
        results = {
            "parse_failed": True,
            "new_engram_names": {"a.md"},
            "candidates_remaining": {"b.md"},
            "approved": 1,
            "rejected": 0,
            "modified": 0,
        }
        assert _should_rotate_observations(results, n_candidates=2, project_id="proj1") is False


def test_parse_failure_rotates_when_all_candidates_cleared():
    from lib.extract import _infer_results_from_snapshot, _should_rotate_observations

    with tempfile.TemporaryDirectory() as tmpdir:
        home, engrams, candidates = _setup_project(Path(tmpdir))
        (candidates / "only.md").write_text("---\n---\n")
        snapshot = {
            "engrams_before": set(),
            "candidates_before": {"only.md"},
        }
        (engrams / "only.md").write_text("---\n---\n")
        (candidates / "only.md").unlink()

        results = _infer_results_from_snapshot("proj1", snapshot, n_candidates=1)
        assert results["candidates_remaining"] == set()
        assert _should_rotate_observations(results, n_candidates=1, project_id="proj1") is True


def test_merge_file_entry_preserves_index_reinforcement():
    from lib.index import merge_file_entry_with_index

    existing = {
        "id": "foo",
        "confidence": 0.72,
        "evidence_count": 5,
        "last_observed": "2026-05-19",
        "source": "lens",
        "success_count": 2,
        "failure_count": 0,
        "pinned": False,
    }
    file_entry = {
        "id": "foo",
        "kind": "preference",
        "trigger": "updated trigger",
        "confidence": 0.5,
        "evidence_count": 1,
        "last_observed": "2020-01-01",
        "success_count": 0,
        "failure_count": 0,
        "pinned": False,
    }
    merged = merge_file_entry_with_index(file_entry, existing)
    assert merged["confidence"] == 0.72
    assert merged["evidence_count"] == 5
    assert merged["last_observed"] == "2026-05-19"
    assert merged["trigger"] == "updated trigger"
    assert merged["source"] == "lens"
    assert merged["success_count"] == 2


def test_deprecate_deletes_file_before_reindex():
    """Deprecated engrams are deleted on disk and stay out of the index after rescan."""
    import lib.index as index_mod
    from lib.extract import _apply_validation_results
    from lib.index import get_entry, load_index

    with tempfile.TemporaryDirectory() as tmpdir:
        home, engrams, _candidates = _setup_project(Path(tmpdir))
        old_id = "use-npm-for-installs"
        old_path = engrams / f"{old_id}.md"
        old_path.write_text(f"---\nid: {old_id}\nkind: preference\n---\nOld rule\n")

        rel = str(old_path.relative_to(home))
        (home / "index.json").write_text(json.dumps({
            "engrams": [{
                "id": old_id,
                "kind": "preference",
                "trigger": "use npm",
                "confidence": 0.8,
                "domain": "general",
                "scope": "project",
                "project_id": "proj1",
                "path": rel,
            }],
        }) + "\n")

        results = {
            "decisions": [{
                "candidate_id": "use-pnpm-for-installs",
                "decision": "APPROVED",
                "deprecates": [old_id],
            }],
        }
        with patch("lib.extract.PRISM_HOME", home), patch.object(index_mod, "PRISM_HOME", home):
            assert get_entry(old_id) is not None
            _apply_validation_results("proj1", results, rotate=False)

        assert not old_path.exists()
        with patch.object(index_mod, "PRISM_HOME", home):
            assert get_entry(old_id) is None
            index = load_index()
        ids = {e["id"] for e in index.get("engrams", [])}
        assert old_id not in ids


def test_successful_json_parse_not_parse_failed():
    from lib.extract import _parse_validation_output, _should_rotate_observations

    with tempfile.TemporaryDirectory() as tmpdir:
        _setup_project(Path(tmpdir))
        snapshot = {"engrams_before": set(), "candidates_before": {"x.md"}}
        payload = json.dumps([
            {"candidate_id": "x", "decision": "APPROVED", "gates": {}, "deprecates": []},
        ])
        output = f"```json\n{payload}\n```"
        with patch("lib.extract._log_validation"), patch("lib.extract.PRISM_HOME", Path(tmpdir)):
            results = _parse_validation_output(output, "proj1", snapshot, 1)
        assert results.get("parse_failed") is False
        assert results["approved"] == 1
        assert _should_rotate_observations(results, 1, "proj1") is True


if __name__ == "__main__":
    test_deprecate_deletes_file_before_reindex()
    print("PASS: test_deprecate_deletes_file_before_reindex")
    test_merge_file_entry_preserves_index_reinforcement()
    print("PASS: test_merge_file_entry_preserves_index_reinforcement")
    test_parse_failure_does_not_count_stale_engrams()
    print("PASS: test_parse_failure_does_not_count_stale_engrams")
    test_parse_failure_keeps_observations_when_candidates_remain()
    print("PASS: test_parse_failure_keeps_observations_when_candidates_remain")
    test_parse_failure_rotates_when_all_candidates_cleared()
    print("PASS: test_parse_failure_rotates_when_all_candidates_cleared")
    test_successful_json_parse_not_parse_failed()
    print("PASS: test_successful_json_parse_not_parse_failed")
    print("\nAll extract validation tests passed!")
