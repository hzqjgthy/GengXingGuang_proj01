import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class CaseStore:
    def __init__(self, data_dir: Path):
        self._cases_path = data_dir / "cases.json"
        self._results_path = data_dir / "demo_results.json"
        self._cases = self._read_json(self._cases_path)
        self._results = self._read_json(self._results_path)

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def list_cases(self) -> List[Dict[str, Any]]:
        summaries = []
        for case in self._cases["cases"]:
            summaries.append(
                {
                    "id": case["id"],
                    "code": case["code"],
                    "display_name": case["display_name"],
                    "age": case["age"],
                    "sex": case["sex"],
                    "headline": case["headline"],
                    "expected_syndrome": case["expected_syndrome"],
                    "image_url": case["image_url"],
                    "accent": case["accent"],
                }
            )
        return summaries

    def get_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        for case in self._cases["cases"]:
            if case["id"] == case_id:
                return copy.deepcopy(case)
        return None

    def get_result(self, result_key: str) -> Optional[Dict[str, Any]]:
        result = self._results.get(result_key)
        return copy.deepcopy(result) if result else None

    def get_result_keys(self) -> List[str]:
        return list(self._results.keys())

