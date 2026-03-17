"""
Evidence Validation (Fail-Closed)
Ensures all insights have proper evidence binding
"""

import json
import logging
from typing import Dict, List, Tuple

import aiosqlite

logger = logging.getLogger(__name__)


async def validate_insight_evidence_binding(
    db_path: str,
    insight_id: str,
    claims: List[Dict],
    evidence_map: Dict[str, Dict],
) -> Tuple[bool, List[str]]:
    """
    Validate insight evidence binding (FAIL-CLOSED)

    Args:
        db_path: Database path
        insight_id: Insight ID
        claims: List of claims [{"text": "...", "evidence_ids": ["E1", "E2"]}]
        evidence_map: Dict of evidence {evidence_id: {...}}

    Returns:
        (is_valid, errors)

    Fail-closed rules:
    1. Every claim must have at least 1 evidence_id
    2. Every evidence_id must exist in evidence_map
    3. Every evidence must have valid locator
    4. Parsing errors = FAIL
    """
    errors = []

    # Validation Rule 0: Claims must be list
    if not isinstance(claims, list):
        errors.append("Claims must be a list")
        return (False, errors)

    # Validation Rule 1: No empty claims
    if not claims:
        errors.append("No claims provided (must have at least 1)")
        return (False, errors)

    # Validation Rule 2: Each claim must have evidence_ids
    for i, claim in enumerate(claims):
        if not isinstance(claim, dict):
            errors.append(f"Claim {i} is not a dict")
            continue

        if "text" not in claim:
            errors.append(f"Claim {i} missing 'text' field")

        if "evidence_ids" not in claim:
            errors.append(f"Claim {i} missing 'evidence_ids' field")
            continue

        evidence_ids = claim["evidence_ids"]

        if not isinstance(evidence_ids, list):
            errors.append(f"Claim {i} evidence_ids is not a list")
            continue

        if not evidence_ids:
            errors.append(f"Claim {i} has no evidence_ids (must have at least 1)")

        # Validation Rule 3: Every evidence_id must exist
        for eid in evidence_ids:
            if eid not in evidence_map:
                errors.append(f"Claim {i} references non-existent evidence: {eid}")

    # Validation Rule 4: Evidence locator validity
    for eid, evidence in evidence_map.items():
        if "locator_json" not in evidence:
            errors.append(f"Evidence {eid} missing 'locator_json'")
            continue

        locator = evidence["locator_json"]

        if not isinstance(locator, dict):
            errors.append(f"Evidence {eid} locator_json is not a dict")
            continue

        # Check locator fields based on source_type
        source_type = evidence.get("source_type", "")

        if source_type == "VAULT":
            required = ["file_path", "chunk_id"]
            for field in required:
                if field not in locator:
                    errors.append(f"Evidence {eid} VAULT locator missing '{field}'")

        elif source_type == "CRAWLED":
            required = ["data_id"]
            for field in required:
                if field not in locator:
                    errors.append(f"Evidence {eid} CRAWLED locator missing '{field}'")

        elif source_type == "SOURCE_ITEM":
            required = ["item_id"]
            for field in required:
                if field not in locator:
                    errors.append(f"Evidence {eid} SOURCE_ITEM locator missing '{field}'")

        else:
            errors.append(f"Evidence {eid} has unknown source_type: {source_type}")

    # Validation Rule 5: Evidence snippet must not be empty
    for eid, evidence in evidence_map.items():
        snippet = evidence.get("snippet", "")
        if not snippet or not snippet.strip():
            errors.append(f"Evidence {eid} has empty snippet")

    # Return result
    is_valid = len(errors) == 0

    if not is_valid:
        logger.warning(
            f"Insight {insight_id} FAILED evidence binding validation: {len(errors)} errors"
        )
        for error in errors:
            logger.warning(f"  - {error}")

    return (is_valid, errors)


async def validate_evidence_exists_in_db(
    db_path: str,
    evidence_ids: List[str],
) -> Tuple[bool, List[str]]:
    """
    Check if evidence IDs exist in database
    Returns: (all_exist, missing_ids)
    """
    missing = []

    async with aiosqlite.connect(db_path) as db:
        for eid in evidence_ids:
            cursor = await db.execute(
                "SELECT 1 FROM evidence WHERE evidence_id = ? LIMIT 1",
                (eid,),
            )
            row = await cursor.fetchone()
            if not row:
                missing.append(eid)

    return (len(missing) == 0, missing)


async def store_insight_claims(
    db_path: str,
    insight_id: str,
    claims: List[Dict],
) -> None:
    """
    Store insight claims in DB
    """
    async with aiosqlite.connect(db_path) as db:
        for claim in claims:
            from uuid import uuid4

            claim_id = str(uuid4())

            await db.execute(
                """
                INSERT INTO insight_claims (claim_id, insight_id, text, evidence_ids_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    claim_id,
                    insight_id,
                    claim["text"],
                    json.dumps(claim["evidence_ids"], ensure_ascii=False),
                ),
            )

        await db.commit()
