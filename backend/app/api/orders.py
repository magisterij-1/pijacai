from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.api.dependencies import require_roles
from app.database import get_db
from app.models import OrderStatus, Product, ProductionOrder, Recipe, RecipeItem, Role, User
from app.schemas.orders import MaterialRequirement, OrderCreate, OrderOut, OrderPreviewIn, OrderPreviewOut, ProductOption


router = APIRouter(prefix="/api", tags=["Proizvodni nalogi"])


def recipe_items():
    return selectinload(Recipe.items).joinedload(RecipeItem.material)


def active_recipe(db: Session, product_id: int, lock: bool = False):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Izdelek ni najden.")
    query = select(Recipe).where(Recipe.product_id == product_id, Recipe.active.is_(True)).options(recipe_items())
    if lock:
        query = query.with_for_update()
    recipe = db.scalar(query)
    if recipe is None:
        raise HTTPException(status_code=409, detail="Za ta izdelek ni aktivne recepture.")
    if not recipe.items:
        raise HTTPException(status_code=409, detail="Receptura mora vsebovati vsaj eno surovino.")
    return product, recipe


def preview(product: Product, recipe: Recipe, planned_qty: int) -> OrderPreviewOut:
    return OrderPreviewOut(
        product_id=product.id, product_name=product.name, product_unit=product.unit,
        recipe_id=recipe.id, recipe_version=recipe.version, output_qty=recipe.output_qty,
        planned_qty=planned_qty,
        requirements=[MaterialRequirement(
            material_id=item.material_id, material_name=item.material.name,
            material_type=item.material.type, unit=item.material.unit,
            required_qty=item.qty * planned_qty / recipe.output_qty,
        ) for item in recipe.items],
    )


def order_view(order: ProductionOrder) -> OrderOut:
    return OrderOut(
        **preview(order.product, order.recipe, order.planned_qty).model_dump(),
        id=order.id, planned_date=order.planned_date, status=order.status, created_by=order.created_by,
    )


@router.get("/lookup/products", response_model=list[ProductOption])
def products(user: User = Depends(require_roles(Role.planner)), db: Session = Depends(get_db)):
    return db.scalars(select(Product).join(Recipe, Recipe.product_id == Product.id).where(
        Recipe.active.is_(True), Recipe.items.any(),
    ).order_by(Product.name, Product.id)).all()


@router.post("/orders/preview", response_model=OrderPreviewOut)
def preview_order(data: OrderPreviewIn, user: User = Depends(require_roles(Role.planner)), db: Session = Depends(get_db)):
    product, recipe = active_recipe(db, data.product_id)
    return preview(product, recipe, data.planned_qty)


@router.post("/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(data: OrderCreate, user: User = Depends(require_roles(Role.planner)), db: Session = Depends(get_db)):
    # Poslovni dan temelji na slovenskem časovnem pasu, tudi če kontejner uporablja UTC.
    today = db.scalar(select(cast(func.timezone("Europe/Ljubljana", func.now()), Date)))
    if data.planned_date < today:
        raise HTTPException(status_code=422, detail=[{
            "loc": ["body", "planned_date"], "msg": "Načrtovan datum ne sme biti v preteklosti.", "type": "value_error",
        }])
    product, recipe = active_recipe(db, data.product_id, lock=True)
    if data.recipe_id is not None and data.recipe_id != recipe.id:
        raise HTTPException(status_code=409, detail="Receptura se je spremenila. Ponovno preveri potrebne količine.")
    order = ProductionOrder(
        product_id=product.id, recipe_id=recipe.id, planned_qty=data.planned_qty,
        planned_date=data.planned_date, status=OrderStatus.planned, created_by=user.id,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order_view(order)


@router.get("/orders", response_model=list[OrderOut])
def orders(user: User = Depends(require_roles(Role.planner, Role.operator)), db: Session = Depends(get_db)):
    query = select(ProductionOrder).options(
        joinedload(ProductionOrder.product),
        joinedload(ProductionOrder.recipe).selectinload(Recipe.items).joinedload(RecipeItem.material),
    ).order_by(ProductionOrder.id)
    if user.role == Role.operator:
        query = query.where(ProductionOrder.status.in_([OrderStatus.planned, OrderStatus.in_progress]))
    return [order_view(order) for order in db.scalars(query).all()]
