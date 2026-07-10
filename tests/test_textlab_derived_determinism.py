"""The FULL Rung-0-style criterion: same inputs -> byte-identical raw AND derived output
(decisions.jsonl, metrics.json, aggregate, graph JSON, DOT)."""
import os

from coliseum.textlab.graph_export import write_graphs
from coliseum.textlab.metrics import write_aggregate, write_run_metrics
from coliseum.textlab.runner import run_scenario

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCEN = lambda name: os.path.join(ROOT, "configs", "scenarios", f"{name}.yaml")
CONFIG_DIR = os.path.join(ROOT, "configs", "scenarios")


def produce(base):
    """One full pipeline pass: 2 scenarios x 2 personas -> metrics + graphs."""
    run_dirs = []
    for scen in ("corrupt_king", "corrupt_king_verifiable"):
        for persona in ("obedient", "merciful"):
            r = run_scenario(SCEN(scen), f"scripted:{persona}", 5, str(base / "runs"))
            run_dirs.append(r.run_dir)
    run_dirs = sorted(set(run_dirs))
    files = []
    for d in run_dirs:
        files.append(write_run_metrics(d, str(base / "metrics")))
        files.append(os.path.join(d, "decisions.jsonl"))
    files.append(write_aggregate(run_dirs, str(base / "metrics")))
    files.extend(write_graphs(run_dirs, str(base / "graphs")))
    return sorted(files)


def test_full_pipeline_byte_identical(tmp_path):
    files_a = produce(tmp_path / "a")
    files_b = produce(tmp_path / "b")
    assert len(files_a) == len(files_b) > 0
    for fa, fb in zip(files_a, files_b):
        assert os.path.relpath(fa, tmp_path / "a") == os.path.relpath(fb, tmp_path / "b")
        with open(fa, "rb") as f1, open(fb, "rb") as f2:
            assert f1.read() == f2.read(), f"derived output differs: {fa}"