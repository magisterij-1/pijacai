# — izračun potreb, zaklepi in transakcijski FIFO odpis.
from decimal import Decimal
from fractions import Fraction

from fastapi import HTTPException
from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import Batch, BatchConsumption, BatchStatus, Material, MaterialLot, OrderStatus, ProductionLine, ProductionOrder, Recipe, RecipeItem, User
from app.schemas.batches import BatchPreview, BatchStart, StockRequirement


def required_quantity(item: RecipeItem, quantity: Decimal, output: Decimal) -> Decimal:
    scaled = Fraction(item.qty) * Fraction(quantity) / Fraction(output) * 1000
    if scaled.denominator != 1:
        raise HTTPException(status_code=422, detail=[{
            "loc": ["body", "qty"], "type": "value_error",
            "msg": f"Izberi količino šarže, ki omogoča natančen odpis {item.material.name} na 0,001 {item.material.unit}.",
        }])
    return Decimal(scaled.numerator) / Decimal(1000)


def prepare(db: Session, order_id: int, data: BatchStart, lock: bool = False):
    order_query = select(ProductionOrder).where(ProductionOrder.id == order_id).execution_options(populate_existing=True)
    line_query = select(ProductionLine).where(ProductionLine.id == data.line_id).execution_options(populate_existing=True)
    if lock:
        order_query = order_query.with_for_update()
        line_query = line_query.with_for_update()
    order = db.scalar(order_query)
    if order is None:
        raise HTTPException(status_code=404, detail="Proizvodni nalog ni najden.")
    if order.status not in (OrderStatus.planned, OrderStatus.in_progress):
        raise HTTPException(status_code=409, detail="Šaržo je mogoče zagnati samo za načrtovan ali tekoč nalog.")
    line = db.scalar(line_query)
    if line is None:
        raise HTTPException(status_code=404, detail="Proizvodna linija ni najdena.")
    if not line.active:
        raise HTTPException(status_code=409, detail="Proizvodna linija ni aktivna.")
    recipe = db.scalar(select(Recipe).where(Recipe.id == order.recipe_id).options(selectinload(Recipe.items).joinedload(RecipeItem.material)))
    if recipe is None or recipe.product_id != order.product_id or not recipe.items:
        raise HTTPException(status_code=409, detail="Nalog nima veljavne pripete recepture.")
    items = sorted(recipe.items, key=lambda item: item.material_id)
    required = [(item, required_quantity(item, data.qty, recipe.output_qty)) for item in items]
    material_ids = [item.material_id for item in items]
    if lock:
        # Enak vrstni red materialov preprečuje krožno čakanje med zagoni različnih nalogov.
        db.execute(select(Material.id).where(Material.id.in_(material_ids)).order_by(Material.id).with_for_update()).all()
    query = select(MaterialLot).where(
        MaterialLot.material_id.in_(material_ids), MaterialLot.remaining_qty > 0,
    ).order_by(MaterialLot.material_id, MaterialLot.received_at, MaterialLot.id).execution_options(populate_existing=True)
    if lock:
        query = query.with_for_update()
    lots = db.scalars(query).all()
    grouped = {material_id: [] for material_id in material_ids}
    for lot in lots:
        grouped[lot.material_id].append(lot)
    requirements = []
    for item, needed in required:
        available = sum((lot.remaining_qty for lot in grouped[item.material_id]), Decimal("0.000"))
        missing = max(needed - available, Decimal("0.000"))
        requirements.append(StockRequirement(
            material_id=item.material_id, material_name=item.material.name, unit=item.material.unit,
            required_qty=needed, available_qty=available, missing_qty=missing,
            status="PREMALO" if missing > 0 else "OK",
        ))
    result = BatchPreview(
        order_id=order.id, recipe_id=recipe.id, recipe_version=recipe.version,
        line_id=line.id, qty=data.qty, can_start=all(item.missing_qty == 0 for item in requirements), requirements=requirements,
    )
    return order, line, result, grouped


def start(db: Session, order_id: int, data: BatchStart, operator: User) -> Batch:
    order, line, result, grouped = prepare(db, order_id, data, lock=True)
    if not result.can_start:
        raise HTTPException(status_code=409, detail={
            "code": "INSUFFICIENT_STOCK", "message": "Za zagon šarže ni dovolj zaloge.",
            "missing": [item.model_dump(mode="json") for item in result.requirements if item.missing_qty > 0],
        })
    started_at = db.scalar(select(func.clock_timestamp()))
    production_date = db.scalar(select(cast(func.timezone("Europe/Ljubljana", started_at), Date)))
    # Linija je zaklenjena, zato sta štetje in rezervacija dnevne zaporedne številke usklajena.
    sequence = (db.scalar(select(func.max(Batch.sequence_no)).where(Batch.line_id == line.id, Batch.production_date == production_date)) or 0) + 1
    batch = Batch(
        batch_code=f"{production_date.isoformat()}-L{line.id}-{sequence:02d}",
        order_id=order.id, line_id=line.id, production_date=production_date, sequence_no=sequence,
        operator_id=operator.id, status=BatchStatus.in_production, planned_qty=data.qty, started_at=started_at,
    )
    db.add(batch)
    db.flush()
    for requirement in result.requirements:
        remaining = requirement.required_qty
        for lot in grouped[requirement.material_id]:
            used = min(remaining, lot.remaining_qty)
            if used > 0:
                lot.remaining_qty -= used
                db.add(BatchConsumption(batch_id=batch.id, material_lot_id=lot.id, qty=used))
                remaining -= used
            if remaining == 0:
                break
        if remaining != 0:
            raise RuntimeError("Odpis porabe se ne ujema s preverjeno zalogo.")
    order.status = OrderStatus.in_progress
    db.flush()
    return batch
