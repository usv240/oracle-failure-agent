from fastapi import APIRouter
from backend.db.schemas import DecisionAuditInput, AuditResponse
from backend.services.auditor import audit_decision
from backend.services.output_writer import write_audit

router = APIRouter()


@router.post("/evaluate", response_model=AuditResponse)
async def evaluate_decision(body: DecisionAuditInput):
    result = await audit_decision(body.decision, body.metrics)
    result.output_file = write_audit(result)
    return result
