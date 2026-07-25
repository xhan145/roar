# Root conftest: makes pytest add the project root to sys.path so tests can
# import the app modules (commands, config, recorder, ...) directly.


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "kokoro_model: opt-in test requiring a preinstalled verified local "
        "Kokoro voice pack and Python 3.12 runtime; never downloads")
