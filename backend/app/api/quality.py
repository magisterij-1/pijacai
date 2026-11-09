from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.batches import PathId, detail
from app.api.dependencies import require_roles
from app.database import get_db
from app.models import Batch, BatchStatus, ProductionOrder, QualityCheck, QualityParameter, Role, User
from app.schemas.quality import BatchReject, ParameterWithLatest, QualityCheckCreate, QualityCheckOut, QualityOverview
from app.schemas.batches import BatchDetail


router = APIRouter(prefix="/api", tags=["Kakovost"])


@router.post("/batches/{batch_id}/reject", response_model=BatchDetail)
def reject_batch(batch_id: PathId, data: BatchReject, user: User = Depends(require_roles(Role.quality)), db: Session = Depends(get_db)):
    try:
        batch = db.scalar(select(Batch).where(Batch.id == batch_id).with_for_update().execution_options(populate_existing=True))
        if batch is None:
            raise HTTPException(status_code=404, detail="Šarža ni najdena.")
        if batch.status != BatchStatus.awaiting_qc:
            raise HTTPException(status_code=409, detail="Zavrniti je mogoče samo šaržo, ki čaka na kontrolo.")
        batch.status = BatchStatus.rejected
        batch.decision_note = data.decision_note
        batch.decided_by = user.id
        batch.decided_at = db.scalar(select(func.clock_timestamp()))
        db.flush()
        result = detail(db, batch)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.post("/batches/{batch_id}/release", response_model=BatchDetail)
def release_batch(batch_id: PathId, user: User = Depends(require_roles(Role.quality)), db: Session = Depends(get_db)):
    try:
        # Zapis meritve in odločitev zakleneta isto šaržo, zato se ne moreta prehiteti.
        batch = db.scalar(select(Batch).where(Batch.id == batch_id).with_for_update().execution_options(populate_existing=True))
        if batch is None:
            raise HTTPException(status_code=404, detail="Šarža ni najdena.")
        if batch.status != BatchStatus.awaiting_qc:
            raise HTTPException(status_code=409, detail="Sprostiti je mogoče samo šaržo, ki čaka na kontrolo.")
        order = db.get(ProductionOrder, batch.order_id)
        parameters = db.scalars(select(QualityParameter).where(QualityParameter.product_id == order.product_id)
                               .order_by(QualityParameter.id).with_for_update(read=True)).all()
        if not parameters:
            raise HTTPException(status_code=422, detail={
                "code": "NO_QUALITY_PARAMETERS", "message": "Izdelek nima določenih parametrov kakovosti.",
                "missing": [], "invalid": [],
            })
        checks = db.scalars(select(QualityCheck).where(QualityCheck.batch_id == batch.id)
                            .order_by(QualityCheck.checked_at.desc(), QualityCheck.id.desc())
                            .execution_options(populate_existing=True)).all()
        latest = {}
        for check in checks:
            latest.setdefault(check.parameter_id, check)
        missing = [{"parameter_id": item.id, "name": item.name} for item in parameters if item.id not in latest]
        invalid = [{"parameter_id": item.id, "name": item.name} for item in parameters
                   if item.id in latest and not latest[item.id].passed]
        if missing or invalid:
            raise HTTPException(status_code=422, detail={
                "code": "QUALITY_NOT_PASSED", "message": "Za sprostitev morajo biti vnesene in ustrezne vse zahtevane meritve.",
                "missing": missing, "invalid": invalid,
            })
        batch.status = BatchStatus.released
        batch.decided_by = user.id
        batch.decided_at = db.scalar(select(func.clock_timestamp()))
        batch.decision_note = None
        db.flush()
        result = detail(db, batch)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.get("/batches/{batch_id}/checks", response_model=QualityOverview)
def batch_checks(batch_id: PathId, user: User = Depends(require_roles(Role.quality)), db: Session = Depends(get_db)):
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Šarža ni najdena.")
    order = db.get(ProductionOrder, batch.order_id)
    parameters = db.scalars(select(QualityParameter).where(QualityParameter.product_id == order.product_id)
                           .order_by(QualityParameter.id)).all()
    checks = db.scalars(select(QualityCheck).where(QualityCheck.batch_id == batch.id)
                       .order_by(QualityCheck.checked_at.desc(), QualityCheck.id.desc())).all()
    latest = {}
    history = [QualityCheckOut.model_validate(check) for check in checks]
    for check in history:
        latest.setdefault(check.parameter_id, check)
    return QualityOverview(batch_id=batch.id, checks=history, parameters=[ParameterWithLatest(
        id=parameter.id, product_id=parameter.product_id, name=parameter.name, unit=parameter.unit,
        min_value=parameter.min_value, max_value=parameter.max_value, latest_check=latest.get(parameter.id),
    ) for parameter in parameters])


@router.post("/batches/{batch_id}/checks", response_model=QualityCheckOut, status_code=status.HTTP_201_CREATED)
def create_check(batch_id: PathId, data: QualityCheckCreate, user: User = Depends(require_roles(Role.quality)), db: Session = Depends(get_db)):
    try:
        batch = db.scalar(select(Batch).where(Batch.id == batch_id).with_for_update().execution_options(populate_existing=True))
        if batch is None:
            raise HTTPException(status_code=404, detail="Šarža ni najdena.")
        if batch.status != BatchStatus.awaiting_qc:
            raise HTTPException(status_code=409, detail="Meritve je mogoče vnašati samo za šaržo, ki čaka na kontrolo.")
        parameter = db.scalar(select(QualityParameter).where(QualityParameter.id == data.parameter_id)
                              .with_for_update(read=True).execution_options(populate_existing=True))
        if parameter is None:
            raise HTTPException(status_code=404, detail="Parameter kakovosti ni najden.")
        order = db.get(ProductionOrder, batch.order_id)
        if parameter.product_id != order.product_id:
            raise HTTPException(status_code=422, detail=[{
                "loc": ["body", "parameter_id"], "type": "value_error", "msg": "Parameter ne pripada izdelku šarže.",
            }])
        check = QualityCheck(batch_id=batch.id, parameter_id=parameter.id, value=data.value,
                             passed=parameter.min_value <= data.value <= parameter.max_value,
                             checked_by=user.id, checked_at=db.scalar(select(func.clock_timestamp())))
        db.add(check)
        db.flush()
        db.refresh(check)
        result = QualityCheckOut.model_validate(check)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
