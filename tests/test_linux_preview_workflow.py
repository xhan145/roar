from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "linux-preview.yml"


def load_workflow():
    with WORKFLOW.open(encoding="utf-8") as workflow_file:
        return yaml.load(workflow_file, Loader=yaml.BaseLoader)


def steps_by_name(job):
    return {step.get("name"): step for step in job["steps"] if "name" in step}


def test_linux_preview_build_is_read_only_and_uploads_verified_assets():
    workflow = load_workflow()
    build = workflow["jobs"]["build"]

    assert build["runs-on"] == "ubuntu-24.04"
    assert build["permissions"] == {"contents": "read"}
    assert build["steps"][-1]["uses"] == "actions/upload-artifact@v4"
    uploaded = build["steps"][-1]["with"]
    assert uploaded["path"].splitlines() == [
        "dist/ROAR-Linux-*-x86_64.AppImage",
        "dist/ROAR-Linux-*-x86_64.AppImage.sha256",
    ]


def test_linux_preview_build_uses_pinned_tool_and_runs_package_checks():
    workflow = load_workflow()
    build_steps = steps_by_name(workflow["jobs"]["build"])
    ubuntu_dependencies = build_steps["Install Ubuntu package dependencies"]
    install = build_steps["Install AppImageTool"]
    package = build_steps["Build and verify AppImage"]
    run_commands = "\n".join(
        step["run"] for step in workflow["jobs"]["build"]["steps"] if "run" in step
    )

    assert "https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage" in install["run"]
    assert "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0" in install["run"]
    assert "dbus-x11" in ubuntu_dependencies["run"].split()
    assert "python -m pytest tests/test_*linux*.py -v" in run_commands
    assert "bash -n linux/build_appimage.sh linux/verify_appimage.sh" in run_commands
    assert "bash linux/build_appimage.sh" in run_commands
    assert "bash linux/verify_appimage.sh dist/ROAR-Linux-*-x86_64.AppImage" in run_commands
    assert package["env"]["APPIMAGE_EXTRACT_AND_RUN"] == "1"


def test_linux_preview_attach_only_updates_an_existing_draft_or_prerelease():
    workflow = load_workflow()
    attach = workflow["jobs"]["attach"]
    attach_steps = steps_by_name(attach)
    release_step = attach_steps["Confirm target is an existing draft or prerelease"]
    release_commands = "\n".join(
        step.get("run", "") for step in attach["steps"]
    )

    assert attach["permissions"] == {"contents": "write"}
    assert attach["needs"] == "build"
    assert attach["if"] == "${{ github.event_name == 'workflow_dispatch' && inputs.release_tag != '' }}"
    assert "gh release view \"$TAG\" --json isDraft,isPrerelease" in release_step["run"]
    assert "isDraft" in release_step["run"]
    assert "isPrerelease" in release_step["run"]
    assert "gh release upload \"$TAG\" \"$APPIMAGE\" \"$SHA\" --clobber" in release_commands
    assert "gh release create" not in release_commands
    assert "gh release edit" not in release_commands
    assert "publish" not in release_commands.lower()


def test_linux_preview_only_attaches_on_manual_release_tag_dispatch():
    workflow = load_workflow()
    triggers = workflow["on"]

    assert {
        "**/*.py",
        "linux/**",
        "roar-linux.spec",
        "requirements-linux*.txt",
        "requirements-linux.txt",
        "assets/**",
        "settings.html",
        "transcript.html",
        "fob.png",
        "licenses/**",
        "THIRD_PARTY_NOTICES.md",
        ".github/workflows/linux-preview.yml",
        "tests/test_*linux*.py",
    } <= set(triggers["pull_request"]["paths"])
    release_tag = triggers["workflow_dispatch"]["inputs"]["release_tag"]
    assert release_tag == {
        "description": "Existing draft/prerelease tag to receive verified assets; leave empty for artifact-only build",
        "required": "false",
        "type": "string",
    }
