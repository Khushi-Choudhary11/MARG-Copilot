"""
Delay prediction service.

Tries to load the trained LightGBM pipeline (best_delay_model.pkl). If the
`lightgbm` package isn't installed, or the model file is missing/corrupt, or
prediction raises for any reason, falls back to:

    delay_next_station = 0.5 * station_average_delay + 0.5 * train_average_delay

This service must NEVER raise - callers always get a numeric prediction plus
a `source` flag ("model" or "fallback").
"""
from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.config import MODEL_PATH, MODEL_METADATA_PATH

logger = logging.getLogger(__name__)


@dataclass
class PredictionResult:
    delay_minutes: float
    source: str  # "model" | "fallback"


class DelayPredictor:
    def __init__(self) -> None:
        self.model: Any | None = None
        self.metadata: dict | None = None
        self.numeric_features: list[str] = []
        self.categorical_features: list[str] = []
        self.feature_columns: list[str] = []
        self._load()

    def _load(self) -> None:
        try:
            with open(MODEL_METADATA_PATH, "rb") as f:
                self.metadata = pickle.load(f)
            self.numeric_features = self.metadata.get("numeric_features", [])
            self.categorical_features = self.metadata.get("categorical_features", [])
            self.feature_columns = self.numeric_features + self.categorical_features
            logger.info(
                "Loaded model metadata: %s (%d numeric, %d categorical features)",
                self.metadata.get("model_name"),
                len(self.numeric_features),
                len(self.categorical_features),
            )
        except Exception:
            logger.exception("Could not load model metadata from %s", MODEL_METADATA_PATH)
            self.metadata = None

        try:
            import joblib  # noqa: F401 - only needed if lightgbm is installed

            self.model = joblib.load(MODEL_PATH)
            logger.info("Loaded trained model from %s", MODEL_PATH)
        except Exception:
            logger.warning(
                "Trained model unavailable (lightgbm not installed or load failed). "
                "Falling back to station/train average delay for all predictions."
            )
            self.model = None

    @property
    def is_model_loaded(self) -> bool:
        return self.model is not None

    @property
    def model_name(self) -> str:
        if self.metadata:
            return self.metadata.get("model_name", "unknown")
        return "fallback"

    def predict(self, row: dict) -> PredictionResult:
        """Predict delay_next_station (minutes) for a single row of features."""
        if self.model is not None and self.feature_columns:
            try:
                frame = {col: [row.get(col)] for col in self.feature_columns}
                df = pd.DataFrame(frame)
                pred = self.model.predict(df)[0]
                return PredictionResult(delay_minutes=round(float(pred), 2), source="model")
            except Exception:
                logger.exception("Model prediction failed, using fallback")

        return PredictionResult(delay_minutes=self._fallback(row), source="fallback")

    @staticmethod
    def _fallback(row: dict) -> float:
        station_avg = row.get("station_average_delay")
        train_avg = row.get("train_average_delay")
        station_avg = float(station_avg) if station_avg is not None and not pd.isna(station_avg) else 0.0
        train_avg = float(train_avg) if train_avg is not None and not pd.isna(train_avg) else 0.0
        return round(0.5 * station_avg + 0.5 * train_avg, 2)


# Module-level singleton, loaded once at app startup.
predictor = DelayPredictor()
