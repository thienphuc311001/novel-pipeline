"""Small native-format master dictionary fixture used by unit/UI tests."""

from __future__ import annotations

import json
from pathlib import Path

from chinese.master_dictionary import MasterDictionary


def create_dictionary_fixture(root: Path) -> MasterDictionary:
    dictionary_dir = root / "dictionary"
    dictionary_dir.mkdir(parents=True, exist_ok=True)
    (dictionary_dir / "ChinesePhienAmWords.txt").write_text(
        "大=đại\n相=tương\n国=quốc\n寺=tự\n未=vị\n知=tri\n词=từ\n的=đích\n人=nhân\n",
        encoding="utf-8",
    )
    (dictionary_dir / "LuatNhan.txt").write_text(
        "{0} 的人=người {0}\n{0} 的人={0} nhân\n",
        encoding="utf-8",
    )
    (dictionary_dir / "Names.txt").write_text(
        "\ufeff大相国寺=Đại Tướng Quốc Tự\n清风=Thanh Phong\ninvalid row\n",
        encoding="utf-8",
    )
    (dictionary_dir / "QualityOverrides.txt").write_text(
        "# quality patches\n清风=Thanh Phong\t20\n",
        encoding="utf-8",
    )
    (dictionary_dir / "VietPhrase_1.txt").write_text(
        "大相=đại tướng\n清风=gió mát\n阻挡不了=không ngăn được/không ngăn trở\n",
        encoding="utf-8",
    )
    (dictionary_dir / "VietPhrase_2.txt").write_text(
        "大=tòa/lớn\n清风=Thanh Phong\n未知=không biết\n词=từ\n修炼者=tu luyện giả\n修炼=tu luyện\n正文中的中文词语=nội dung tiếng Trung\n",
        encoding="utf-8",
    )
    (dictionary_dir / "dict-default.json").write_text(
        json.dumps(
            {
                "phienam": {
                    "大": "đại",
                    "相": "tướng",
                    "国": "quốc",
                    "寺": "tự",
                    "未": "vị",
                    "知": "tri",
                    "词": "từ",
                    "的": "đích",
                    "人": "nhân",
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return MasterDictionary(dictionary_dir, root / "master.sqlite3")

