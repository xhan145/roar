from pathlib import Path

import yaml


WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pages.yml"
)


def load_workflow():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_pages_rebuilds_on_release_events_and_generator_contract_changes():
    """Fails if a release edit or manifest generator change cannot refresh Pages."""
    workflow = load_workflow()

    assert workflow["on"]["release"]["types"] == ["published", "edited"]
    assert workflow["permissions"] == {
        "contents": "read",
        "pages": "write",
        "id-token": "write",
    }
    assert {
        "scripts/generate_site_release_manifest.py",
        "site/data/releases.schema.json",
        ".github/workflows/pages.yml",
    } <= set(workflow["on"]["push"]["paths"])


def test_pages_generates_verified_metadata_before_uploading_the_artifact():
    """Fails if Pages uploads stale metadata instead of a fresh release manifest."""
    steps = load_workflow()["jobs"]["deploy"]["steps"]
    setup_python_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("uses") == "actions/setup-python@v5"
    )
    generation_index, generation_step = next(
        (index, step)
        for index, step in enumerate(steps)
        if step.get("name") == "Generate verified release metadata"
    )
    upload_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("uses") == "actions/upload-pages-artifact@v3"
    )

    assert setup_python_index < generation_index < upload_index
    assert generation_step["env"] == {"GH_TOKEN": "${{ github.token }}"}
    assert generation_step["run"].split() == [
        "python",
        "scripts/generate_site_release_manifest.py",
        "--repository",
        "${{",
        "github.repository",
        "}}",
        "--output",
        "site/data/releases.json",
    ]
