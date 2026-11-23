r"""The data folder of the app: %LOCALAPPDATA%\BoshMow, outside the repository."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DataFolder:
    """The data folder and the place of each thing in it."""

    root: Path

    @property
    def database(self) -> Path:
        return self.root / "bosh.db"

    @property
    def resources(self) -> Path:
        """The untouched copies of the imported files."""
        return self.root / "resources"

    @property
    def ai_log(self) -> Path:
        """The log of the AI calls, one JSON line per call."""
        return self.root / "logs" / "ai_calls.jsonl"


def default_data_folder() -> DataFolder:
    r"""%LOCALAPPDATA%\BoshMow."""
    return DataFolder(Path(os.environ["LOCALAPPDATA"]) / "BoshMow")
