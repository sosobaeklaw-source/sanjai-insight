"""
Data Pipeline with ETL (Extract, Transform, Load) capabilities.

Features:
- Modular ETL pipeline
- Data validation and cleansing
- Transformation chains
- Error handling and recovery
- Pipeline monitoring
"""

import asyncio
import logging
import sqlite3
import json
import os
from typing import Dict, List, Optional, Callable, Any, AsyncGenerator
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import hashlib
import traceback

logger = logging.getLogger(__name__)


class StageStatus(Enum):
    """Pipeline stage status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class DataQuality(Enum):
    """Data quality levels."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INVALID = "invalid"


@dataclass
class DataRecord:
    """Data record with metadata."""
    record_id: str
    data: Dict[str, Any]
    metadata: Dict = field(default_factory=dict)
    quality: DataQuality = DataQuality.HIGH
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class PipelineStage:
    """Pipeline stage definition."""
    stage_id: str
    name: str
    processor: Callable
    config: Dict = field(default_factory=dict)
    required: bool = True
    retry_on_failure: bool = False


@dataclass
class PipelineRun:
    """Pipeline execution run."""
    run_id: str
    pipeline_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: StageStatus = StageStatus.RUNNING
    records_processed: int = 0
    records_success: int = 0
    records_failed: int = 0
    stages_completed: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class DataValidator:
    """
    Data validation and quality checking.

    Features:
    - Schema validation
    - Type checking
    - Range validation
    - Custom validators
    """

    def __init__(self):
        """Initialize validator."""
        self._validators: Dict[str, Callable] = {}

    def register_validator(self, name: str, validator: Callable[[Any], bool]):
        """
        Register custom validator.

        Args:
            name: Validator name
            validator: Validation function
        """
        self._validators[name] = validator

    def validate(
        self,
        record: DataRecord,
        schema: Dict[str, Any]
    ) -> DataRecord:
        """
        Validate data record against schema.

        Args:
            record: Data record to validate
            schema: Validation schema

        Returns:
            Validated record with errors/warnings
        """
        errors = []
        warnings = []

        for field, rules in schema.items():
            value = record.data.get(field)

            # Required field check
            if rules.get("required", False) and value is None:
                errors.append(f"Missing required field: {field}")
                continue

            if value is None:
                continue

            # Type check
            expected_type = rules.get("type")
            if expected_type and not isinstance(value, expected_type):
                errors.append(
                    f"Field {field} expected {expected_type.__name__}, "
                    f"got {type(value).__name__}"
                )

            # Range check
            if "min" in rules and value < rules["min"]:
                errors.append(f"Field {field} below minimum: {rules['min']}")

            if "max" in rules and value > rules["max"]:
                errors.append(f"Field {field} above maximum: {rules['max']}")

            # Pattern check
            if "pattern" in rules:
                import re
                if not re.match(rules["pattern"], str(value)):
                    errors.append(f"Field {field} does not match pattern")

            # Custom validators
            if "validator" in rules:
                validator_name = rules["validator"]
                if validator_name in self._validators:
                    if not self._validators[validator_name](value):
                        errors.append(
                            f"Field {field} failed validation: {validator_name}"
                        )

        # Set quality level
        if errors:
            record.quality = DataQuality.INVALID
        elif warnings:
            record.quality = DataQuality.MEDIUM
        else:
            record.quality = DataQuality.HIGH

        record.errors = errors
        record.warnings = warnings

        return record


class DataTransformer:
    """
    Data transformation utilities.

    Features:
    - Field mapping
    - Data normalization
    - Type conversion
    - Aggregation
    """

    @staticmethod
    def map_fields(
        record: DataRecord,
        field_mapping: Dict[str, str]
    ) -> DataRecord:
        """
        Map field names.

        Args:
            record: Input record
            field_mapping: {old_name: new_name}

        Returns:
            Transformed record
        """
        new_data = {}

        for old_name, new_name in field_mapping.items():
            if old_name in record.data:
                new_data[new_name] = record.data[old_name]

        # Keep unmapped fields
        for key, value in record.data.items():
            if key not in field_mapping:
                new_data[key] = value

        record.data = new_data
        return record

    @staticmethod
    def normalize_text(
        record: DataRecord,
        fields: List[str]
    ) -> DataRecord:
        """
        Normalize text fields (lowercase, strip, etc).

        Args:
            record: Input record
            fields: Fields to normalize

        Returns:
            Normalized record
        """
        for field in fields:
            if field in record.data and isinstance(record.data[field], str):
                record.data[field] = record.data[field].strip().lower()

        return record

    @staticmethod
    def convert_types(
        record: DataRecord,
        type_mapping: Dict[str, type]
    ) -> DataRecord:
        """
        Convert field types.

        Args:
            record: Input record
            type_mapping: {field: target_type}

        Returns:
            Converted record
        """
        for field, target_type in type_mapping.items():
            if field in record.data:
                try:
                    record.data[field] = target_type(record.data[field])
                except (ValueError, TypeError) as e:
                    record.errors.append(
                        f"Failed to convert {field} to {target_type.__name__}: {e}"
                    )

        return record

    @staticmethod
    def deduplicate(records: List[DataRecord], key_field: str) -> List[DataRecord]:
        """
        Remove duplicate records based on key field.

        Args:
            records: Input records
            key_field: Field to use as deduplication key

        Returns:
            Deduplicated records
        """
        seen = set()
        unique_records = []

        for record in records:
            key = record.data.get(key_field)
            if key and key not in seen:
                seen.add(key)
                unique_records.append(record)

        return unique_records


class Pipeline:
    """
    Modular ETL data pipeline.

    Features:
    - Multi-stage processing
    - Parallel execution
    - Error recovery
    - Progress tracking
    """

    def __init__(
        self,
        pipeline_id: str,
        db_path: str = "data/pipeline.db"
    ):
        """
        Initialize pipeline.

        Args:
            pipeline_id: Pipeline identifier
            db_path: Database for pipeline state
        """
        self.pipeline_id = pipeline_id
        self.db_path = db_path
        self._stages: List[PipelineStage] = []
        self._ensure_db()

    def _ensure_db(self):
        """Create pipeline database."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    run_id TEXT PRIMARY KEY,
                    pipeline_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL,
                    records_processed INTEGER DEFAULT 0,
                    records_success INTEGER DEFAULT 0,
                    records_failed INTEGER DEFAULT 0,
                    stages_completed TEXT DEFAULT '[]',
                    errors TEXT DEFAULT '[]'
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_pipeline_runs
                ON pipeline_runs(pipeline_id, started_at)
            """)

    def add_stage(
        self,
        stage_id: str,
        name: str,
        processor: Callable,
        config: Optional[Dict] = None,
        required: bool = True
    ):
        """
        Add processing stage to pipeline.

        Args:
            stage_id: Stage identifier
            name: Stage name
            processor: Processing function
            config: Stage configuration
            required: Whether stage is required
        """
        stage = PipelineStage(
            stage_id=stage_id,
            name=name,
            processor=processor,
            config=config or {},
            required=required
        )

        self._stages.append(stage)
        logger.info(f"Added stage {stage_id} to pipeline {self.pipeline_id}")

    async def run(
        self,
        data_source: AsyncGenerator[Dict, None],
        run_id: Optional[str] = None
    ) -> PipelineRun:
        """
        Execute pipeline on data source.

        Args:
            data_source: Async generator yielding data dicts
            run_id: Optional run identifier

        Returns:
            Pipeline run result
        """
        if not run_id:
            run_id = f"{self.pipeline_id}_{int(datetime.utcnow().timestamp())}"

        run = PipelineRun(
            run_id=run_id,
            pipeline_id=self.pipeline_id,
            started_at=datetime.utcnow()
        )

        self._save_run(run)

        logger.info(f"Starting pipeline run {run_id}")

        try:
            async for data_dict in data_source:
                # Create data record
                record_id = hashlib.md5(
                    json.dumps(data_dict, sort_keys=True).encode()
                ).hexdigest()

                record = DataRecord(
                    record_id=record_id,
                    data=data_dict
                )

                # Process through stages
                try:
                    for stage in self._stages:
                        record = await self._process_stage(stage, record)

                        if record.quality == DataQuality.INVALID and stage.required:
                            raise ValueError(f"Invalid data at stage {stage.stage_id}")

                    run.records_success += 1

                except Exception as e:
                    logger.error(f"Failed to process record {record_id}: {e}")
                    run.records_failed += 1
                    run.errors.append(str(e))

                run.records_processed += 1

                # Update progress periodically
                if run.records_processed % 100 == 0:
                    self._save_run(run)

            # Complete
            run.status = StageStatus.COMPLETED
            run.completed_at = datetime.utcnow()
            self._save_run(run)

            logger.info(
                f"Completed pipeline run {run_id}: "
                f"{run.records_success}/{run.records_processed} succeeded"
            )

        except Exception as e:
            logger.error(f"Pipeline run {run_id} failed: {e}")
            run.status = StageStatus.FAILED
            run.completed_at = datetime.utcnow()
            run.errors.append(str(e))
            self._save_run(run)

        return run

    async def _process_stage(
        self,
        stage: PipelineStage,
        record: DataRecord
    ) -> DataRecord:
        """
        Process record through stage.

        Args:
            stage: Pipeline stage
            record: Data record

        Returns:
            Processed record
        """
        try:
            # Execute stage processor
            if asyncio.iscoroutinefunction(stage.processor):
                result = await stage.processor(record, stage.config)
            else:
                result = stage.processor(record, stage.config)

            return result

        except Exception as e:
            logger.error(f"Stage {stage.stage_id} failed: {e}")

            if stage.required:
                raise
            else:
                record.warnings.append(
                    f"Stage {stage.stage_id} failed (non-critical): {e}"
                )
                return record

    def _save_run(self, run: PipelineRun):
        """Save pipeline run to database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO pipeline_runs
                (run_id, pipeline_id, started_at, completed_at, status,
                 records_processed, records_success, records_failed,
                 stages_completed, errors)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run.run_id,
                run.pipeline_id,
                run.started_at.isoformat(),
                run.completed_at.isoformat() if run.completed_at else None,
                run.status.value,
                run.records_processed,
                run.records_success,
                run.records_failed,
                json.dumps(run.stages_completed),
                json.dumps(run.errors)
            ))

    def get_run(self, run_id: str) -> Optional[PipelineRun]:
        """Get pipeline run by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT run_id, pipeline_id, started_at, completed_at, status,
                       records_processed, records_success, records_failed,
                       stages_completed, errors
                FROM pipeline_runs
                WHERE run_id = ?
            """, (run_id,))

            row = cursor.fetchone()
            if not row:
                return None

            return PipelineRun(
                run_id=row[0],
                pipeline_id=row[1],
                started_at=datetime.fromisoformat(row[2]),
                completed_at=datetime.fromisoformat(row[3]) if row[3] else None,
                status=StageStatus(row[4]),
                records_processed=row[5],
                records_success=row[6],
                records_failed=row[7],
                stages_completed=json.loads(row[8]),
                errors=json.loads(row[9])
            )

    def get_recent_runs(self, limit: int = 10) -> List[PipelineRun]:
        """Get recent pipeline runs."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT run_id, pipeline_id, started_at, completed_at, status,
                       records_processed, records_success, records_failed,
                       stages_completed, errors
                FROM pipeline_runs
                WHERE pipeline_id = ?
                ORDER BY started_at DESC
                LIMIT ?
            """, (self.pipeline_id, limit))

            runs = []
            for row in cursor.fetchall():
                runs.append(PipelineRun(
                    run_id=row[0],
                    pipeline_id=row[1],
                    started_at=datetime.fromisoformat(row[2]),
                    completed_at=datetime.fromisoformat(row[3]) if row[3] else None,
                    status=StageStatus(row[4]),
                    records_processed=row[5],
                    records_success=row[6],
                    records_failed=row[7],
                    stages_completed=json.loads(row[8]),
                    errors=json.loads(row[9])
                ))

            return runs


# Example usage
async def example_extract() -> AsyncGenerator[Dict, None]:
    """Example data extraction."""
    # Simulate extracting data from source
    for i in range(100):
        yield {
            "id": i,
            "name": f"Record {i}",
            "value": i * 10,
            "category": "test"
        }


def example_transform(record: DataRecord, config: Dict) -> DataRecord:
    """Example transformation."""
    # Add computed field
    record.data["computed"] = record.data["value"] * 2

    # Normalize name
    if "name" in record.data:
        record.data["name"] = record.data["name"].upper()

    return record


async def example_load(record: DataRecord, config: Dict) -> DataRecord:
    """Example data loading."""
    # Simulate writing to destination
    logger.info(f"Loaded record: {record.record_id}")
    return record


async def run_example_pipeline():
    """Run example pipeline."""
    pipeline = Pipeline("example_pipeline")

    # Add stages
    pipeline.add_stage("extract", "Extract Data", example_extract)
    pipeline.add_stage("transform", "Transform Data", example_transform)
    pipeline.add_stage("load", "Load Data", example_load)

    # Execute
    result = await pipeline.run(example_extract())

    print(f"Pipeline completed: {result.records_success}/{result.records_processed}")
