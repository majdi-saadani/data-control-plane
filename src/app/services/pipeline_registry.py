"""Loads pipeline definitions from the YAML config file and serves them by name."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.core.exceptions import ConfigurationError, NotFoundError
from app.domain.pipeline import Pipeline, PipelinesConfig

logger = logging.getLogger(__name__)


class PipelineRegistry:
    def __init__(self, pipelines: dict[str, Pipeline]) -> None:
        self._pipelines = pipelines

    @classmethod
    def from_yaml(cls, path: str | Path) -> PipelineRegistry:
        file = Path(path)
        if not file.is_file():
            raise ConfigurationError(f"pipelines config not found: {file}")
        try:
            raw = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
            config = PipelinesConfig.model_validate(raw)
        except (yaml.YAMLError, ValidationError) as exc:
            raise ConfigurationError(f"invalid pipelines config {file}: {exc}") from exc
        logger.info("Loaded %d pipeline(s) from %s", len(config.pipelines), file)
        return cls(config.pipelines)

    def list(self) -> list[Pipeline]:
        return list(self._pipelines.values())

    def get(self, name: str) -> Pipeline:
        try:
            return self._pipelines[name]
        except KeyError:
            raise NotFoundError(f"pipeline '{name}' not found") from None
