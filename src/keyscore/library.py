"""本地曲谱库的扫描、创建和导入。"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .parser import ScoreParseError, parse_score


@dataclass(frozen=True)
class ScoreEntry:
    """表示歌单中的一份本地曲谱。"""

    title: str
    path: Path


def default_data_directory() -> Path:
    """
    返回键谱数据目录。

    Returns:
        Path: 保存曲谱和设置的目录。
    """

    configured = os.environ.get("KEYSCORE_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data"


class ScoreLibrary:
    """管理应用数据目录中的 UTF-8 文本曲谱。"""

    def __init__(self, root: Path) -> None:
        """
        初始化并创建曲谱目录。

        Args:
            root (Path): 应用数据根目录。
        """

        self.root = root
        self.scores_directory = root / "scores"
        self.scores_directory.mkdir(parents=True, exist_ok=True)
        self._ensure_example()

    def entries(self) -> tuple[ScoreEntry, ...]:
        """
        扫描并返回所有本地曲谱。

        Returns:
            tuple[ScoreEntry, ...]: 按曲名排序的曲谱列表。
        """

        result: list[ScoreEntry] = []
        for path in self.scores_directory.glob("*.txt"):
            try:
                text = path.read_text(encoding="utf-8")
                title = parse_score(text).title
            except (OSError, UnicodeError, ScoreParseError):
                title = path.stem
            result.append(ScoreEntry(title=title, path=path))
        return tuple(sorted(result, key=lambda entry: entry.title.casefold()))

    def import_score(self, source: Path) -> ScoreEntry:
        """
        将外部曲谱复制到本地曲谱库。

        Args:
            source (Path): 待导入的 UTF-8 文本曲谱。

        Returns:
            ScoreEntry: 导入后的曲谱条目。

        Raises:
            ValueError: 文件不是有效曲谱时抛出。
            OSError: 读取或复制失败时抛出。
        """

        text = source.read_text(encoding="utf-8")
        try:
            score = parse_score(text)
        except ScoreParseError as exc:
            raise ValueError(str(exc)) from exc
        destination = self._unique_path(source.stem)
        shutil.copy2(source, destination)
        return ScoreEntry(score.title, destination)

    def create_score(self, title: str = "未命名曲谱") -> ScoreEntry:
        """
        创建一份可立即编辑的新曲谱。

        Args:
            title (str): 初始曲名。

        Returns:
            ScoreEntry: 新建曲谱条目。
        """

        path = self._unique_path(title)
        path.write_text(
            f"@title {title}\n@bpm 100\n@beat 4/4\n@section_gap 2\n\n"
            "1 2 3 4 | 5 6 7 8 |\n---\n1 2 3 4 |\n",
            encoding="utf-8",
        )
        return ScoreEntry(title, path)

    def _unique_path(self, stem: str) -> Path:
        """
        为新曲谱生成不覆盖已有文件的路径。

        Args:
            stem (str): 期望的文件名主体。

        Returns:
            Path: 可用目标路径。
        """

        safe_stem = "".join(character for character in stem if character not in '<>:"/\\|?*').strip()
        safe_stem = safe_stem or "score"
        candidate = self.scores_directory / f"{safe_stem}.txt"
        suffix = 2
        while candidate.exists():
            candidate = self.scores_directory / f"{safe_stem} {suffix}.txt"
            suffix += 1
        return candidate

    def _ensure_example(self) -> None:
        """在空曲谱库中创建一份示例曲谱。"""

        if any(self.scores_directory.glob("*.txt")):
            return
        path = self.scores_directory / "小星星.txt"
        path.write_text(
            "@title 小星星\n@bpm 100\n@beat 4/4\n@section_gap 2\n\n"
            "1 1 5 5 | 6 6 5:2 |\n---\n4 4 3 3 | 2 2 1:2 |\n",
            encoding="utf-8",
        )
